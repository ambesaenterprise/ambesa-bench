# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Ambesa Enterprise Ltd.

"""Eval harness — shared types.

Kept tight on purpose: every field has a clear meaning a PR reader can
interpret without consulting docs.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class Mode(StrEnum):
    """Which side of the harness produced this report.

    - ``recording`` grades the committed ``captured/agent_run.json`` against
      the contract. Catches drift when recordings are refreshed.
    - ``replay`` runs the agent loop with ``MockProvider`` replaying the
      recording's model decisions, with tools dispatched live. Catches
      drift in tools / prompts that breaks the loop's contract.
    """

    RECORDING = "recording"
    REPLAY = "replay"


class Severity(StrEnum):
    """How a check failure should be treated.

    - ``BLOCKING`` — counts toward ``GradeReport.passed``; CI gates on it.
    - ``INFO`` — recorded and rendered but does not gate CI. Use for
      observational metrics (latency drift, exact tool count) that
      should remain visible without being promoted to contract.
    """

    BLOCKING = "blocking"
    INFO = "info"


class CheckResult(BaseModel):
    """One assertion against the contract — passed or not, with detail."""

    name: str
    passed: bool
    severity: Severity = Severity.BLOCKING
    detail: str = ""


class EvalMetrics(BaseModel):
    """Numerical metrics extracted from an AgentRun for the results table."""

    failure_class: str | None = None
    confidence: float | None = None
    cost_usd: float = 0.0
    iterations: int = 0
    prompt_tokens: int = 0
    cached_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: int = 0


class GradeReport(BaseModel):
    """One scenario, one mode, one grade report.

    ``passed`` is the AND of every BLOCKING check's ``passed``. INFO
    checks are recorded and rendered but don't gate CI. The ``checks``
    list is rendered in PR bodies when something fails so reviewers see
    exactly which contract clause was violated.
    """

    scenario: str
    mode: Mode
    passed: bool
    checks: list[CheckResult] = Field(default_factory=list)
    metrics: EvalMetrics = Field(default_factory=EvalMetrics)

    @property
    def blocking_failures(self) -> list[CheckResult]:
        return [c for c in self.checks if not c.passed and c.severity is Severity.BLOCKING]

    @property
    def info_failures(self) -> list[CheckResult]:
        return [c for c in self.checks if not c.passed and c.severity is Severity.INFO]

    @property
    def checks_passed(self) -> int:
        return sum(1 for c in self.checks if c.passed)

    @property
    def checks_total(self) -> int:
        return len(self.checks)


class ScenarioResult(BaseModel):
    """One scenario's full result — both modes."""

    name: str
    recording: GradeReport
    replay: GradeReport

    @property
    def passed(self) -> bool:
        return self.recording.passed and self.replay.passed
