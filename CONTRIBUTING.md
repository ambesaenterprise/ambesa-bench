# Contributing to ambesa-bench

Thanks for considering a contribution. `ambesa-bench` is a public, vendor-neutral benchmark — its value depends on the quality and neutrality of the scenarios, the clarity of the grading contract, and the absence of vendor-specific bias. The guidelines below exist to keep that bar.

## What this project accepts

- **New scenarios.** Realistic dbt-failure reproductions with a clear failure class, an `expected.yaml` contract, a complete overlay/baseline/captured/expected.patch set, and a `README.md` describing what's broken and what an acceptable fix looks like. See `python/ambesa_fixtures/jaffle_shop/scenarios/01-schema-drift/` as a template.
- **Eval contract improvements.** New BLOCKING or INFO check types in `ambesa_core.eval.grader` and the matching schema fields in `ambesa_core.eval.contract`. Contract changes must be backwards-compatible with the v1 schema (or shipped as a v2 with a migration note).
- **Adapter integrations.** New agent adapters showing how to plug an agent (other model providers, other prompting strategies, other tool stacks) into the bench runner. Should live in a separate package or example directory, not inside `ambesa_bench`.
- **Bug fixes to the benchmark runner.** Edge cases in `ambesa_bench.runner`, `ambesa_core.eval.grader`, the lab-artifact filter, the CLI, or the fixtures' setup scripts.

## What this project does NOT accept

- **Production Ambesa cloud code.** The hosted agent loop, the dispatch layer, per-tenant memory, accept-rate tuning — none of these belong here. They live in a separate private codebase.
- **Private prompts.** Ambesa's tuned production prompts are not in scope. The public reference agent uses a deliberately minimal prompt declared in `python/ambesa_bench/src/ambesa_bench/_prompt.py`; that prompt and the failure-class enum are the public surface.
- **Customer incidents.** Real failures captured from a customer's production warehouse must be **sanitized** (no customer identifiers, no real schemas, no real table or column names tied to a customer's domain, no real data values) **and explicitly marked** with `provenance.type: production_incident` before review. That provenance value structurally excludes the scenario from the public benchmark aggregator (see `ambesa_core.eval.contract.Provenance.counts_toward_public_benchmark`). Unmarked or unsanitized customer captures will be closed without merge.

If you're unsure whether a contribution fits, open an issue with the proposed change before doing the work.

## Workflow

1. Fork and branch off `main`.
2. For a new scenario: copy a sibling scenario directory and adapt it. Run `uv run ambesa-bench --mode recording --scenarios <your-scenario>` locally and confirm the contract grades the way you intend.
3. Open a PR with:
   - A clear title (Conventional Commits: `feat(fixtures): scenario NN — <slug>`, `feat(eval): <change>`, `fix(bench): <change>`).
   - A description that explains *why* the scenario exists or *what* the bug was. For scenarios: cite the source if it's a `public_incident_replay`.
   - The CI checklist below ticked.
4. CI must be green. PRs with red CI will not be reviewed.

## CI checklist (run locally before pushing)

```bash
uv sync --all-packages
uv run ruff check python/
uv run ruff format --check python/
uv run mypy --strict python/ambesa_core/src python/ambesa_bench/src
uv run pytest python/ -q
uv run ambesa-bench --mode recording
uv run ambesa-bench --mode replay
```

All seven commands must exit 0. (`--mode live` is optional; only run it if you've changed agent behavior and want to refresh recordings, and you have an `ANTHROPIC_API_KEY` set.)

## Code style

- Python 3.12+, `from __future__ import annotations` at the top of every file.
- `ruff` for lint + format (config in root `pyproject.toml`).
- `mypy --strict`. No implicit `Any`.
- Type hints on every public function. Docstrings on every public symbol.
- No comments that explain *what* the code does — leave that to identifiers. Comments are for *why*: hidden constraints, surprising invariants, or workarounds.

## Re-recording scenarios

Each scenario's `captured/agent_run.json` is a recording of the reference agent diagnosing the scenario live. Recordings get refreshed deliberately, not on every CI run, because they cost real Anthropic credits.

To re-record a single scenario:

```bash
cd python/ambesa_fixtures/jaffle_shop/scenarios/<name>
ANTHROPIC_API_KEY=sk-ant-... uv run python record.py
```

Commit the updated `captured/` files in the same PR as the change that motivated the re-record. The PR body should explain *why* the recording changed (model bump, prompt fix, contract change).

## Security

See [SECURITY.md](./SECURITY.md).

## Code of conduct

By participating you agree to abide by [CODE_OF_CONDUCT.md](./CODE_OF_CONDUCT.md).

## License

By contributing, you agree your contributions are licensed under Apache-2.0 (the project license) — see [LICENSE](./LICENSE).
