# Cost Janitor — Orphan Scan Report

- **Scan timestamp:** `2026-05-22T09:31:00Z`
- **Account:** `000000000000`
- **Region:** `us-east-1`
- **Total orphans:** **5**
- **Estimated monthly waste:** **$28.24**

| Resource | Type | Reason | Age (days) | Monthly $ | Suggested action | Auto-safe |
|---|---|---|---|---|---|---|
| `vol-0a9c8f7e6d5b4a3c2` | ebs_volume | unattached | 47 | $16.00 | delete | yes |
| `vol-1f2e3d4c5b6a7980f` | ebs_volume | unattached;missing_required_tags:Owner | 113 | $8.00 | delete | no |
| `i-0123456789abcdef0` | ec2_instance | stopped_too_long | 32 | $0.64 | terminate | no |
| `eipalloc-0a1b2c3d4e5f6a7b8` | elastic_ip | unassociated | n/a | $3.60 | release | no |
| `vol-0deadbeefdeadbeef` | ebs_volume | missing_required_tags:Project,Owner | n/a | $0.00 | tag | no |
