# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Ambesa Enterprise Ltd.

"""Grade an ``AgentRun`` against an ``ExpectedOutcome``.

Each check is a self-contained boolean assertion; the result list is what
PR reviewers see when something fails. The ordering is deliberate: the
most load-bearing checks (failure class, confidence floor) come first so
they show up at the top of a failure report.
"""

from __future__ import annotations

from pathlib import Path

from ambesa_core.eval._types import (
    CheckResult,
    EvalMetrics,
    GradeReport,
    Mode,
    Severity,
)
from ambesa_core.eval.contract import ExpectedOutcome
from ambesa_core.fix_validate import fix_applies_cleanly
from ambesa_core.types import AgentRun

_ = Severity  # currently every check is BLOCKING; future soft checks set Severity.INFO explicitly

_TERMINAL_TOOL = "submit_diagnosis"


def grade(  # noqa: PLR0912 — orchestrator naturally branches per check; splitting
    # into per-check helpers would obscure the read-top-down ordering of the
    # contract clauses, which is the whole point of this function's shape.
    *,
    scenario: str,
    mode: Mode,
    run: AgentRun,
    expected: ExpectedOutcome,
    project_dir: Path,
) -> GradeReport:
    """Score one ``AgentRun`` against the contract, return a full report.

    ``project_dir`` is the staged baseline+overlay project the diff would
    apply against — needed for the ``fix_must_apply_cleanly`` check.
    """
    checks: list[CheckResult] = []
    diag = run.final_diagnosis
    fix = run.final_fix

    # 1. Failure class — most load-bearing assertion ────────────────────
    if diag is None:
        checks.append(
            CheckResult(
                name="failure_class",
                passed=False,
                detail="no diagnosis submitted",
            ),
        )
    else:
        ok = diag.failure_class is expected.expected_failure_class
        checks.append(
            CheckResult(
                name="failure_class",
                passed=ok,
                detail=(
                    f"expected={expected.expected_failure_class.value}, "
                    f"got={diag.failure_class.value}"
                ),
            ),
        )

    # 2. Confidence floor ───────────────────────────────────────────────
    if diag is None:
        checks.append(
            CheckResult(
                name="min_confidence",
                passed=False,
                detail="no diagnosis to read confidence from",
            ),
        )
    else:
        ok = diag.confidence >= expected.min_confidence
        checks.append(
            CheckResult(
                name="min_confidence",
                passed=ok,
                detail=f"expected≥{expected.min_confidence}, got={diag.confidence:.3f}",
            ),
        )

    # 3. Tool usage shape ───────────────────────────────────────────────
    tool_names = _all_tool_names_called(run)
    evidence_calls = sum(1 for n in tool_names if n != _TERMINAL_TOOL)

    checks.append(
        CheckResult(
            name="min_evidence_calls",
            passed=evidence_calls >= expected.min_evidence_calls,
            detail=(
                f"expected≥{expected.min_evidence_calls}, got={evidence_calls} "
                f"(non-terminal tool calls)"
            ),
        ),
    )

    if expected.at_least_one_of:
        called = [t for t in expected.at_least_one_of if t in tool_names]
        checks.append(
            CheckResult(
                name="at_least_one_of",
                passed=bool(called),
                detail=(f"required one of {expected.at_least_one_of}, matched={called}"),
            ),
        )

    if expected.forbidden_tool_calls:
        used_forbidden = [t for t in expected.forbidden_tool_calls if t in tool_names]
        checks.append(
            CheckResult(
                name="forbidden_tool_calls",
                passed=not used_forbidden,
                detail=(
                    f"forbidden={expected.forbidden_tool_calls}, violated_with={used_forbidden}"
                ),
            ),
        )

    # 4. Iteration / cost ceilings ──────────────────────────────────────
    iterations = len(run.iterations)
    checks.append(
        CheckResult(
            name="max_iterations",
            passed=iterations <= expected.max_iterations,
            detail=f"expected≤{expected.max_iterations}, got={iterations}",
        ),
    )
    checks.append(
        CheckResult(
            name="max_cost_usd",
            passed=run.total_cost_usd <= expected.max_cost_usd,
            detail=f"expected≤${expected.max_cost_usd:.4f}, got=${run.total_cost_usd:.4f}",
        ),
    )

    # 5. Diff shape ─────────────────────────────────────────────────────
    if (
        expected.expected_files_touched
        or expected.forbidden_files_touched
        or expected.fix_must_apply_cleanly
    ):
        diff_text = fix.diff if fix is not None else ""
        touched = _files_in_diff(diff_text)

        if expected.expected_files_touched:
            missing = [f for f in expected.expected_files_touched if f not in touched]
            checks.append(
                CheckResult(
                    name="expected_files_touched",
                    passed=not missing,
                    detail=(
                        f"expected={expected.expected_files_touched}, "
                        f"touched={sorted(touched)}, missing={missing}"
                    ),
                ),
            )

        if expected.forbidden_files_touched:
            violated = [f for f in expected.forbidden_files_touched if f in touched]
            checks.append(
                CheckResult(
                    name="forbidden_files_touched",
                    passed=not violated,
                    detail=(f"forbidden={expected.forbidden_files_touched}, violated={violated}"),
                ),
            )

        if expected.fix_must_apply_cleanly:
            applies = fix_applies_cleanly(diff_text, project_dir) if diff_text else False
            checks.append(
                CheckResult(
                    name="fix_must_apply_cleanly",
                    passed=applies,
                    detail=(
                        "`git apply --check` succeeded"
                        if applies
                        else "diff is empty or `git apply --check` rejected it"
                    ),
                ),
            )

    # 6. Text assertions on diagnosis ───────────────────────────────────
    if diag is not None and (expected.must_mention_columns or expected.must_mention_models):
        haystack = (diag.root_cause + " " + diag.explanation).lower()
        for col in expected.must_mention_columns:
            checks.append(
                CheckResult(
                    name=f"mentions:{col}",
                    passed=col.lower() in haystack,
                    detail=f"diagnosis text contains '{col}'",
                ),
            )
        for model in expected.must_mention_models:
            checks.append(
                CheckResult(
                    name=f"mentions:{model}",
                    passed=model.lower() in haystack,
                    detail=f"diagnosis text contains '{model}'",
                ),
            )

    metrics = EvalMetrics(
        failure_class=diag.failure_class.value if diag else None,
        confidence=diag.confidence if diag else None,
        cost_usd=run.total_cost_usd,
        iterations=iterations,
        prompt_tokens=run.total_token_usage.prompt,
        cached_tokens=run.total_token_usage.cached,
        completion_tokens=run.total_token_usage.completion,
        latency_ms=int(
            ((run.ended_at - run.started_at).total_seconds() * 1000) if run.ended_at else 0
        ),
    )

    # `passed` is the AND of every BLOCKING check. INFO checks are
    # rendered in the table but don't gate CI.
    blocking_passed = all(c.passed for c in checks if c.severity is Severity.BLOCKING)

    return GradeReport(
        scenario=scenario,
        mode=mode,
        passed=blocking_passed,
        checks=checks,
        metrics=metrics,
    )


def _all_tool_names_called(run: AgentRun) -> list[str]:
    return [tc.name for it in run.iterations for tc in it.tool_calls]


def _files_in_diff(diff_text: str) -> set[str]:
    """Extract the set of files a unified diff modifies, by parsing `+++ b/<path>` lines."""
    files: set[str] = set()
    for line in diff_text.splitlines():
        if line.startswith("+++ b/"):
            files.add(line[len("+++ b/") :].strip())
        elif line.startswith("+++ ") and not line.startswith("+++ /dev/null"):
            files.add(line[len("+++ ") :].strip())
    return files


__all__ = ["grade"]
