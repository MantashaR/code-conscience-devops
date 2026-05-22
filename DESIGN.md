# Design note — productionising the NimbusKart Cost Janitor

This note covers the gap between "demo that runs on a laptop" and "thing FinOps
relies on across a real multi-cloud estate". Five sections, in priority order.

## 1. Multi-cloud reality

The Janitor as shipped is single-cloud only. For GCP next quarter (and Azure
after) the goal is to add cloud plugins, not rewrite the detector logic.

**Module boundaries I'd cut along:**

```
janitor/
├── core/
│   ├── schema.py        # Finding dataclass + report JSON/MD writers
│   ├── orchestrator.py  # for each enabled provider: collect & merge findings
│   ├── safety.py        # Protected-tag/-label normalisation, age helpers
│   └── pricing.py       # per-cloud pricing tables (already started)
├── providers/
│   ├── aws/             # boto3 backends — current janitor.py moves here
│   ├── gcp/             # google-cloud-compute, google-cloud-billing
│   └── azure/           # azure-mgmt-compute, azure-mgmt-resource
└── cli.py               # --provider aws,gcp; --account/--project/--subscription
```

**What stays cloud-agnostic:** the `Finding` schema, the deduplication and
safety rules (`safe_to_auto_delete`, `Protected` tag handling), the
JSON/Markdown writers, the `--dry-run`/`--delete` contract, and the
`age_threshold` semantics. These are *policy*, not API surface.

**What's cloud-specific:** identity (account_id vs project_id vs
subscription_id), the tagging metaphor (AWS tags vs GCP labels — labels are
lowercase-only — vs Azure tags), the actual `describe_*` / `list_*` / `delete`
API calls, and pricing tables. Each provider plugin implements one
`scan() -> list[Finding]` and one `delete(finding) -> None` interface; the
orchestrator does not care which cloud the finding came from.

**The trade-off I'd accept:** a thin abstraction (provider plugins return
`Finding` directly) over a thick one (an internal IR that each provider maps
into). The former is faster to add a cloud to; the latter helps later if we
build queries like "all orphans across all clouds tagged team=x", which I'd
defer until we have the second cloud in production.

## 2. Permissions

**Minimal read-only policy for `--dry-run` mode (the daily Lambda case):**

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "JanitorReadOnly",
      "Effect": "Allow",
      "Action": [
        "ec2:DescribeVolumes",
        "ec2:DescribeInstances",
        "ec2:DescribeAddresses",
        "ec2:DescribeSnapshots",
        "ec2:DescribeNatGateways",
        "ec2:DescribeNetworkInterfaces",
        "sts:GetCallerIdentity",
        "cloudwatch:PutMetricData"
      ],
      "Resource": "*"
    }
  ]
}
```

`PutMetricData` is in the read-only policy because the Janitor must publish
its own observability metrics (Section 4) even when it isn't allowed to delete
anything. Everything else is `Describe*` — no list-buckets, no IAM reads.

**Additional permissions for `--delete` mode** are attached to a *separate*
role, never to the daily-scan role:

- `ec2:DeleteVolume`, `ec2:TerminateInstances`, `ec2:ReleaseAddress`
- `ec2:CreateTags` (so the Janitor can mark resources `JanitorPendingDeletion`
  during the soaking window — see §3)

…each scoped via an IAM condition `aws:ResourceTag/ManagedBy: terraform` so
the Janitor cannot, by construction, delete anything it didn't see provisioned
through IaC.

## 3. Safety net — two failure modes I lose sleep over

**(a) The "stopped for a sprint" instance.** A dev stops an EC2 instance to
test failover, goes on holiday, the 14-day threshold fires while they're away,
the instance is terminated, the root volume is gone, work is lost.

> *Guardrail:* never auto-terminate EC2 (already encoded —
> `safe_to_auto_delete=False` for `ec2_instance` in `janitor.py`). In
> `--delete` mode, EC2 findings should instead receive a
> `JanitorPendingDeletion=<date+7>` tag and a Slack ping to the resource's
> `Owner`; only after the date elapses (and the tag survives a second scan)
> does the Janitor terminate. The soaking window converts a single irreversible
> action into a multi-day notification flow that a human can interrupt.

**(b) The "unattached but loved" volume.** An EBS volume is attached on demand
each Sunday by a Lambda for a weekly batch job. The Janitor scans on a
Saturday, sees it unattached, deletes it. Sunday's job fails.

> *Guardrail:* `safe_to_auto_delete=true` already requires all four required
> tags. On top of that, the Janitor should issue a CloudTrail
> `LookupEvents` call for `AttachVolume` against the volume in the last 30
> days — any hit downgrades the finding to "manual review" with a reason
> string like `recently_attached`. The cost is two extra API calls per
> orphan; the benefit is that "infrequently used but real" volumes stop
> getting deleted by accident.

## 4. Observability

All metrics in a CloudWatch namespace `NimbusKart/CostJanitor`. Five metrics:

| Metric | Source | Alert threshold |
|---|---|---|
| `JanitorRunsFailed` (count) | Lambda exit ≠ 0 AND ≠ "orphans found" | > 0 in 1h → page oncall |
| `OrphanCount` (gauge) | `report.json` `summary.total_orphans` | > 50 sustained 7d → Slack `#finops` |
| `EstimatedMonthlyWasteUSD` (gauge) | `report.json` `summary.estimated_monthly_waste_usd` | > $500 sustained 7d → Slack `#finops` |
| `TimeSinceLastScan` (seconds) | EventBridge schedule heartbeat | > 48h → page oncall (the scanner stopped) |
| `DeletionFailures` (count) | `--delete` mode error log | > 0 in any run → quarantine account, manual review |

`TimeSinceLastScan` matters more than people expect: a Janitor that quietly
fails to run for a month is worse than one that runs and finds problems,
because no-one notices until the bill arrives.

## 5. What I deliberately did not build

This v0 leaves out several things on purpose. The Janitor only runs in CI on
PRs and on push to `main`; the production equivalent would be an EventBridge-
triggered Lambda with the metrics above, running daily across all accounts
discovered via `organizations:ListAccounts`. I did not implement the soaking-
window mechanism from §3, the cross-account assume-role pattern, the GCP or
Azure detectors (only their seams), the CloudTrail "recently used" check, or
detectors for snapshots, NAT gateways, idle load balancers, or unused IAM
roles. Pricing uses a small static table cited in `constants.py`; production
would pull daily from the AWS Pricing API and refresh the table. Notification
beyond the PR comment (Slack, PagerDuty) is not wired up — production scoping
decision: integrate with NimbusKart's existing oncall tooling rather than
build a parallel one.
