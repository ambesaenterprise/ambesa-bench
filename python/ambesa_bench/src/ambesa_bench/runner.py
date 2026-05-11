# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Ambesa Enterprise Ltd.

"""Public bench-runner — drive any agent against ambesa-bench scenarios.

A bench scenario directory must contain:

    expected.yaml             # the golden-outcome contract
    captured/agent_run.json   # a previous agent's recording (optional for live mode)
    captured/manifest.json    # captured dbt artifacts for the failing run
    captured/run_results.json
    overlay/                  # files that override baseline (the breakage)

Three grading modes:

* ``recording`` — grade ``captured/agent_run.json`` as-is. Useful for
  scoring a saved run without re-invoking any agent.
* ``replay`` — drive the agent with :class:`MockProvider` replaying the
  recording's completions. Tools dispatch live against the staged
  project_dir; only the model decisions are frozen. Catches drift in
  the tool surface.
* ``live`` — invoke the agent with a real :class:`LLMProvider` (e.g.
  AnthropicProvider). Costs LLM credits.

Public API: :func:`run_scenario` for one scenario, :func:`run_all` for the
full suite. The :mod:`cli` module wires both into a ``ambesa-bench``
entry point.
"""

from __future__ import annotations

import asyncio
import importlib
import shutil
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Protocol, cast
from uuid import uuid4

# Default agent — imported eagerly. There's no circular dependency
# (reference_agent does not import runner) so the lazy form was overkill.
from ambesa_bench.reference_agent import run as _default_reference_agent
from ambesa_core.eval._types import GradeReport, Mode
from ambesa_core.eval.contract import load_expected
from ambesa_core.eval.grader import grade
from ambesa_core.llm import LLMProvider
from ambesa_core.testing import MockProvider, completions_from_agent_run
from ambesa_core.types import (
    AgentRun,
    FailingModel,
    FailureClass,
    Incident,
)


class BenchMode(StrEnum):
    """Grading modes the public runner supports."""

    RECORDING = "recording"
    REPLAY = "replay"
    LIVE = "live"


class AgentRunner(Protocol):
    """The shape any agent must satisfy to plug into the bench.

    A user-supplied agent is a coroutine that takes an
    :class:`Incident`, a ``project_root`` Path, and an
    :class:`LLMProvider`, and returns an :class:`AgentRun`. The
    reference agent (:func:`ambesa_bench.run`) satisfies this; users
    writing their own agents should match this signature so the
    bench-runner can drive them uniformly.
    """

    async def __call__(
        self,
        *,
        incident: Incident,
        project_root: str | Path,
        provider: LLMProvider,
    ) -> AgentRun: ...


@dataclass(frozen=True)
class BenchResult:
    """One scenario's grade in one mode plus the AgentRun that produced it."""

    scenario: str
    mode: BenchMode
    report: GradeReport
    run: AgentRun


# ────────────────────────────────────────────────────────────────────────
# Discovery + setup helpers
# ────────────────────────────────────────────────────────────────────────


def discover_scenarios(scenarios_root: Path) -> list[Path]:
    """Return scenario directories under ``scenarios_root`` in sorted order.

    A directory counts as a scenario iff it contains ``expected.yaml``.
    Hidden dirs (``.foo``) and dirs without the contract are skipped.
    """
    return sorted(
        d
        for d in scenarios_root.iterdir()
        if d.is_dir() and not d.name.startswith(".") and (d / "expected.yaml").exists()
    )


def stage_project(*, baseline: Path, overlay: Path, captured: Path) -> Path:
    """Copy baseline → tmpdir, apply overlay, plant captured target/.

    Returns the staged project_dir. Caller is responsible for cleanup
    (typically a context manager wrapping the call). The bench-runner
    uses this layout because the grader's ``fix_must_apply_cleanly``
    check needs a writable working tree.
    """
    tmp = Path(tempfile.mkdtemp(prefix="ambesa-bench-"))
    project = tmp / "project"
    shutil.copytree(baseline, project)

    if overlay.exists():
        for src in overlay.rglob("*"):
            if src.is_file():
                rel = src.relative_to(overlay)
                dest = project / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)

    target = project / "target"
    target.mkdir(exist_ok=True)
    shutil.copy2(captured / "manifest.json", target / "manifest.json")
    shutil.copy2(captured / "run_results.json", target / "run_results.json")
    return project


def load_recorded_run(path: Path) -> AgentRun:
    """Reconstruct the recorded :class:`AgentRun` from its JSON dump."""
    return AgentRun.model_validate_json(path.read_text())


def incident_from_recording(recorded_run: AgentRun) -> Incident:
    """Build a fresh :class:`Incident` for replay/live runs.

    Uses the recording's failing model identity (extracted from the first
    ``read_manifest_node`` or ``read_file`` tool call argument) so the
    replay agent diagnoses the same target the recording did. Falls back
    to ``"model.unknown.unknown"`` if no hint is present — recording
    is malformed; the grader's checks fail clearly rather than crashing
    here.
    """
    diag = recorded_run.final_diagnosis
    failure_class = diag.failure_class if diag else FailureClass.UNKNOWN
    error_text = diag.root_cause if diag else "(unknown — recording lacked diagnosis)"

    return Incident(
        id=uuid4(),
        repo_full_name="ambesa-bench/scenario",
        commit_sha="0" * 40,
        failing_model=FailingModel(
            unique_id=_extract_unique_id(recorded_run) or "model.unknown.unknown",
            name="failing_model",
            relation_name=None,
            error=error_text,
            raw_status="error",
            failure_class_hint=failure_class,
        ),
        manifest_excerpt=None,
        recent_commits=[],
        detected_at=datetime.now(UTC),
    )


def _extract_unique_id(run: AgentRun) -> str | None:
    """Look for the first manifest-node lookup or file read in the recording.

    Order of preference: ``read_manifest_node`` arg ``unique_id`` →
    ``read_file`` path translated back to a likely unique_id. Returns
    None when nothing identifiable is in the recording.
    """
    for it in run.iterations:
        for tc in it.tool_calls:
            if tc.name == "read_manifest_node":
                uid = tc.arguments.get("unique_id")
                if isinstance(uid, str):
                    return uid
            if tc.name == "read_file":
                path = tc.arguments.get("path", "")
                if isinstance(path, str) and path.startswith("models/") and path.endswith(".sql"):
                    # models/staging/stg_customers.sql → model.<project>.stg_customers
                    # The project name is unknown here; the caller falls back to UNKNOWN
                    # if the grader needs it strictly.
                    return None
    return None


# ────────────────────────────────────────────────────────────────────────
# Mode runners
# ────────────────────────────────────────────────────────────────────────


def _grade_recording(*, scenario: str, project_dir: Path, captured_dir: Path) -> BenchResult:
    expected = load_expected(captured_dir.parent / "expected.yaml")
    run = load_recorded_run(captured_dir / "agent_run.json")
    report = grade(
        scenario=scenario,
        mode=Mode.RECORDING,
        run=run,
        expected=expected,
        project_dir=project_dir,
    )
    return BenchResult(scenario=scenario, mode=BenchMode.RECORDING, report=report, run=run)


async def _run_replay(
    *,
    scenario: str,
    project_dir: Path,
    captured_dir: Path,
    agent: AgentRunner,
) -> BenchResult:
    expected = load_expected(captured_dir.parent / "expected.yaml")
    recorded = load_recorded_run(captured_dir / "agent_run.json")
    completions = completions_from_agent_run(captured_dir / "agent_run.json")
    provider = MockProvider(completions)
    incident = incident_from_recording(recorded)
    run = await agent(
        incident=incident,
        project_root=project_dir,
        provider=provider,
    )
    report = grade(
        scenario=scenario,
        mode=Mode.REPLAY,
        run=run,
        expected=expected,
        project_dir=project_dir,
    )
    return BenchResult(scenario=scenario, mode=BenchMode.REPLAY, report=report, run=run)


async def _run_live(
    *,
    scenario: str,
    project_dir: Path,
    captured_dir: Path,
    agent: AgentRunner,
    provider: LLMProvider,
) -> BenchResult:
    expected = load_expected(captured_dir.parent / "expected.yaml")
    # An ``Incident`` is still required; live runs synthesize one from the
    # captured manifest+run_results so the bench is self-contained.
    recorded = load_recorded_run(captured_dir / "agent_run.json")
    incident = incident_from_recording(recorded)
    run = await agent(
        incident=incident,
        project_root=project_dir,
        provider=provider,
    )
    report = grade(
        scenario=scenario,
        mode=Mode.REPLAY,  # ScenarioResult only knows recording/replay; live grades like replay
        run=run,
        expected=expected,
        project_dir=project_dir,
    )
    return BenchResult(scenario=scenario, mode=BenchMode.LIVE, report=report, run=run)


# ────────────────────────────────────────────────────────────────────────
# Top-level entry points
# ────────────────────────────────────────────────────────────────────────


def run_scenario(
    *,
    scenario_dir: Path,
    fixture_root: Path,
    mode: BenchMode,
    agent: AgentRunner | None = None,
    provider: LLMProvider | None = None,
) -> BenchResult:
    """Evaluate one scenario in one mode. Synchronous wrapper."""
    name = scenario_dir.name
    captured = scenario_dir / "captured"
    if not captured.exists():
        raise FileNotFoundError(f"missing captured/ in {scenario_dir}")

    project_dir = stage_project(
        baseline=fixture_root / "baseline",
        overlay=scenario_dir / "overlay",
        captured=captured,
    )

    if mode is BenchMode.RECORDING:
        return _grade_recording(scenario=name, project_dir=project_dir, captured_dir=captured)

    if agent is None:
        agent = _default_reference_agent

    if mode is BenchMode.REPLAY:
        return asyncio.run(
            _run_replay(
                scenario=name,
                project_dir=project_dir,
                captured_dir=captured,
                agent=agent,
            ),
        )

    if mode is BenchMode.LIVE:
        if provider is None:
            raise ValueError("live mode requires an LLMProvider; pass one or use replay/recording")
        return asyncio.run(
            _run_live(
                scenario=name,
                project_dir=project_dir,
                captured_dir=captured,
                agent=agent,
                provider=provider,
            ),
        )

    raise ValueError(f"unknown mode: {mode}")


def run_all(
    *,
    scenarios_root: Path,
    fixture_root: Path,
    mode: BenchMode,
    agent: AgentRunner | None = None,
    provider: LLMProvider | None = None,
    only: Iterable[str] | None = None,
) -> list[BenchResult]:
    """Run every scenario (or the subset matching ``only``) in ``mode``."""
    selected = discover_scenarios(scenarios_root)
    if only is not None:
        wanted = set(only)
        selected = [s for s in selected if s.name in wanted]
    return [
        run_scenario(
            scenario_dir=s,
            fixture_root=fixture_root,
            mode=mode,
            agent=agent,
            provider=provider,
        )
        for s in selected
    ]


def load_agent(spec: str) -> AgentRunner:
    """Resolve a ``module:attr`` string to a callable agent.

    Used by the CLI's ``--agent`` flag so users can plug in their own
    agent without modifying the bench code. ``ambesa_bench.reference_agent:run``
    is the default and a good template to copy.
    """
    if ":" not in spec:
        raise ValueError(f"agent spec must be 'module:attr', got: {spec!r}")
    module_name, attr_name = spec.split(":", 1)
    module = importlib.import_module(module_name)
    fn = getattr(module, attr_name)
    return cast("AgentRunner", fn)


__all__ = [
    "AgentRunner",
    "BenchMode",
    "BenchResult",
    "discover_scenarios",
    "incident_from_recording",
    "load_agent",
    "load_recorded_run",
    "run_all",
    "run_scenario",
    "stage_project",
]
