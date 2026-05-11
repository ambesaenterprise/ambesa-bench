# Scenario 04 — recency miss on empty source table

## What's broken

`raw_orders.csv` has only the header row — zero data rows. dbt seed
loads the empty table cleanly, and `stg_orders` runs to completion (the
model just produces a zero-row relation). The breakage surfaces at the
test phase: a custom recency test (`tests/recency_raw_orders.sql`)
correctly fails because `MAX(order_date)` on an empty table is `NULL`,
and the test's `WHERE most_recent < threshold OR most_recent IS NULL`
clause catches that case.

## Why this scenario exists

This is the **first `public_incident_replay` scenario** — it reproduces
the post-fix shape of [dbt-labs/dbt-utils PR #1065](https://github.com/dbt-labs/dbt-utils/pull/1065)
(commit `e2add69`, merged 2026-01-09). The pre-fix
`dbt_utils.recency()` macro had a `WHERE most_recent < threshold`
clause that evaluated to `NULL` (not `TRUE`) on empty tables, so the
test silently passed when it should have failed. The fix added
`OR most_recent IS NULL`. Customers running pre-fix dbt-utils have a
silent false-negative on freshness checks that empty their pipelines
without alerting; running the post-fix shape against an empty source
correctly surfaces the failure.

The custom test in `tests/recency_raw_orders.sql` mirrors the post-fix
SQL shape directly, avoiding a `dbt deps` step in the fixture. The
PR #1065 link is the externally-verifiable provenance.

## Why this scenario matters beyond "another failure class"

This is the **first `public_incident_replay` provenance type**. It
proves the eval harness can score scenarios reproduced from real,
publicly-verifiable bug fixes. Future scenarios from real public
incidents (or, in private benchmark sets, captures under the
`production_incident` provenance type) follow this template: provenance
block points at the source artifact, `fix_byte_equivalence_target`
declares what claim the contract backs.

## Expected diagnosis

```yaml
failure_class: null_violation
root_cause: |
  raw_orders has zero rows; stg_orders is empty; the recency test's
  most_recent value is NULL; the post-fix `OR most_recent IS NULL`
  clause correctly fails the test.
confidence: ≥ 0.6
```

`null_violation` is the closest fit in the v1 failure class enum — the
test fires because of a NULL value where a non-NULL is expected. A
future class expansion (e.g., `freshness_failure`) might claim this
scenario more precisely.

## Acceptable fix

The fix this scenario grades against is a **consumer-side workaround** —
what a senior DE would write at 3am to unblock the pipeline while waiting
for the upstream load to be repaired. NOT a fork of dbt-utils, NOT an
edit to the seed, NOT a change to dbt_project.yml that suppresses the
test.

Defensible workarounds the agent might propose:

- A defensive filter / coalesce in `stg_orders.sql`
- A count-based companion test in `tests/`
- A `severity: warn` config on the recency test (in `models/staging/schema.yml`)

Any of those is acceptable; the eval contract pins the **forbidden** set
(source seeds, project config, the test SQL itself, schema.yml metadata)
rather than expecting a specific file. The byte-equivalence claim is
"defensible workaround a senior DE would write," not "match the upstream
fix."

## Provenance

```yaml
provenance:
  type: public_incident_replay
  source_pr: https://github.com/dbt-labs/dbt-utils/pull/1065
  source_commit: e2add69
  reproduction_method: dbt-duckdb fixture with empty raw_orders + custom recency test mirroring post-fix dbt_utils.recency() macro shape
  fix_byte_equivalence_target: consumer_workaround
```

## How to reproduce locally

```bash
./setup.sh                               # builds the broken project at $TMPDIR
uv run python record.py                  # runs one live Anthropic agent run (~$0.03)
uv run pytest -k "scenario_04"           # replays the recording without burning credits
```

## Why this scenario exists — and why "no code fix" is the right answer

The recency test correctly fails when the source is empty (header-only
seed). On the bench, this scenario expects:

- **Diagnosis:** `failure_class=logic`, identifying the empty-source
  path through the stale-data check
- **Proposed fix:** ideally `null` (or a non-applying placeholder) — this
  is an **operational alert**, not a code change. The right human action
  is to investigate why upstream stopped delivering rows; no diff in the
  dbt project will fix that.

The stripped reference agent disagrees. It proposes adding rows to
`seeds/raw_orders.csv` to make the test pass. That makes the symptom
go away but DOESN'T fix the underlying issue (broken upstream pipeline)
and creates fake data in source that survives the next sync. The bench
correctly grades this a failure.

The four claims behind the scenario's design:

1. **Source edits are forbidden** in the bench's grading rules — sources
   are inputs from outside the team's authority. Editing them to make
   tests pass is an anti-pattern the bench refuses to reward.

2. **Downstream remediation is preferred** for source-data issues — but
   "no remediation" is also valid. Some failures (this one) signal a
   broken upstream that needs human attention, not a code patch.

3. **"No code fix" is the correct answer** for operational alerts. A
   benchmark that rewards every diagnosis with a diff teaches agents
   to invent fixes. This scenario teaches the opposite: when the right
   answer is "alert a human, don't change code," the agent should say
   so. Empty `proposed_fix` is the contract-compliant response.

4. **The benchmark is intentionally opinionated.** It encodes a
   defensible engineering stance (source data is sacred, fake data is
   worse than the alert it covers up, code changes are not the only
   valid agent output) and grades agents against it. The stripped
   reference agent's failure here is the expected baseline. Agents
   that handle "no fix needed" cleanly — by emitting `proposed_fix=null`
   when source data integrity, not code, is the issue — will score
   higher. Improving on this is the open invitation.
