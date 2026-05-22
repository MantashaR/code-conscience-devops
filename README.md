# NimbusKart Cost Hygiene Toolkit

> Code & Conscience — DevOps Engineer Practical Assignment
> Multi-Cloud Cost Hygiene & Automation Challenge

## Overview

NimbusKart, a fictional e-commerce startup, watched its AWS bill grow from
~$400 to ~$2,100 per month over a quarter. Most of the bleed was suspected to
be orphaned cloud resources — unattached volumes, stopped EC2 instances, idle
Elastic IPs, untagged dev experiments. This repository is the foundation that
lets the team **find**, **fix**, and **prevent** that waste, end-to-end on a
laptop.

It contains:

1. **Terraform** infrastructure that provisions NimbusKart's staging
   environment on LocalStack — including one deliberately orphaned EBS volume
   that the Janitor is expected to catch.
2. **Cost Janitor**, a Python CLI that scans AWS (or a LocalStack emulation
   of it), produces a structured report of waste, and supports a safe
   `--dry-run` / `--delete` workflow with a `Protected=true` tag escape hatch.
3. A **GitHub Actions** workflow that wires the Janitor into every PR so cost
   regressions are caught at review time, not on the monthly bill.
4. A **design note** (`DESIGN.md`) on how the same scaffolding scales to
   multi-cloud, multi-account, production-grade FinOps.

## How to run locally

Requires Docker, Terraform ≥ 1.5, and Python ≥ 3.10.

```bash
git clone https://github.com/MantashaR/code-conscience-devops.git
cd code-conscience-devops

# 1. Start LocalStack
docker run --rm -d -p 4566:4566 --name localstack \
  -e SERVICES=ec2,s3,sts,iam localstack/localstack:3

# 2. Apply Terraform via the tflocal wrapper (it sets LocalStack endpoints)
pip install terraform-local
cd terraform
tflocal init
tflocal apply -auto-approve
cd ..

# 3. Install the Janitor and run it in dry-run mode
cd janitor
pip install -r requirements.txt
python janitor.py --dry-run --region us-east-1 --endpoint http://localhost:4566
# Outputs: ./output/report.json and ./output/report.md
# Exit code: 2 (orphans found), 0 (clean), 1 (runtime error)

# 4. Run the unit tests
pip install -r requirements-dev.txt
pytest tests/ -v

# 5. (When you're done) tear down LocalStack
docker stop localstack
```

To target a real AWS account instead of LocalStack:

```bash
python janitor.py --dry-run --endpoint ""        # uses the normal AWS credential chain
```

## Architecture

```
+--------------------------------------------------------------------+
|                          DEVELOPER LAPTOP                          |
|                                                                    |
|   +------------------+        +---------------------------+        |
|   |  Terraform (HCL) | -----> |        LocalStack         |        |
|   |  + tflocal       |        |  (AWS APIs in a container)|        |
|   +------------------+        +---------------------------+        |
|                                       ^         ^                  |
|                                       |         |                  |
|                                       |         |                  |
|   +------------------+        +------------------+                 |
|   |  Cost Janitor    | <----- |   boto3 client   |                 |
|   |  (Python CLI)    | -----> |  (region + URL)  |                 |
|   +------------------+        +------------------+                 |
|         |                                                          |
|         |  report.json + report.md                                 |
|         v                                                          |
|   +------------------+                                             |
|   |  ./output/       |                                             |
|   +------------------+                                             |
|                                                                    |
+--------------------------------------------------------------------+
                              |
                              |  on every PR
                              v
+--------------------------------------------------------------------+
|                       GITHUB ACTIONS RUNNER                        |
|                                                                    |
|  LocalStack svc --> terraform apply --> janitor --dry-run          |
|                                              |                     |
|                                              v                     |
|                              report.json + report.md (artifacts)   |
|                                              |                     |
|                                              v                     |
|                          sticky PR comment if orphans found        |
+--------------------------------------------------------------------+
```

## Decisions & deviations

- **SSH (TCP/22) default CIDR changed from `0.0.0.0/0` to `10.0.0.0/8`.** The
  spec asked for the wide-open default and explicitly told me to flag it
  (§3.3 + FAQ). Exposing SSH to the whole internet is one of the top causes
  of compromised instances; the variable is still configurable.
- **HTTP (TCP/80) is left open to `0.0.0.0/0` per spec, but flagged.** A real
  production setup should terminate TLS at an ALB and have port 80 redirect
  to 443. Encoded as a security-group description comment, not a code change,
  because the spec was explicit.
- **EC2 AMI is hardcoded.** LocalStack does not validate AMI IDs; for real AWS
  the right pattern is a `data "aws_ssm_parameter"` lookup for the latest
  Amazon Linux 2023 AMI. Left out of v0 because the SSM endpoint surface
  differs between LocalStack and AWS and I wanted `terraform apply` to be
  identical in both.
- **No SSH key pair attached to the EC2 instances.** The spec did not ask
  for one. In production I would mandate SSM Session Manager and disable
  inbound SSH entirely.
- **`safe_to_auto_delete` is `false` for every EC2 finding**, even when fully
  tagged and not Protected. Terminating an instance is irreversible (root EBS
  is gone) so it always needs human eyes. Documented in `janitor.py`.
- **Janitor exit codes are tri-state**: `0` clean, `2` orphans-in-dry-run,
  `1` runtime error. The spec said "non-zero" — I picked `2` rather than `1`
  so CI can distinguish "found orphans" (expected, actionable) from
  "the script crashed" (a different problem, different paging behaviour).
- **Findings are deduplicated**. A resource that's both `unattached` AND
  missing required tags would otherwise appear twice and inflate
  `total_orphans`. I merge them into a single finding with a combined reason
  and keep the higher cost estimate.
- **Untagged findings contribute `$0` to `estimated_monthly_waste_usd`.**
  Missing tags is a *cost-attribution* problem, not a direct $ cost. Counting
  them as $0 keeps the headline waste number trustworthy while still surfacing
  the hygiene issue.
- **AWS provider is parametrised on `var.localstack_endpoint`.** Default is
  `http://localhost:4566` (LocalStack); setting it to `""` flips the same
  Terraform onto a real AWS account via the normal credential chain. Spec was
  LocalStack-only but the cost of supporting both was almost zero.
- **Static pricing constants in `janitor/constants.py`** with sources cited
  inline. The right production answer is the AWS Pricing API refreshed daily;
  that's deferred and listed under Trade-offs.
- **S3 bucket name is `nimbuskart-app-logs-<environment>`** (a deviation from
  the spec which didn't name it). Predictable, environment-scoped, no random
  suffix — fine for a single-account staging stack, would need a hash suffix
  the day this code lands in production.
- **`untagged_resources` detector scope is EC2 / EBS / EIPs only**, mirroring
  the orphan detectors. ELBs, RDS, IAM, and other resources are explicitly
  out of v0 and listed under Trade-offs.

## Trade-offs

What I would do with one more week:

- **Multi-account fan-out.** `sts:AssumeRole` against every member of
  `organizations:ListAccounts`, with the same JSON schema across accounts.
- **Soaking window for `--delete` mode.** Flagged resources receive a
  `JanitorPendingDeletion=<ISO date>` tag and are not deleted until the date
  elapses on a subsequent scan. Gives owners a documented chance to intervene.
- **CloudTrail "recently used" check** before reporting an EBS volume as
  orphan, to catch the "attached weekly by a Lambda" case described in
  `DESIGN.md`.
- **More detectors:** orphaned snapshots, idle NAT gateways, ALBs with zero
  target groups, unused IAM roles, RDS snapshots.
- **GCP detectors.** Module seams are sketched in `DESIGN.md` §1; the actual
  `google-cloud-compute` integration is not yet written.
- **Pricing from the AWS Pricing API** refreshed daily into the constants file
  (or replace the constants file entirely with a runtime lookup table).
- **EventBridge-triggered Lambda runner** with the five CloudWatch metrics
  from `DESIGN.md` §4. The CI-on-PR path stays as the developer-feedback loop;
  Lambda becomes the daily steady-state scan.
- **Integration test against LocalStack inside the Janitor's own pytest suite**
  (not just the GHA workflow). Today the unit tests use moto and the GHA
  workflow tests the full path; a third layer would catch driver/SDK quirks.
- **Slack notification step in the GHA workflow** (gated on a repo variable
  so forks don't break) for org-wide visibility on top of PR comments.

## AI usage disclosure

- **How I used AI.** Claude as a pair-programmer for scaffolding —
  the Terraform module skeleton, the Cost Janitor's CLI shape and detector
  signatures, an initial pass at the moto-based tests, and the YAML for the
  GitHub Actions workflow. Faster than a blank-page start; every block was
  reviewed and several were rewritten before commit.
- **One suggestion I rejected.** An early draft of the read-only IAM policy
  in `DESIGN.md` included S3 actions the Janitor never calls. I tightened it
  to exactly the `Describe*` set plus `sts:GetCallerIdentity` and
  `cloudwatch:PutMetricData` that the script actually exercises, because a
  policy any wider than the script's API surface is a future incident.
- **One section I worked through by hand.** The `_parse_state_transition_time`
  helper and the `_deduplicate` logic in `janitor.py`. Both have edge cases
  that affect correctness — moto's `StateTransitionReason` format doesn't
  match real AWS's, and dedup must combine reasons without double-counting
  cost — so I wanted to be the person who understood every line, not just
  accept generated code. The age parser defensively falls back to
  `LaunchTime` so the detector behaves the same on both backends.
