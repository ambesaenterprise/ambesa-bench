# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Ambesa Enterprise Ltd.

"""Eval result rendering — pasteable into PR bodies and terminal output.

Default output is GitHub-flavored markdown so the result table can be
pasted directly into a PR body without editing. ``--plain`` emits the
same data as fixed-width text for terminals that don't render markdown.
"""

from __future__ import annotations

from collections.abc import Iterable

from ambesa_core.eval._types import (
    GradeReport,
    Mode,
    ScenarioResult,
)


def format_table(
    results: Iterable[ScenarioResult],
    *,
    style: str = "markdown",
) -> str:
    """Render eval results as a table.

    style="markdown" (default) emits a GitHub-flavored markdown table.
    style="plain" emits a fixed-width text table.

    Both formats include scenario, mode, pass status, failure class,
    confidence, cost, iterations, and fix-applies status — the columns
    a PR reviewer cares about.
    """
    rows: list[list[str]] = []
    results = list(results)

    for r in results:
        for report in (r.recording, r.replay):
            rows.append(_row_from_report(report))

    rows.append(_total_row(results))

    headers = [
        "Scenario",
        "Mode",
        "Pass",
        "Class",
        "Confidence",
        "Cost",
        "Iters",
        "Fix applies",
    ]
    if style == "plain":
        return _format_plain(headers, rows)
    return _format_markdown(headers, rows)


def format_failure_details(results: Iterable[ScenarioResult]) -> str:
    """Render only the failed checks, grouped by (scenario, mode).

    Used in PR bodies when ``--strict`` blocks: a reviewer sees exactly
    which contract clauses failed without scrolling through passes.
    """
    blocks: list[str] = []
    for r in results:
        for report in (r.recording, r.replay):
            failures = report.blocking_failures
            if not failures:
                continue
            blocks.append(f"### `{report.scenario}` — {report.mode.value}\n")
            for chk in failures:
                blocks.append(f"- ❌ **{chk.name}** — {chk.detail}")
            blocks.append("")
    return "\n".join(blocks).rstrip()


# ─── Internals ──────────────────────────────────────────────────────────


def _row_from_report(r: GradeReport) -> list[str]:
    m = r.metrics
    fix_applies = next(
        (c.passed for c in r.checks if c.name == "fix_must_apply_cleanly"),
        None,
    )
    fix_str = "✅" if fix_applies is True else ("❌" if fix_applies is False else "—")
    conf_str = f"{m.confidence:.2f}" if m.confidence is not None else "—"
    return [
        r.scenario,
        r.mode.value,
        "✅" if r.passed else "❌",
        m.failure_class or "—",
        conf_str,
        f"${m.cost_usd:.4f}",
        str(m.iterations),
        fix_str,
    ]


def _total_row(results: list[ScenarioResult]) -> list[str]:
    n_total = len(results) * 2
    n_pass = sum(int(r.recording.passed) + int(r.replay.passed) for r in results)
    total_cost = sum(r.recording.metrics.cost_usd + r.replay.metrics.cost_usd for r in results)
    total_iters = sum(r.recording.metrics.iterations + r.replay.metrics.iterations for r in results)
    avg_iters = total_iters / n_total if n_total else 0
    return [
        "**TOTAL**",
        "—",
        f"{n_pass}/{n_total}",
        "—",
        "—",
        f"${total_cost:.4f}",
        f"{avg_iters:.1f} avg",
        "—",
    ]


def _format_markdown(headers: list[str], rows: list[list[str]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join("---" for _ in headers) + "|",
    ]
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def _format_plain(headers: list[str], rows: list[list[str]]) -> str:
    widths = [max(len(h), *(len(r[i]) for r in rows)) for i, h in enumerate(headers)]
    sep = "  "

    def fmt(row: list[str]) -> str:
        return sep.join(cell.ljust(w) for cell, w in zip(row, widths, strict=True))

    out = [fmt(headers), sep.join("─" * w for w in widths)]
    for r in rows:
        out.append(fmt(r))
    return "\n".join(out)


__all__ = ["format_failure_details", "format_table"]


# Suppress unused import — re-exported via ``ambesa_core.eval``.
_ = Mode
