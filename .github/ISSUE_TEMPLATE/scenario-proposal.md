---
name: Scenario proposal
about: Propose a new scenario for the benchmark
labels: scenario-proposal
---

## Failure class

<!-- One of: schema_drift, type_mismatch, null_violation, missing_source, stale_ref, cast_failure, permissions, logic, unknown. If the failure doesn't fit, propose a class extension separately first. -->

## Failure surface

- [ ] `dbt run` (model build fails)
- [ ] `dbt test` (model builds, test fails)
- [ ] `dbt seed` (seed load fails)
- [ ] `dbt compile` (parsing / Jinja fails)
- [ ] Other (specify)

## Provenance

- [ ] `canonical_fixture` — synthetic breakage authored from scratch
- [ ] `public_incident_replay` — reproduces a real, publicly-verifiable bug fix. Link the source PR / commit:
- [ ] `production_incident` (private benchmark only — needs sanitization, will not be accepted in the public repo)

## What the scenario tests

<!-- 2-3 sentences. What gap in the current corpus does this fill? What would a competent agent's diagnosis look like? What's the bench's stance on the acceptable fix? -->

## Acceptable / forbidden fix shape

- Acceptable fix touches:
- Forbidden files (e.g., source seeds, schema.yml, dbt_project.yml):
- "No code fix" is a valid agent output: [ ] yes / [ ] no

## Status

- [ ] Proposal only
- [ ] I plan to author the PR myself
- [ ] I'd like a maintainer to author it
