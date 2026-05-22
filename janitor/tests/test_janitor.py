"""Unit tests for the Cost Janitor.

Uses moto to mock the AWS APIs at the boto3 layer. These tests intentionally
do NOT depend on LocalStack — they should run anywhere Python and pip do.
"""

import json

import boto3
import pytest
from moto import mock_aws

from janitor import (
    Finding,
    build_report,
    delete_resources,
    detect_stopped_instances,
    detect_unassociated_eips,
    detect_unattached_volumes,
    detect_untagged_resources,
    main,
    render_markdown,
    scan,
)

REGION = "us-east-1"


def _fully_tagged():
    return [
        {"Key": "Project", "Value": "nimbuskart"},
        {"Key": "Environment", "Value": "staging"},
        {"Key": "Owner", "Value": "platform-team"},
        {"Key": "ManagedBy", "Value": "terraform"},
    ]


# ---------------------------------------------------------------------------
# Detector tests
# ---------------------------------------------------------------------------


@mock_aws
def test_detect_unattached_volume_with_full_tags_is_auto_safe():
    ec2 = boto3.client("ec2", region_name=REGION)
    vol = ec2.create_volume(
        AvailabilityZone="us-east-1a",
        Size=30,
        VolumeType="gp3",
        TagSpecifications=[{"ResourceType": "volume", "Tags": _fully_tagged()}],
    )
    findings = detect_unattached_volumes(ec2)
    assert len(findings) == 1
    f = findings[0]
    assert f.resource_id == vol["VolumeId"]
    assert f.resource_type == "ebs_volume"
    assert f.reason == "unattached"
    assert f.estimated_monthly_cost_usd == pytest.approx(30 * 0.08, abs=0.01)
    assert f.safe_to_auto_delete is True
    assert f.suggested_action == "delete"


@mock_aws
def test_detect_unattached_volume_missing_tags_is_not_auto_safe():
    ec2 = boto3.client("ec2", region_name=REGION)
    ec2.create_volume(AvailabilityZone="us-east-1a", Size=10, VolumeType="gp3")
    findings = detect_unattached_volumes(ec2)
    assert len(findings) == 1
    assert findings[0].safe_to_auto_delete is False


@mock_aws
def test_detect_unassociated_eip():
    ec2 = boto3.client("ec2", region_name=REGION)
    ec2.allocate_address(
        Domain="vpc",
        TagSpecifications=[{"ResourceType": "elastic-ip", "Tags": _fully_tagged()}],
    )
    findings = detect_unassociated_eips(ec2)
    assert len(findings) == 1
    assert findings[0].resource_type == "elastic_ip"
    assert findings[0].reason == "unassociated"
    assert findings[0].safe_to_auto_delete is True


@mock_aws
def test_detect_associated_eip_is_skipped():
    ec2 = boto3.client("ec2", region_name=REGION)
    vpc = ec2.create_vpc(CidrBlock="10.0.0.0/16")
    subnet = ec2.create_subnet(VpcId=vpc["Vpc"]["VpcId"], CidrBlock="10.0.1.0/24")
    inst = ec2.run_instances(
        ImageId="ami-12345678",
        MinCount=1,
        MaxCount=1,
        SubnetId=subnet["Subnet"]["SubnetId"],
        InstanceType="t3.micro",
    )
    iid = inst["Instances"][0]["InstanceId"]
    addr = ec2.allocate_address(Domain="vpc")
    ec2.associate_address(AllocationId=addr["AllocationId"], InstanceId=iid)
    findings = detect_unassociated_eips(ec2)
    assert findings == []


@mock_aws
def test_detect_stopped_instance_with_zero_age_threshold():
    ec2 = boto3.client("ec2", region_name=REGION)
    vpc = ec2.create_vpc(CidrBlock="10.0.0.0/16")
    subnet = ec2.create_subnet(VpcId=vpc["Vpc"]["VpcId"], CidrBlock="10.0.1.0/24")
    inst = ec2.run_instances(
        ImageId="ami-12345678",
        MinCount=1,
        MaxCount=1,
        SubnetId=subnet["Subnet"]["SubnetId"],
        InstanceType="t3.micro",
        TagSpecifications=[
            {"ResourceType": "instance", "Tags": _fully_tagged()}
        ],
    )
    iid = inst["Instances"][0]["InstanceId"]
    ec2.stop_instances(InstanceIds=[iid])

    findings = detect_stopped_instances(ec2, age_threshold_days=0)
    assert len(findings) == 1
    f = findings[0]
    assert f.resource_id == iid
    assert f.resource_type == "ec2_instance"
    assert f.reason == "stopped_too_long"
    # Termination is destructive; never auto-safe even with full tags.
    assert f.safe_to_auto_delete is False
    assert f.suggested_action == "terminate"


@mock_aws
def test_stopped_instance_below_threshold_is_skipped():
    ec2 = boto3.client("ec2", region_name=REGION)
    vpc = ec2.create_vpc(CidrBlock="10.0.0.0/16")
    subnet = ec2.create_subnet(VpcId=vpc["Vpc"]["VpcId"], CidrBlock="10.0.1.0/24")
    inst = ec2.run_instances(
        ImageId="ami-12345678", MinCount=1, MaxCount=1,
        SubnetId=subnet["Subnet"]["SubnetId"], InstanceType="t3.micro",
    )
    ec2.stop_instances(InstanceIds=[inst["Instances"][0]["InstanceId"]])
    findings = detect_stopped_instances(ec2, age_threshold_days=365)
    assert findings == []


@mock_aws
def test_detect_untagged_volume_lists_missing_keys():
    ec2 = boto3.client("ec2", region_name=REGION)
    ec2.create_volume(AvailabilityZone="us-east-1a", Size=10, VolumeType="gp3")
    findings = detect_untagged_resources(ec2)
    assert len(findings) == 1
    f = findings[0]
    assert f.resource_type == "ebs_volume"
    assert f.reason.startswith("missing_required_tags:")
    for required in ("Project", "Environment", "Owner"):
        assert required in f.reason
        assert f.tags[required] is None


# ---------------------------------------------------------------------------
# Delete-mode safety
# ---------------------------------------------------------------------------


@mock_aws
def test_protected_volume_is_skipped_in_delete_mode():
    ec2 = boto3.client("ec2", region_name=REGION)
    protected_tags = _fully_tagged() + [{"Key": "Protected", "Value": "true"}]
    protected = ec2.create_volume(
        AvailabilityZone="us-east-1a", Size=10, VolumeType="gp3",
        TagSpecifications=[{"ResourceType": "volume", "Tags": protected_tags}],
    )
    normal = ec2.create_volume(
        AvailabilityZone="us-east-1a", Size=10, VolumeType="gp3",
        TagSpecifications=[{"ResourceType": "volume", "Tags": _fully_tagged()}],
    )

    findings = detect_unattached_volumes(ec2)
    deleted, prot, failed = delete_resources(ec2, findings)

    assert protected["VolumeId"] in prot
    assert normal["VolumeId"] in deleted
    assert failed == []

    remaining = {v["VolumeId"] for v in ec2.describe_volumes()["Volumes"]}
    assert protected["VolumeId"] in remaining
    assert normal["VolumeId"] not in remaining


# ---------------------------------------------------------------------------
# main() exit codes + report schema
# ---------------------------------------------------------------------------


@mock_aws
def test_main_exits_2_when_orphans_in_dry_run(tmp_path):
    ec2 = boto3.client("ec2", region_name=REGION)
    ec2.create_volume(
        AvailabilityZone="us-east-1a", Size=10, VolumeType="gp3",
        TagSpecifications=[{"ResourceType": "volume", "Tags": _fully_tagged()}],
    )
    code = main([
        "--region", REGION,
        "--endpoint", "",
        "--output-dir", str(tmp_path),
        "--dry-run",
    ])
    assert code == 2


@mock_aws
def test_main_exits_0_when_clean(tmp_path):
    code = main([
        "--region", REGION,
        "--endpoint", "",
        "--output-dir", str(tmp_path),
        "--dry-run",
    ])
    assert code == 0


@mock_aws
def test_report_json_matches_schema(tmp_path):
    ec2 = boto3.client("ec2", region_name=REGION)
    ec2.create_volume(AvailabilityZone="us-east-1a", Size=10, VolumeType="gp3")
    main(["--region", REGION, "--endpoint", "", "--output-dir", str(tmp_path)])

    data = json.loads((tmp_path / "report.json").read_text())
    for top in ("scan_timestamp", "account_id", "region", "summary", "findings"):
        assert top in data, f"missing top-level key {top}"
    for k in ("total_orphans", "estimated_monthly_waste_usd"):
        assert k in data["summary"]
    assert isinstance(data["findings"], list)
    for finding in data["findings"]:
        for key in (
            "resource_id",
            "resource_type",
            "reason",
            "age_days",
            "estimated_monthly_cost_usd",
            "tags",
            "suggested_action",
            "safe_to_auto_delete",
        ):
            assert key in finding, f"finding missing {key}"


@mock_aws
def test_dedup_when_resource_hits_multiple_detectors(tmp_path):
    """A volume that's both unattached AND missing tags should appear once,
    with both reasons combined."""
    ec2 = boto3.client("ec2", region_name=REGION)
    ec2.create_volume(AvailabilityZone="us-east-1a", Size=10, VolumeType="gp3")
    findings = scan(ec2, age_threshold_days=14)
    volume_findings = [f for f in findings if f.resource_type == "ebs_volume"]
    assert len(volume_findings) == 1
    assert "unattached" in volume_findings[0].reason
    assert "missing_required_tags" in volume_findings[0].reason


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def test_render_markdown_empty():
    report = {
        "scan_timestamp": "2026-01-15T10:00:00Z",
        "account_id": "000000000000",
        "region": "us-east-1",
        "summary": {"total_orphans": 0, "estimated_monthly_waste_usd": 0.0},
        "findings": [],
    }
    md = render_markdown(report)
    assert "No orphans found" in md
    assert "Total orphans" in md


def test_render_markdown_with_findings():
    report = {
        "scan_timestamp": "2026-01-15T10:00:00Z",
        "account_id": "000000000000",
        "region": "us-east-1",
        "summary": {"total_orphans": 1, "estimated_monthly_waste_usd": 8.0},
        "findings": [
            {
                "resource_id": "vol-abc",
                "resource_type": "ebs_volume",
                "reason": "unattached",
                "age_days": 21,
                "estimated_monthly_cost_usd": 8.0,
                "tags": {},
                "suggested_action": "delete",
                "safe_to_auto_delete": False,
            }
        ],
    }
    md = render_markdown(report)
    assert "vol-abc" in md
    assert "unattached" in md
    assert "$8.00" in md
