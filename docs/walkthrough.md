# Walkthrough video

**Link:** _TBD — paste the unlisted YouTube / Loom URL here before submitting._
**Length:** max 5 minutes (per spec §6.4).
**Recording status:** TBD.

## What the video covers

Per the spec, the walkthrough demonstrates four things, in order:

1. **LocalStack + Terraform live.** Start LocalStack with the same command
   from `README.md`, then `tflocal apply -auto-approve` against the
   `terraform/` directory. Show the orphan EBS volume in the apply summary.
2. **Janitor run + one finding walked end-to-end.** Run
   `python janitor.py --dry-run`, open `output/report.json`, and walk through
   the orphan EBS volume's record: how `reason="unattached"` came out of the
   `describe_volumes` filter, how the $cost was calculated from
   `constants.py`, why `safe_to_auto_delete` is `true` for this one
   (fully tagged, not Protected, low-risk resource type).
3. **One design decision I'm proud of.** The dedup logic in
   `_deduplicate()` in `janitor.py`. The naïve version emits two findings
   for a resource that's both unattached *and* untagged; mine collapses them
   into one row with both reasons and the larger cost estimate. Worth
   showing because it keeps `summary.total_orphans` honest.
4. **One thing I would change.** The `safe_to_auto_delete` field is currently
   binary; it should be a confidence enum (`safe`, `needs_review`,
   `never_auto`) so the `--delete` flow can have a `--auto-safe-only` mode
   that takes only the green-light cases. Today's binary collapses
   "definitely fine" and "fine with a tag" together.

## Transcript / talking points

_(Add a short bulleted transcript here after recording — it lets the
reviewer skim and helps if the audio is unclear.)_
