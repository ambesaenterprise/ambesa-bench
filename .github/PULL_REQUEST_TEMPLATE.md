## Summary

<!-- 1-2 sentences. What changed and why. -->

## Type of change

- [ ] New scenario
- [ ] Eval contract / grader change
- [ ] Adapter integration
- [ ] Bug fix in the bench runner / CLI / fixtures
- [ ] Documentation / repo hygiene
- [ ] Other (explain)

## Test plan

- [ ] `uv run ruff check python/` exits 0
- [ ] `uv run ruff format --check python/` exits 0
- [ ] `uv run mypy --strict python/ambesa_core/src python/ambesa_bench/src` exits 0
- [ ] `uv run pytest python/ -q` exits 0
- [ ] `uv run ambesa-bench --mode recording` exits 0
- [ ] `uv run ambesa-bench --mode replay` exits 0
- [ ] (If you re-recorded any scenario) `captured/` updated and commit references the recording cost

## Scenario PRs only

- [ ] `expected.yaml` validates against the contract schema
- [ ] `overlay/` reproduces the breakage from a clean `baseline/`
- [ ] `setup.sh` runs end-to-end and produces `target/manifest.json` + `target/run_results.json` with the expected failure
- [ ] `README.md` describes what's broken, the expected diagnosis, and acceptable / forbidden fixes
- [ ] If `provenance.type` is `public_incident_replay`: source PR / commit linked in the README

## Risks

<!-- What could regress? What did you spot-check? -->
