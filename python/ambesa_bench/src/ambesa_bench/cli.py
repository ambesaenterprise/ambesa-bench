# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Ambesa Enterprise Ltd.

"""Command-line interface for ambesa-bench.

Wires :func:`ambesa_bench.runner.run_all` into a single ``ambesa-bench``
entry point. Defaults are tuned to "clone the bench, type ``ambesa-bench``,
see your scores":

    ambesa-bench                        # all scenarios, recording mode, markdown
    ambesa-bench --mode replay          # exercise the loop against MockProvider
    ambesa-bench --mode live            # invoke agent live (requires API key)
    ambesa-bench --scenarios 01-schema-drift --mode replay
    ambesa-bench --agent my_pkg.my_mod:my_agent --mode live
    ambesa-bench --strict               # exit 1 if any scenario fails

Output is markdown by default; ``--output json`` emits structured JSON for
CI/automation.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import click

from ambesa_bench.runner import (
    BenchMode,
    BenchResult,
    load_agent,
    run_all,
)


def _default_scenarios_root() -> Path:
    """Locate the bench's ``scenarios/`` directory.

    Resolves to ``./scenarios/`` (flat layout), ``./python/ambesa_fixtures/
    jaffle_shop/scenarios/`` (current bench layout), or — when the package
    is installed outside a checkout — a path relative to ``__file__``.
    Override with ``--scenarios-root``.
    """
    cwd = Path.cwd()
    for candidate in (
        cwd / "scenarios",
        cwd / "python/ambesa_fixtures/jaffle_shop/scenarios",
        Path(__file__).resolve().parent.parent.parent.parent.parent
        / "python/ambesa_fixtures/jaffle_shop/scenarios",
    ):
        if candidate.exists() and candidate.is_dir():
            return candidate
    return cwd / "scenarios"  # let the runner raise a clear FileNotFoundError


def _default_fixture_root(scenarios_root: Path) -> Path:
    """The fixture root is one level up from scenarios/ (contains baseline/)."""
    return scenarios_root.parent


def _format_markdown(results: list[BenchResult]) -> str:
    """Render BenchResults as a compact markdown table.

    One row per (scenario, mode). Columns: scenario, mode, pass/fail tick,
    failure_class as graded, confidence, cost_usd, iterations. Designed to
    look the same as ``ambesa eval --strict`` for visual parity.
    """
    lines = [
        "| Scenario | Mode | Pass | Class | Confidence | Cost | Iters |",
        "|---|---|---|---|---|---|---|",
    ]
    pass_count = 0
    total_cost = 0.0
    total_iters = 0
    for r in results:
        passed = all(c.passed for c in r.report.checks)
        if passed:
            pass_count += 1
        m = r.report.metrics
        cls = m.failure_class or "—"
        conf = f"{m.confidence:.2f}" if m.confidence is not None else "—"
        lines.append(
            f"| {r.scenario} | {r.mode.value} | "
            f"{'✅' if passed else '❌'} | {cls} | {conf} | "
            f"${m.cost_usd:.4f} | {m.iterations} |",
        )
        total_cost += m.cost_usd
        total_iters += m.iterations
    avg_iters = total_iters / len(results) if results else 0.0
    lines.append(
        f"| **TOTAL** | — | {pass_count}/{len(results)} | — | — | "
        f"${total_cost:.4f} | {avg_iters:.1f} avg |",
    )
    return "\n".join(lines)


@click.command(name="ambesa-bench")
@click.option(
    "--scenarios",
    multiple=True,
    metavar="NAME",
    help="Restrict to specific scenarios (repeat flag). Default: all discovered.",
)
@click.option(
    "--mode",
    type=click.Choice([m.value for m in BenchMode]),
    default=BenchMode.RECORDING.value,
    show_default=True,
    help="Grading mode.",
)
@click.option(
    "--agent",
    metavar="MODULE:ATTR",
    default="ambesa_bench.reference_agent:run",
    show_default=True,
    help="Dotted import path to your agent function (replay/live modes only).",
)
@click.option(
    "--scenarios-root",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=None,
    help="Override scenarios directory.",
)
@click.option(
    "--fixture-root",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=None,
    help="Override fixture root (must contain baseline/).",
)
@click.option(
    "--output",
    type=click.Choice(["markdown", "json"]),
    default="markdown",
    show_default=True,
)
@click.option(
    "--strict",
    is_flag=True,
    help="Exit 1 if any scenario fails to grade green.",
)
def cli(
    scenarios: tuple[str, ...],
    mode: str,
    agent: str,
    scenarios_root: Path | None,
    fixture_root: Path | None,
    output: str,
    strict: bool,
) -> None:
    """Grade an agent against the ambesa-bench dbt-failure scenarios."""
    bench_mode = BenchMode(mode)
    sroot = scenarios_root or _default_scenarios_root()
    froot = fixture_root or _default_fixture_root(sroot)
    agent_fn = load_agent(agent) if bench_mode is not BenchMode.RECORDING else None

    provider = None
    if bench_mode is BenchMode.LIVE:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            click.echo(
                "live mode requires ANTHROPIC_API_KEY (or pass a custom agent that "
                "supplies its own provider). Use --mode replay if you don't have one.",
                err=True,
            )
            sys.exit(2)
        from ambesa_core.llm import get_provider  # noqa: PLC0415 — lazy: only live mode needs it

        provider = get_provider("anthropic")

    only = list(scenarios) if scenarios else None
    results = run_all(
        scenarios_root=sroot,
        fixture_root=froot,
        mode=bench_mode,
        agent=agent_fn,
        provider=provider,
        only=only,
    )

    if output == "json":
        payload = [
            {
                "scenario": r.scenario,
                "mode": r.mode.value,
                "passed": all(c.passed for c in r.report.checks),
                "checks": [
                    {"name": c.name, "passed": c.passed, "detail": c.detail}
                    for c in r.report.checks
                ],
                "metrics": r.report.metrics.model_dump(),
            }
            for r in results
        ]
        click.echo(json.dumps(payload, indent=2))
    else:
        click.echo(_format_markdown(results))

    any_failed = any(not all(c.passed for c in r.report.checks) for r in results)
    if strict and any_failed:
        sys.exit(1)


if __name__ == "__main__":  # pragma: no cover
    cli()
