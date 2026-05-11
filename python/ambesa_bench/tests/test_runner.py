# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Ambesa Enterprise Ltd.

"""Unit tests for the public bench-runner.

Covers discovery, project staging, agent loading, and per-mode runs
without invoking a live LLM. CLI smoke tests use Click's CliRunner so
no subprocess overhead.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from click.testing import CliRunner

from ambesa_bench.cli import cli
from ambesa_bench.reference_agent import run as reference_agent_run
from ambesa_bench.runner import (
    BenchMode,
    BenchResult,
    discover_scenarios,
    incident_from_recording,
    load_agent,
    run_all,
    run_scenario,
    stage_project,
)
from ambesa_core.types import (
    AgentIteration,
    AgentRun,
    AgentStopReason,
    Diagnosis,
    FailureClass,
    TokenUsage,
    ToolCall,
)

# ────────────────────────────────────────────────────────────────────────
# discover_scenarios
# ────────────────────────────────────────────────────────────────────────


def test_discover_finds_only_dirs_with_expected_yaml(tmp_path: Path) -> None:
    (tmp_path / "01-good").mkdir()
    (tmp_path / "01-good/expected.yaml").write_text("expected_failure_class: schema_drift\n")
    (tmp_path / "02-no-contract").mkdir()  # missing expected.yaml
    (tmp_path / ".hidden").mkdir()
    (tmp_path / ".hidden/expected.yaml").write_text("expected_failure_class: schema_drift\n")
    (tmp_path / "loose-file.txt").write_text("not a scenario")

    found = discover_scenarios(tmp_path)
    assert [p.name for p in found] == ["01-good"]


# ────────────────────────────────────────────────────────────────────────
# stage_project
# ────────────────────────────────────────────────────────────────────────


def test_stage_project_overlays_files_and_plants_target(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline"
    overlay = tmp_path / "overlay"
    captured = tmp_path / "captured"
    for d in (baseline, overlay, captured):
        d.mkdir()
    (baseline / "seeds").mkdir()
    (baseline / "seeds/raw_customers.csv").write_text("id,name\n1,Alice\n")
    (overlay / "seeds").mkdir()
    (overlay / "seeds/raw_customers.csv").write_text("customer_id,name\n1,Alice\n")
    (captured / "manifest.json").write_text("{}")
    (captured / "run_results.json").write_text("[]")

    project = stage_project(baseline=baseline, overlay=overlay, captured=captured)

    # Overlay won — broken header is what's in the staged project
    assert (project / "seeds/raw_customers.csv").read_text().startswith("customer_id,")
    # target/ is planted with captured artifacts
    assert (project / "target/manifest.json").read_text() == "{}"
    assert (project / "target/run_results.json").read_text() == "[]"


# ────────────────────────────────────────────────────────────────────────
# incident_from_recording
# ────────────────────────────────────────────────────────────────────────


def _make_recording_with_diagnosis() -> AgentRun:
    return AgentRun(
        incident_id="local",
        tenant_id="local",
        started_at=datetime.now(UTC),
        iterations=[
            AgentIteration(
                n=1,
                model="claude-sonnet-4-6",
                prompt_tokens=10,
                completion_tokens=5,
                cost_usd=0.001,
                latency_ms=100,
                tool_calls=[
                    ToolCall(
                        id="tu_1",
                        name="read_manifest_node",
                        arguments={"unique_id": "model.demo.stg_customers"},
                    ),
                ],
            ),
        ],
        final_diagnosis=Diagnosis(
            incident_id="00000000-0000-0000-0000-000000000001",
            failure_class=FailureClass.SCHEMA_DRIFT,
            root_cause="renamed col",
            explanation="x",
            confidence=0.9,
            prompt_version="v1",
            model="claude-sonnet-4-6",
            token_usage=TokenUsage(prompt=10, completion=5),
            cost_usd=0.001,
            latency_ms=100,
        ),
        stop_reason=AgentStopReason.DIAGNOSIS_SUBMITTED,
    )


def test_incident_from_recording_extracts_unique_id_from_manifest_call() -> None:
    rec = _make_recording_with_diagnosis()
    incident = incident_from_recording(rec)
    assert incident.failing_model.unique_id == "model.demo.stg_customers"
    assert incident.failing_model.failure_class_hint is FailureClass.SCHEMA_DRIFT


def test_incident_from_recording_falls_back_when_no_diagnosis() -> None:
    rec = AgentRun(
        incident_id="local",
        tenant_id="local",
        started_at=datetime.now(UTC),
        stop_reason=AgentStopReason.MAX_ITERATIONS,
    )
    incident = incident_from_recording(rec)
    assert incident.failing_model.unique_id == "model.unknown.unknown"
    assert incident.failing_model.failure_class_hint is FailureClass.UNKNOWN


# ────────────────────────────────────────────────────────────────────────
# load_agent
# ────────────────────────────────────────────────────────────────────────


def test_load_agent_resolves_dotted_path() -> None:
    fn = load_agent("ambesa_bench.reference_agent:run")
    assert fn is reference_agent_run


def test_load_agent_rejects_bad_spec() -> None:
    with pytest.raises(ValueError, match="agent spec"):
        load_agent("no_colon_here")


# ────────────────────────────────────────────────────────────────────────
# run_scenario / run_all in RECORDING mode (end-to-end against fake scenario)
# ────────────────────────────────────────────────────────────────────────


def _build_minimal_scenario(tmp_path: Path, *, scenario_name: str = "01-fake") -> tuple[Path, Path]:
    """Build a minimal scenario layout that the runner can grade in RECORDING.

    Returns (scenarios_root, fixture_root). Fixture has a baseline/ dir
    with one model so stage_project has something to copy. Idempotent —
    re-calls just add another scenario under the same fixture_root.
    """
    fixture_root = tmp_path / "fixture"
    baseline = fixture_root / "baseline"
    if not baseline.exists():
        baseline.mkdir(parents=True)
        (baseline / "dbt_project.yml").write_text("name: demo\nprofile: demo\n")

    scenarios_root = fixture_root / "scenarios"
    scenario = scenarios_root / scenario_name
    captured = scenario / "captured"
    captured.mkdir(parents=True, exist_ok=True)
    (captured / "manifest.json").write_text("{}")
    (captured / "run_results.json").write_text("[]")

    # Maximally lax (within schema) — runner-mechanics test, not grader.
    (scenario / "expected.yaml").write_text(
        "provenance:\n"
        "  type: canonical_fixture\n"
        "  reproduction_method: synthetic test fixture\n"
        "  fix_byte_equivalence_target: exact\n"
        "expected_failure_class: schema_drift\n"
        "min_confidence: 0.0\n"
        "min_evidence_calls: 0\n"
        "max_iterations: 30\n"
        "max_cost_usd: 100.0\n"
        "fix_must_apply_cleanly: false\n",
    )

    rec = _make_recording_with_diagnosis()
    (captured / "agent_run.json").write_text(rec.model_dump_json())

    return scenarios_root, fixture_root


def test_run_scenario_recording_grades_existing_recording(tmp_path: Path) -> None:
    scenarios_root, fixture_root = _build_minimal_scenario(tmp_path)
    scenario_dir = next(iter(discover_scenarios(scenarios_root)))

    result = run_scenario(
        scenario_dir=scenario_dir,
        fixture_root=fixture_root,
        mode=BenchMode.RECORDING,
    )
    assert isinstance(result, BenchResult)
    assert result.mode is BenchMode.RECORDING
    assert all(c.passed for c in result.report.checks), [
        (c.name, c.passed, c.detail) for c in result.report.checks if not c.passed
    ]


def test_run_all_filters_to_only_arg(tmp_path: Path) -> None:
    scenarios_root, fixture_root = _build_minimal_scenario(tmp_path, scenario_name="01-keep")
    _build_minimal_scenario(tmp_path, scenario_name="02-skip")[0]
    # second scenario sits in the same scenarios_root (relies on _build_minimal_scenario
    # creating under fixture_root/scenarios). Re-check:
    assert {p.name for p in discover_scenarios(scenarios_root)} >= {"01-keep"}

    results = run_all(
        scenarios_root=scenarios_root,
        fixture_root=fixture_root,
        mode=BenchMode.RECORDING,
        only=["01-keep"],
    )
    assert {r.scenario for r in results} == {"01-keep"}


# ────────────────────────────────────────────────────────────────────────
# CLI smoke
# ────────────────────────────────────────────────────────────────────────


def test_cli_recording_mode_outputs_markdown_table(tmp_path: Path) -> None:
    scenarios_root, fixture_root = _build_minimal_scenario(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "--scenarios-root",
            str(scenarios_root),
            "--fixture-root",
            str(fixture_root),
            "--mode",
            "recording",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "01-fake" in result.output
    assert "✅" in result.output
    assert "TOTAL" in result.output


def test_cli_json_output_is_parseable(tmp_path: Path) -> None:
    scenarios_root, fixture_root = _build_minimal_scenario(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "--scenarios-root",
            str(scenarios_root),
            "--fixture-root",
            str(fixture_root),
            "--mode",
            "recording",
            "--output",
            "json",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert isinstance(payload, list)
    assert payload[0]["scenario"] == "01-fake"
    assert payload[0]["mode"] == "recording"
    assert payload[0]["passed"] is True


def test_cli_strict_exits_nonzero_on_failure(tmp_path: Path) -> None:
    scenarios_root, fixture_root = _build_minimal_scenario(tmp_path)
    # Make the recording deliberately wrong-class — grader will fail
    bad = AgentRun(
        incident_id="local",
        tenant_id="local",
        started_at=datetime.now(UTC),
        final_diagnosis=Diagnosis(
            incident_id="00000000-0000-0000-0000-000000000002",
            failure_class=FailureClass.NULL_VIOLATION,  # expected was schema_drift
            root_cause="x",
            explanation="x",
            confidence=0.5,
            prompt_version="v1",
            model="claude-sonnet-4-6",
            token_usage=TokenUsage(prompt=1, completion=1),
            cost_usd=0.0,
            latency_ms=0,
        ),
        stop_reason=AgentStopReason.DIAGNOSIS_SUBMITTED,
    )
    captured = scenarios_root / "01-fake/captured"
    (captured / "agent_run.json").write_text(bad.model_dump_json())

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "--scenarios-root",
            str(scenarios_root),
            "--fixture-root",
            str(fixture_root),
            "--mode",
            "recording",
            "--strict",
        ],
    )
    assert result.exit_code == 1
    assert "❌" in result.output
