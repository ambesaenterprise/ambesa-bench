# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Ambesa Enterprise Ltd.

"""Eval harness — golden-outcome contracts and scenario grading.

Public entry points:

- :class:`ExpectedOutcome` — Pydantic-validated ``expected.yaml``
- :func:`grade` — score one ``AgentRun`` against an ``ExpectedOutcome``
- :func:`format_table` — pasteable PR-body table from a list of results
"""

from __future__ import annotations

from ambesa_core.eval._types import (
    CheckResult,
    EvalMetrics,
    GradeReport,
    Mode,
    ScenarioResult,
    Severity,
)
from ambesa_core.eval.contract import (
    ExpectedOutcome,
    FixByteEquivalenceTarget,
    Provenance,
    ProvenanceType,
    load_expected,
)
from ambesa_core.eval.grader import grade
from ambesa_core.eval.reporting import format_table

__all__ = [
    "CheckResult",
    "EvalMetrics",
    "ExpectedOutcome",
    "FixByteEquivalenceTarget",
    "GradeReport",
    "Mode",
    "Provenance",
    "ProvenanceType",
    "ScenarioResult",
    "Severity",
    "format_table",
    "grade",
    "load_expected",
]
