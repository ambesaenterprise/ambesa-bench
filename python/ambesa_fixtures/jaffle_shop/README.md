# Jaffle Shop fixture

The deterministic dbt project the `ambesa-bench` scenarios are authored against.

## Why Jaffle Shop

It's the dbt community's "hello world" project — every data engineer who'll evaluate an agent against this benchmark knows it instantly. The `baseline/` directory is a vendored copy of [`dbt-labs/jaffle_shop`](https://github.com/dbt-labs/jaffle_shop) with its original MIT license preserved at `baseline/LICENSE`.

## Layout

```
jaffle_shop/
├── baseline/                   # Clean dbt project; passes `dbt build`
├── scenarios/                  # Deliberately-broken variants
│   └── <NN>-<slug>/
│       ├── README.md           # What's broken; acceptable / forbidden fixes
│       ├── expected.yaml       # Golden-outcome contract
│       ├── expected.patch      # Reference fix shape (byte-equivalence grading)
│       ├── overlay/            # Files that replace baseline copies
│       ├── setup.sh            # Builds the working dir from baseline + overlay
│       ├── record.py           # One-off live recording (~$0.03 per run)
│       └── captured/           # Reference agent recording for grading
│           ├── agent_run.json
│           ├── manifest.json
│           └── run_results.json
├── profiles.yml                # dbt-duckdb profile used by setup.sh
└── run.sh                      # Run any scenario end-to-end
```

## Scenarios

| # | Failure class | What's broken |
|---|---|---|
| 01-schema-drift | `schema_drift` | Source CSV column renamed; staging model still uses the old name |
| 02-type-mismatch | `type_mismatch` | Seed schema declares a column as integer; values are non-integer strings |
| 03-null-violation | `null_violation` | NULLs introduced in a `not_null`-tested column; bench expects the fix at the model layer, not in the seed |
| 04-recency-miss-on-empty | `logic` | Empty source table; recency test correctly fails; bench expects "no code fix needed — operational alert" as a valid agent output |

## Running a scenario

Each scenario is self-contained. The runner copies `baseline/` to a temp dir, overlays the scenario's files, runs `dbt build` (which fails by design), and captures `target/manifest.json` + `target/run_results.json` for the agent to consume:

```bash
./run.sh 01-schema-drift
# → /tmp/ambesa-fixture-01-schema-drift/
#   - baseline + overlay applied
#   - target/manifest.json
#   - target/run_results.json (with the failure)
```

The agent is then invoked against this directory; its diagnosis + proposed diff are graded against `expected.yaml` and `expected.patch`.

## Why captured artifacts, not live dbt

Unit / CI runs don't need a live warehouse — the agent reads `manifest.json` and `run_results.json`. Those are captured once against a local DuckDB, committed as fixture data, and replayed. The `record.py` script in each scenario re-records against a live Anthropic call when the underlying agent or prompt changes.

## License

`baseline/` retains its upstream MIT license (see `baseline/LICENSE`). The scaffolding around it (`scenarios/`, `run.sh`, `profiles.yml`) is Apache-2.0 under the repo-root [LICENSE](../../../LICENSE).
