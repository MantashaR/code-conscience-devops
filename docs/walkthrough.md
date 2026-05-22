# Walkthrough video

**Link:** _TBD — paste the unlisted Loom / YouTube URL here before submitting._
**Length:** target 4:30, hard limit 5:00 (per spec §6.4).
**Tool:** Loom (https://www.loom.com) — free, one-click record, gives you an
unlisted URL. Choose "Screen + cam" (camera optional; spec says talking head
not required).

---

## Before you hit record (do these once)

This is 5 minutes of doing things, not 5 minutes of waiting for things. Pre-warm
everything so the recording flows:

1. **Open three windows you'll switch between:**
   - VS Code (or your editor) with the repo open, ideally with these files in tabs:
     `terraform/main.tf`, `janitor/janitor.py`, `janitor/constants.py`,
     `samples/report.example.json`
   - A terminal at `C:\Users\Lenovo\code-conscience-devops\`
   - A browser tab on https://github.com/MantashaR/code-conscience-devops/pull/1
2. **Start Docker Desktop** (wait until the whale icon is steady, not animating).
3. **Pre-pull LocalStack so it's instant** — in the terminal, run once:
   ```
   docker pull localstack/localstack:3
   ```
4. **Pre-init Terraform** (apply will be the only slow step on camera):
   ```
   cd terraform
   terraform init
   cd ..
   ```
5. **Verify the Janitor runs locally** before recording. Open a fresh terminal:
   ```
   cd janitor
   pip install -r requirements-dev.txt
   ```
6. **Close anything sensitive** — email, Slack, screenshots. Loom captures
   everything on your screen.

---

## The script

> Read normally. Every line is sized so the timestamp lines up with what
> you're showing. Don't read it like a script — let yourself stumble; spec
> says "mistakes are fine."

### 0:00 — Intro (≈15 seconds)

> "Hi, I'm Mantasha. This is the walkthrough for the Code & Conscience DevOps
> assignment — the NimbusKart Cost Hygiene Toolkit. It's three things in one
> repo: Terraform that builds a small AWS stack on LocalStack, a Python Cost
> Janitor that finds orphan resources, and a GitHub Actions workflow that
> runs the Janitor on every PR. Let me show you it working end-to-end."

**Action:** Have the repo's `README.md` on screen at the top.

---

### 0:15 — Part 1: LocalStack + Terraform apply live (≈60 seconds)

> "First, the infrastructure layer. I'm running everything against LocalStack
> so nothing hits real AWS."

**Action:** Switch to terminal. Type and run:

```
docker run --rm -d -p 4566:4566 --name localstack -e SERVICES=ec2,s3,sts,iam localstack/localstack:3
```

> "That starts LocalStack as a Docker container. Now Terraform."

**Action:** `cd terraform/`. Open `main.tf` in the editor side-by-side.

> "The structure is split into a reusable network module — VPC, subnets,
> security group — and a root module that adds the web tier, the S3 bucket
> with versioning, and one deliberately-unattached EBS volume. That orphan
> volume is the bait for the Janitor in Part B."

**Action:** Run:

```
terraform apply -auto-approve
```

> "Notice every resource gets the four required tags — Project, Environment,
> Owner, ManagedBy=terraform — applied via a `locals` block so I don't have
> to repeat them on every resource."

**Wait for apply to finish.** Should be ~30 seconds. While waiting:

> "If LocalStack accepts everything, we'll have an orphan EBS volume sitting
> there with no instance attached. That's what the Janitor is going to catch
> next."

---

### 1:15 — Part 2: Janitor finds the orphan (≈2 minutes)

**Action:** `cd ../janitor`. Open `janitor.py` in the editor.

> "The Janitor is a single Python file with four detectors — unattached EBS
> volumes, stopped EC2 instances older than a configurable threshold,
> unassociated Elastic IPs, and resources missing required tags. Each
> detector returns `Finding` objects that match the schema the brief specifies."

**Action:** Scroll to the top of `janitor.py`, point at the `Finding` dataclass.

> "Every finding has these eight fields — the ones the spec requires by
> name plus a couple I added like `safe_to_auto_delete`."

**Action:** Run in terminal:

```
python janitor.py --dry-run --region us-east-1 --endpoint http://localhost:4566
```

> "Default mode is dry-run, which writes a report and exits 2 if any orphans
> are found — that's the exit code the GitHub Actions workflow uses to fail
> PRs. Let's look at what it produced."

**Action:** Open `output/report.json` in the editor.

> "Five fields at the top — scan_timestamp, account, region, summary, and
> findings. The summary shows total_orphans and estimated_monthly_waste_usd.
> The findings array has one entry: our orphan EBS volume."

**Action:** Point at the orphan finding in the JSON.

> "Reason is 'unattached' because `describe_volumes` filtered for status
> 'available'. age_days comes from the volume's create time. The cost
> estimate is size in GB times the EBS gp3 monthly price from `constants.py`,
> with the source cited inline. `safe_to_auto_delete` is true because the
> volume has all four required tags and no Protected tag."

**Action:** Briefly flip to `constants.py` and point at `EBS_GP3_USD_PER_GB_MONTH`.

> "If this same volume had been missing the Owner tag, `safe_to_auto_delete`
> would have come back false — the Janitor refuses to delete anything it
> can't attribute."

---

### 3:15 — Part 3: One design decision I'm proud of (≈60 seconds)

**Action:** In `janitor.py`, jump to the `_deduplicate` function.

> "The thing I'm most proud of is this — the deduplication."

**Action:** Highlight the function.

> "A single resource can hit more than one detector. An unattached EBS volume
> that's also missing required tags would naively appear in the report twice
> — once with reason 'unattached', once with 'missing_required_tags'. That
> would double the `total_orphans` count and confuse the cost number."

> "`_deduplicate` walks the findings, keyed by `(resource_id, resource_type)`.
> When it sees a duplicate, it merges them: concatenates the reasons,
> keeps the higher cost estimate so we don't double-count waste, and ANDs
> the `safe_to_auto_delete` flags so any unsafe finding poisons the merged
> result."

> "This way the summary number stays honest, even when detectors overlap."

---

### 4:15 — Part 4: One thing I would change (≈30 seconds)

**Action:** Still in `janitor.py`, point at the `safe_to_auto_delete` field on `Finding`.

> "The thing I'd change is `safe_to_auto_delete`. Right now it's a boolean,
> which collapses two different things — 'definitely safe' and 'safe but
> still wants human sign-off' — into the same value. I'd make it a confidence
> enum: 'auto_safe', 'needs_review', 'never_auto'. Then `--delete` mode
> could have an `--auto-safe-only` flag for the green-light cases, and
> 'needs_review' findings would go to a separate notification flow instead
> of being silently skipped."

---

### 4:45 — Outro (≈15 seconds)

> "That's it. The full PR is live on GitHub at MantashaR/code-conscience-devops,
> CI runs on every PR and posts the orphan report as a sticky comment, and
> the DESIGN.md walks through what would change at production scale. Thanks
> for watching."

**Action:** Hit stop. Copy the Loom URL.

---

## After recording

1. Paste the Loom URL into the `**Link:**` line at the top of this file.
2. Paste the same URL into `SUBMISSION.md` under `## Walkthrough video`.
3. Tick the last checkbox in `SUBMISSION.md`.
4. Push: `git add docs/walkthrough.md SUBMISSION.md && git commit -m "docs: add walkthrough video link" && git push`.
5. Send the recruiter email — subject `[DevOps Assignment] Mantasha R`, body
   with the repo URL and the video URL.

---

## If they ask in a follow-up interview

Three likely questions and short answers:

- **"Walk me through what happens when the Janitor sees a Protected volume in --delete mode."**
  → `_is_protected` returns true → `delete_resources` skips it, logs the skip,
  appends to the `protected` list. The volume is still in the report's `findings`
  array with `safe_to_auto_delete=false`. Code lives at `janitor.py:351`.

- **"Why did you change the SSH default from 0.0.0.0/0 to RFC1918?"**
  → The spec said to flag unsafe defaults under "Decisions & deviations" (§3.3
  + the FAQ). Exposing port 22 to the whole internet is one of the top causes
  of compromised EC2 instances. The variable is still configurable, so a
  caller who really wants the wide-open default can override it explicitly.

- **"Why is the lifecycle config gated behind a variable?"**
  → The AWS provider 5.x runs a consistency-check wait after
  `PutBucketLifecycleConfiguration` — it polls `GetBucketLifecycleConfiguration`
  until the response matches what was just put. LocalStack 3 doesn't return a
  matching read, so the provider times out after 3 minutes. CI passes
  `-var="enable_lifecycle=false"`; production deployments leave the default
  `true`. Documented in `terraform/variables.tf` and README "Decisions &
  deviations".
