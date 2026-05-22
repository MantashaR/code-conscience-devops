# NimbusKart Cost Hygiene Toolkit

> Code & Conscience — DevOps Engineer Practical Assignment
> Multi-Cloud Cost Hygiene & Automation Challenge

## Overview

NimbusKart, a fictional e-commerce startup, watched its AWS bill grow from
~$400 to ~$2,100 per month over a quarter. Most of the bleed was suspected to be
orphaned cloud resources — unattached volumes, stopped EC2 instances, idle
Elastic IPs, untagged dev experiments. This repository is the foundation that
lets the team **find**, **fix**, and **prevent** that waste, end-to-end on a
laptop.

It contains:

1. **Terraform** infrastructure that provisions NimbusKart's staging environment
   on LocalStack — including one deliberately orphaned EBS volume that the
   Janitor is expected to catch.
2. **Cost Janitor**, a Python CLI that scans AWS (or a LocalStack emulation of
   it), produces a structured report of waste, and supports a safe
   `--dry-run` / `--delete` workflow with a `Protected=true` tag escape hatch.
3. A **GitHub Actions** workflow that wires the Janitor into every PR so cost
   regressions are caught at review time, not on the monthly bill.
4. A **design note** (`DESIGN.md`) on how the same scaffolding scales to
   multi-cloud, multi-account, production-grade FinOps.

## How to run locally

```bash
git clone <this-repo-url> code-conscience-devops
cd code-conscience-devops

# 1. Start LocalStack
docker run --rm -d -p 4566:4566 --name localstack localstack/localstack:3

# 2. Apply Terraform (uses the tflocal wrapper to point at LocalStack)
pip install terraform-local
cd terraform
tflocal init
tflocal apply -auto-approve
cd ..

# 3. Install + run the Janitor in dry-run mode
cd janitor
pip install -r requirements.txt
python janitor.py --dry-run --region us-east-1 --endpoint http://localhost:4566
# -> writes report.json and report.md to ./output/

# 4. (Optional) Run unit tests
pytest tests/
```

Exit codes for the Janitor:

- `0` — no orphans found
- `2` — orphans found in `--dry-run` mode (CI will fail the PR)
- `1` — runtime error

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
|   |  (Python CLI)    | -----> |   (region + EP)  |                 |
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
|                              PR comment if orphans found           |
+--------------------------------------------------------------------+
```

## Decisions & deviations

> _Populated as each part is built. Final list lives at the bottom of this
> file._

- TBD

## Trade-offs

> _What I'd do with one more week — populated at the end._

- TBD

## AI usage disclosure

> _Populated honestly at the end._

- TBD
