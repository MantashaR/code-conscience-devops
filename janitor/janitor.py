"""
NimbusKart Cost Janitor.

Scans an AWS account (or a LocalStack/moto emulation of one) for orphaned
resources, writes a structured JSON report plus a Markdown summary, and either
reports (--dry-run, the default) or destroys (--delete) them.

In --delete mode every resource carrying the tag `Protected=true` is skipped
unconditionally — this is the escape hatch for resources whose ownership is
unclear but which are known to be load-bearing.

Exit codes:
    0  no orphans found, or --delete completed
    2  orphans found in --dry-run mode (so CI can fail PRs)
    1  runtime error
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from constants import (
    EBS_GP3_USD_PER_GB_MONTH,
    EIP_UNASSOCIATED_MONTHLY_USD,
    PROTECTED_TAG_KEY,
    PROTECTED_TAG_VALUE,
    REQUIRED_TAGS,
    STOPPED_INSTANCE_MONTHLY_USD,
)

logger = logging.getLogger("janitor")

EXIT_OK = 0
EXIT_RUNTIME_ERROR = 1
EXIT_ORPHANS_FOUND = 2


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class Finding:
    """One orphan record. Matches the schema in section 4.4 of the brief.

    Extra fields are allowed by the schema but none of the listed fields may
    be renamed or removed.
    """

    resource_id: str
    resource_type: str
    reason: str
    age_days: int | None
    estimated_monthly_cost_usd: float
    tags: dict
    suggested_action: str
    safe_to_auto_delete: bool


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _tags_to_dict(tag_list) -> dict:
    if not tag_list:
        return {}
    return {t["Key"]: t.get("Value", "") for t in tag_list}


def _missing_required_tags(tags: dict) -> list[str]:
    return [k for k in REQUIRED_TAGS if not tags.get(k)]


def _is_protected(tags: dict) -> bool:
    return str(tags.get(PROTECTED_TAG_KEY, "")).strip().lower() == PROTECTED_TAG_VALUE


def _missing_tags_dict(tags: dict) -> dict:
    """Return the input tags merged with `None` for every required key that's
    absent — matches the spec's example where missing tags appear as null."""
    out = dict(tags)
    for k in REQUIRED_TAGS:
        if not out.get(k):
            out[k] = None
    return out


# ---------------------------------------------------------------------------
# Detectors
# ---------------------------------------------------------------------------


def detect_unattached_volumes(ec2) -> list[Finding]:
    findings: list[Finding] = []
    paginator = ec2.get_paginator("describe_volumes")
    for page in paginator.paginate(
        Filters=[{"Name": "status", "Values": ["available"]}]
    ):
        for vol in page.get("Volumes", []):
            tags = _tags_to_dict(vol.get("Tags", []))
            create_time = vol.get("CreateTime")
            age = (_utcnow() - create_time).days if create_time else None
            size_gb = vol.get("Size", 0)
            cost = round(size_gb * EBS_GP3_USD_PER_GB_MONTH, 2)

            findings.append(
                Finding(
                    resource_id=vol["VolumeId"],
                    resource_type="ebs_volume",
                    reason="unattached",
                    age_days=age,
                    estimated_monthly_cost_usd=cost,
                    tags=tags,
                    suggested_action="delete",
                    # An unattached volume that's properly tagged and not
                    # protected is the only case we mark as auto-safe. Anything
                    # missing tags could belong to someone we don't know.
                    safe_to_auto_delete=(
                        not _missing_required_tags(tags) and not _is_protected(tags)
                    ),
                )
            )
    return findings


def _parse_state_transition_time(reason: str) -> datetime | None:
    """EC2 returns StateTransitionReason like:
        "User initiated (2026-05-01 12:00:00 GMT)"
    LocalStack and moto sometimes return empty strings or different formats —
    return None and let the caller fall back to LaunchTime."""
    if not reason or "(" not in reason or ")" not in reason:
        return None
    try:
        inside = reason.split("(", 1)[1].rsplit(")", 1)[0]
        # Strip the trailing timezone word ("GMT", "UTC") if present.
        parts = inside.rsplit(" ", 1)
        ts = parts[0] if parts[-1].isalpha() else inside
        return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except (ValueError, IndexError):
        return None


def detect_stopped_instances(
    ec2, age_threshold_days: int
) -> list[Finding]:
    findings: list[Finding] = []
    cutoff = _utcnow() - timedelta(days=age_threshold_days)

    paginator = ec2.get_paginator("describe_instances")
    for page in paginator.paginate(
        Filters=[{"Name": "instance-state-name", "Values": ["stopped"]}]
    ):
        for reservation in page.get("Reservations", []):
            for inst in reservation.get("Instances", []):
                tags = _tags_to_dict(inst.get("Tags", []))

                # Prefer the actual stop transition time; fall back to launch.
                transition_dt = _parse_state_transition_time(
                    inst.get("StateTransitionReason", "")
                ) or inst.get("LaunchTime")
                if transition_dt is None or transition_dt > cutoff:
                    continue

                age = (_utcnow() - transition_dt).days
                findings.append(
                    Finding(
                        resource_id=inst["InstanceId"],
                        resource_type="ec2_instance",
                        reason="stopped_too_long",
                        age_days=age,
                        estimated_monthly_cost_usd=STOPPED_INSTANCE_MONTHLY_USD,
                        tags=tags,
                        suggested_action="terminate",
                        # Terminating an EC2 instance is destructive (root EBS
                        # gone, metadata lost). Never auto-safe — humans must
                        # confirm even if tags are clean.
                        safe_to_auto_delete=False,
                    )
                )
    return findings


def detect_unassociated_eips(ec2) -> list[Finding]:
    findings: list[Finding] = []
    addresses = ec2.describe_addresses().get("Addresses", [])
    for addr in addresses:
        if addr.get("AssociationId") or addr.get("InstanceId"):
            continue
        tags = _tags_to_dict(addr.get("Tags", []))
        rid = addr.get("AllocationId") or addr.get("PublicIp")
        findings.append(
            Finding(
                resource_id=rid,
                resource_type="elastic_ip",
                reason="unassociated",
                age_days=None,  # EIPs don't carry creation timestamps.
                estimated_monthly_cost_usd=round(EIP_UNASSOCIATED_MONTHLY_USD, 2),
                tags=tags,
                suggested_action="release",
                safe_to_auto_delete=(
                    not _missing_required_tags(tags) and not _is_protected(tags)
                ),
            )
        )
    return findings


def _untagged_finding(rid: str, rtype: str, tags: dict) -> Finding:
    missing = _missing_required_tags(tags)
    return Finding(
        resource_id=rid,
        resource_type=rtype,
        reason="missing_required_tags:" + ",".join(missing),
        age_days=None,
        # Missing tags isn't a direct $ cost — it's a cost-attribution risk.
        # We surface it as $0 so the summary number reflects real spend; the
        # finding still counts toward total_orphans.
        estimated_monthly_cost_usd=0.0,
        tags=_missing_tags_dict(tags),
        suggested_action="tag",
        safe_to_auto_delete=False,
    )


def detect_untagged_resources(ec2) -> list[Finding]:
    findings: list[Finding] = []

    for reservation in ec2.describe_instances().get("Reservations", []):
        for inst in reservation.get("Instances", []):
            tags = _tags_to_dict(inst.get("Tags", []))
            if _missing_required_tags(tags):
                findings.append(_untagged_finding(inst["InstanceId"], "ec2_instance", tags))

    for vol in ec2.describe_volumes().get("Volumes", []):
        tags = _tags_to_dict(vol.get("Tags", []))
        if _missing_required_tags(tags):
            findings.append(_untagged_finding(vol["VolumeId"], "ebs_volume", tags))

    for addr in ec2.describe_addresses().get("Addresses", []):
        tags = _tags_to_dict(addr.get("Tags", []))
        if _missing_required_tags(tags):
            rid = addr.get("AllocationId") or addr.get("PublicIp")
            findings.append(_untagged_finding(rid, "elastic_ip", tags))

    return findings


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def _deduplicate(findings: Iterable[Finding]) -> list[Finding]:
    """A resource can hit multiple detectors (e.g. unattached AND untagged).
    Merge into one finding per (id, type), concatenating reasons and taking
    the larger cost estimate so we don't double-count waste."""
    seen: dict[tuple[str, str], Finding] = {}
    for f in findings:
        key = (f.resource_id, f.resource_type)
        if key not in seen:
            seen[key] = f
            continue
        existing = seen[key]
        if f.reason not in existing.reason:
            existing.reason = f"{existing.reason};{f.reason}"
        existing.estimated_monthly_cost_usd = max(
            existing.estimated_monthly_cost_usd, f.estimated_monthly_cost_usd
        )
        # Lose auto-safe if any detector marked it unsafe; merge tag info.
        existing.safe_to_auto_delete = (
            existing.safe_to_auto_delete and f.safe_to_auto_delete
        )
        for k, v in f.tags.items():
            existing.tags.setdefault(k, v)
    return list(seen.values())


def scan(ec2, age_threshold_days: int) -> list[Finding]:
    findings: list[Finding] = []
    findings.extend(detect_unattached_volumes(ec2))
    findings.extend(detect_stopped_instances(ec2, age_threshold_days))
    findings.extend(detect_unassociated_eips(ec2))
    findings.extend(detect_untagged_resources(ec2))
    return _deduplicate(findings)


def build_report(findings: list[Finding], account_id: str, region: str) -> dict:
    return {
        "scan_timestamp": _utcnow().replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "account_id": account_id,
        "region": region,
        "summary": {
            "total_orphans": len(findings),
            "estimated_monthly_waste_usd": round(
                sum(f.estimated_monthly_cost_usd for f in findings), 2
            ),
        },
        "findings": [asdict(f) for f in findings],
    }


def render_markdown(report: dict) -> str:
    lines = [
        "# Cost Janitor — Orphan Scan Report",
        "",
        f"- **Scan timestamp:** `{report['scan_timestamp']}`",
        f"- **Account:** `{report['account_id']}`",
        f"- **Region:** `{report['region']}`",
        f"- **Total orphans:** **{report['summary']['total_orphans']}**",
        f"- **Estimated monthly waste:** **${report['summary']['estimated_monthly_waste_usd']:.2f}**",
        "",
    ]
    if not report["findings"]:
        lines.append("_No orphans found. Account is clean._")
        return "\n".join(lines) + "\n"

    lines.extend(
        [
            "| Resource | Type | Reason | Age (days) | Monthly $ | Suggested action | Auto-safe |",
            "|---|---|---|---|---|---|---|",
        ]
    )
    for f in report["findings"]:
        lines.append(
            "| `{rid}` | {rtype} | {reason} | {age} | ${cost:.2f} | {action} | {safe} |".format(
                rid=f["resource_id"],
                rtype=f["resource_type"],
                reason=f["reason"],
                age=f["age_days"] if f["age_days"] is not None else "n/a",
                cost=f["estimated_monthly_cost_usd"],
                action=f["suggested_action"],
                safe="yes" if f["safe_to_auto_delete"] else "no",
            )
        )
    return "\n".join(lines) + "\n"


def write_outputs(report: dict, output_dir: str) -> Path:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (out / "report.md").write_text(render_markdown(report), encoding="utf-8")
    return out


# ---------------------------------------------------------------------------
# Delete mode
# ---------------------------------------------------------------------------


def delete_resources(ec2, findings: list[Finding]) -> tuple[list, list, list]:
    """Apply each finding's suggested_action. Returns (deleted, protected, failed)."""
    deleted: list[str] = []
    protected: list[str] = []
    failed: list[tuple[str, str]] = []
    for f in findings:
        if _is_protected(f.tags):
            logger.info(
                "Skipping %s %s (Protected=true)", f.resource_type, f.resource_id
            )
            protected.append(f.resource_id)
            continue

        try:
            if f.resource_type == "ebs_volume" and f.suggested_action == "delete":
                ec2.delete_volume(VolumeId=f.resource_id)
            elif (
                f.resource_type == "ec2_instance"
                and f.suggested_action == "terminate"
            ):
                ec2.terminate_instances(InstanceIds=[f.resource_id])
            elif f.resource_type == "elastic_ip" and f.suggested_action == "release":
                ec2.release_address(AllocationId=f.resource_id)
            else:
                logger.info(
                    "Skipping %s %s (action=%s requires manual remediation)",
                    f.resource_type,
                    f.resource_id,
                    f.suggested_action,
                )
                continue
            deleted.append(f.resource_id)
            logger.info(
                "Deleted %s %s (saved ~$%.2f/month)",
                f.resource_type,
                f.resource_id,
                f.estimated_monthly_cost_usd,
            )
        except (BotoCoreError, ClientError) as exc:
            logger.error(
                "Failed to delete %s %s: %s", f.resource_type, f.resource_id, exc
            )
            failed.append((f.resource_id, str(exc)))
    return deleted, protected, failed


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="janitor",
        description="NimbusKart Cost Janitor — finds and (optionally) deletes orphaned AWS resources.",
    )
    parser.add_argument(
        "--region",
        default=os.environ.get("AWS_REGION", "us-east-1"),
        help="AWS region to scan. Default us-east-1 or $AWS_REGION.",
    )
    parser.add_argument(
        "--endpoint",
        default=os.environ.get("AWS_ENDPOINT_URL", "http://localhost:4566"),
        help=(
            "AWS endpoint URL. Default is LocalStack on localhost. "
            "Pass an empty string to target real AWS via the normal credential chain."
        ),
    )
    parser.add_argument(
        "--age-threshold",
        type=int,
        default=14,
        help="Number of days a stopped EC2 instance must have been stopped before being flagged. Default 14.",
    )
    parser.add_argument(
        "--output-dir",
        default="output",
        help="Directory to write report.json and report.md. Default ./output.",
    )

    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        help="Report only; do not delete. This is the default.",
    )
    mode.add_argument(
        "--delete",
        dest="delete",
        action="store_true",
        help="Actually delete orphaned resources. Skips anything tagged Protected=true.",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Verbose (DEBUG) logging."
    )

    args = parser.parse_args(argv)
    # If neither flag passed, default to dry-run.
    if not args.delete:
        args.dry_run = True
    return args


def build_clients(region: str, endpoint: str):
    session = boto3.session.Session(region_name=region)
    kwargs: dict = {}
    if endpoint:
        kwargs.update(
            endpoint_url=endpoint,
            aws_access_key_id="test",
            aws_secret_access_key="test",
            config=Config(retries={"max_attempts": 3}),
        )
    return session.client("ec2", **kwargs), session.client("sts", **kwargs)


def resolve_account_id(sts) -> str:
    try:
        return sts.get_caller_identity()["Account"]
    except (BotoCoreError, ClientError) as exc:
        logger.warning(
            "get_caller_identity failed (%s); falling back to 000000000000.", exc
        )
        return "000000000000"


def main(argv=None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    try:
        ec2, sts = build_clients(args.region, args.endpoint)
        account_id = resolve_account_id(sts)

        logger.info(
            "Scanning region=%s endpoint=%s mode=%s",
            args.region,
            args.endpoint or "default-aws",
            "delete" if args.delete else "dry-run",
        )
        findings = scan(ec2, args.age_threshold)
        report = build_report(findings, account_id, args.region)
        out_dir = write_outputs(report, args.output_dir)
        logger.info(
            "Wrote report to %s (%d orphans, ~$%.2f/month)",
            out_dir,
            len(findings),
            report["summary"]["estimated_monthly_waste_usd"],
        )

        if args.delete:
            deleted, protected, failed = delete_resources(ec2, findings)
            logger.info(
                "Delete summary: %d deleted, %d protected, %d failed",
                len(deleted),
                len(protected),
                len(failed),
            )
            return EXIT_OK if not failed else EXIT_RUNTIME_ERROR

        return EXIT_ORPHANS_FOUND if findings else EXIT_OK

    except (BotoCoreError, ClientError) as exc:
        logger.error("AWS API error: %s", exc)
        return EXIT_RUNTIME_ERROR


if __name__ == "__main__":
    sys.exit(main())
