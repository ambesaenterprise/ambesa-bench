# ambesa-bench

A vendor-neutral evaluation suite for agents that diagnose broken dbt pipelines.

`ambesa-bench` ships a set of dbt-duckdb scenarios, each with a deliberate breakage, a golden-outcome contract, and captured recordings of a reference agent's diagnosis. It grades any agent that conforms to a small Python interface, using check-based criteria (failure class, root-cause language, cost / iterations bands, fix applies cleanly, forbidden files untouched) plus an optional byte-equivalence claim.

This is **a benchmark, not a product**. The reference adapter included here is intentionally minimal — two evidence-gathering tools (`read_file`, `read_manifest_node`) plus a `submit_diagnosis` sentinel. It is not Ambesa's hosted production agent; that agent uses a richer tool stack and a tuned prompt and lives behind the [Ambesa Watch](https://github.com/apps/ambesa-watch) cloud product. **The published reference baseline is 2/4 on the v1 scenario set.** Beat it with your own agent.

## Install

```bash
git clone https://github.com/ambesaenterprise/ambesa-bench
cd ambesa-bench
uv sync --all-packages
```

Requires Python ≥ 3.12 and [`uv`](https://docs.astral.sh/uv/). The
`--all-packages` flag installs both workspace members (`ambesa-core` and
`ambesa-bench`) so the `ambesa-bench` CLI is available.

## Run

Three grading modes:

| Mode | What it does | Cost |
|---|---|---|
| `recording` | Grade the committed `captured/agent_run.json` as-is. No agent invoked. | $0 |
| `replay` | Drive the agent with `MockProvider` replaying the recording's completions; tools dispatch live. Exercises the loop AND the tool surface against a frozen model. | $0 |
| `live` | Invoke the agent with a real `LLMProvider`. Requires `ANTHROPIC_API_KEY`. | ~$0.05 / scenario |

```bash
uv run ambesa-bench --mode recording
uv run ambesa-bench --mode replay
uv run ambesa-bench --mode live      # requires ANTHROPIC_API_KEY
uv run ambesa-bench --scenarios 01-schema-drift --mode replay
uv run ambesa-bench --agent my_pkg.my_mod:my_agent --mode live
```

Output is a markdown table by default; pass `--output json` for structured output.

## Bring your own agent

Any callable matching this signature plugs into the bench:

```python
async def my_agent(
    *,
    incident: ambesa_core.types.Incident,
    project_root: str | pathlib.Path,
    provider: ambesa_core.llm.LLMProvider,
) -> ambesa_core.types.AgentRun: ...
```

Then:

```bash
uv run ambesa-bench --agent my_package.my_module:my_agent --mode replay
```

See `python/ambesa_bench/src/ambesa_bench/reference_agent.py` for the minimal template.

## Scenarios

The v1 corpus has four scenarios in `python/ambesa_fixtures/jaffle_shop/scenarios/`:

| Scenario | Failure class | Failure surface | Notes |
|---|---|---|---|
| 01-schema-drift | `schema_drift` | `dbt run` | Seed column renamed; downstream model references the old name. |
| 02-type-mismatch | `type_mismatch` | `dbt run` | Seed schema declares a column as `integer`; values are non-integer strings. |
| 03-null-violation | `null_violation` | `dbt test` | Source seed has NULL ids; downstream `not_null` test catches them. Bench expects the fix at the model layer, not in the seed. |
| 04-recency-miss-on-empty | `logic` | `dbt test` | Reproduces [dbt-labs/dbt-utils PR #1065](https://github.com/dbt-labs/dbt-utils/pull/1065). Empty source table → recency test correctly fails. Bench expects "no code fix needed — operational alert" as a valid agent output. |

Each scenario directory contains:

```
scenarios/<name>/
├── README.md              # what's broken, expected diagnosis, acceptable / forbidden fixes
├── expected.yaml          # the golden-outcome contract
├── expected.patch         # the reference fix shape (used by byte-equivalence grading)
├── overlay/               # the deliberate breakage diff applied on top of baseline/
├── captured/              # the reference agent's recorded run
│   ├── agent_run.json
│   ├── manifest.json
│   └── run_results.json
├── setup.sh               # builds a runnable working dir
└── record.py              # one-off live recording (~$0.03 per run, requires ANTHROPIC_API_KEY)
```

## Scoring rubric

Each scenario grades against checks declared in `expected.yaml`:

- **`failure_class_matches`** — diagnosis matches the declared class exactly.
- **`min_confidence`** — agent's confidence is at or above the band.
- **`max_iterations`** — loop ran in fewer than N turns.
- **`max_cost_usd`** — total LLM cost is at or below the band.
- **`forbidden_files_touched`** — proposed fix touches no source seeds, no schema.yml, no `dbt_project.yml`. Source data is immutable in the bench's grading rules.
- **`fix_must_apply_cleanly`** — the proposed unified diff applies cleanly with `git apply`.
- **`fix_byte_equivalence`** (optional) — diff matches `expected.patch` byte-for-byte under the declared target (`consumer_workaround` or `upstream_match`).

Pass = every BLOCKING check passes. INFO checks (latency drift, exact tool counts) are recorded and rendered but don't gate.

## Why the reference baseline is 2/4

Scenarios 03 and 04 deliberately fail on the stripped reference agent.

- **03-null-violation:** the reference agent proposes editing the source seed (filling in the missing ids). The bench treats source seeds as immutable inputs from upstream teams; remediation belongs at the model layer (`where id is not null` in the staging SQL).
- **04-recency-miss-on-empty:** the reference agent proposes filling rows into the seed. The bench treats "alert a human; don't change code" as the correct answer for source-data integrity failures.

These are encoded engineering opinions, not bugs. A vendor-neutral benchmark with no opinions on remediation locality would let every agent "pass" by editing whichever file felt natural. Agents that disagree with the bench's opinions are free to fork the bench or grade against a private contract; the published 2/4 is what the published reference adapter scores against the published rules.

## Repository layout

```
ambesa-bench/
├── LICENSE                                  # Apache-2.0
├── README.md                                # this file
├── CONTRIBUTING.md
├── CODE_OF_CONDUCT.md
├── SECURITY.md
├── pyproject.toml                           # uv workspace root
├── uv.lock
└── python/
    ├── ambesa_core/                         # types, LLM provider, eval grader, public tools
    ├── ambesa_bench/                        # reference agent + bench runner + CLI
    └── ambesa_fixtures/jaffle_shop/         # baseline dbt project + scenarios/
```

## License

Apache-2.0 — see [LICENSE](./LICENSE).

## Contact

Open an issue at https://github.com/ambesaenterprise/ambesa-bench/issues for bugs, scenario proposals, or contract improvements. Security reports: see [SECURITY.md](./SECURITY.md).
