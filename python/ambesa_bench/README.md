# ambesa-bench

Reference adapter for the [ambesa-bench](https://github.com/ambesaenterprise/ambesa-bench) benchmark — a vendor-neutral evaluation suite for agents that diagnose broken dbt pipelines.

## What this package contains

- `ambesa_bench.reference_agent` — a deliberately minimal agent that scores against the bench's scenarios using two evidence-gathering tools (`read_file`, `read_manifest_node`) plus an `LLMProvider` abstraction. This is intentionally not a production-grade agent; it exists so any reader has a working baseline to reproduce locally and improve on.
- `ambesa_bench.runner` — the CLI machinery that takes any agent matching the reference signature and grades it against the scenarios via `ambesa_core.eval.grader`.

## What this package does NOT contain

- Ambesa's hosted production agent (richer tool stack, tuned prompts, dispatch + per-tenant memory layers — lives behind the cloud product, [Ambesa Watch](https://github.com/apps/ambesa-watch)).

## License

This project is Apache-2.0 — see [LICENSE](../../LICENSE).

## Contact

Open an issue at https://github.com/ambesaenterprise/ambesa-bench/issues.
