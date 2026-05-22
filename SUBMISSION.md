# Submission — DevOps Engineer Assignment

**Candidate name:** Mantasha R
**Email:** mantashafroze@gmail.com
**Date submitted:** TBD (fill in on the day you send the email)
**Hours spent (approximate):** TBD

## Deliverables checklist
- [x] Part A: Terraform code under /terraform applies cleanly on LocalStack
- [x] Part A: `terraform validate` and `terraform fmt -check` both pass
- [x] Part B: Janitor script runs in --dry-run mode and produces report.json
- [x] Part B: GitHub Actions workflow runs green on a fresh PR
- [x] Part B: --delete mode respects Protected=true tag
- [x] Part C: DESIGN.md is present and within 2 pages
- [ ] Walkthrough video link below is accessible (unlisted is fine)

## Walkthrough video
Link (Loom / YouTube unlisted / Google Drive): _TBD_
Length: max 5 minutes

## Sample report
Path to a sample report.json produced by your script: `samples/report.example.json`

## Known limitations
(bullet list — be honest)
- The Janitor's scope is intentionally EC2 / EBS / Elastic IP only. Snapshots,
  NAT gateways, idle ALBs, unused IAM roles, and RDS resources are not
  detected. The four orphan types in the spec are all covered.
- `safe_to_auto_delete` is binary; a confidence enum would be more useful for
  the future `--auto-safe-only` flag (see walkthrough video, "what I'd
  change").
- Pricing is a small static constants table cited from the AWS pricing pages
  on 2026-05-22 — the right production answer is the AWS Pricing API
  refreshed daily.
- Multi-account fan-out (sts:AssumeRole over `organizations:ListAccounts`)
  and GCP/Azure detectors are sketched in `DESIGN.md` but not implemented.
- No integration test that exercises the full Janitor against LocalStack
  inside `pytest`; the GitHub Actions workflow is the only place the
  LocalStack path is end-to-end tested. Unit tests use moto.

## AI usage disclosure
See the `## AI usage disclosure` section of `README.md` for the full version.
Short version: I used AI as a pair-programmer for scaffolding, reviewed and
reshaped the output before each commit, rejected one over-broad IAM policy
suggestion, and worked through the dedup and state-transition parsing logic
by hand. The spec asks for judgment about AI, not abstinence — that's what
this submission tries to show.
