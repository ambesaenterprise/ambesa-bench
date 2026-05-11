# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Ambesa Enterprise Ltd.

"""Unit tests for the stripped reference agent.

Every test runs the loop against a hand-rolled MockProvider — no live
Anthropic, no network. Each test exercises one loop-shape contract:

* terminal call ends the run with diagnosis_submitted
* read_file dispatch round-trips through the lab-leak filter
* unknown tool surfaces an error result the model can recover from
* exhausted iterations reach MAX_ITERATIONS
* zero tool calls without a diagnosis reaches ERROR
* cost cap halts before hitting max_iterations
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from ambesa_bench import run as bench_run
from ambesa_core.llm import ToolCallBlock
from ambesa_core.testing import MockProvider, make_completion
from ambesa_core.types import (
    AgentStopReason,
    FailingModel,
    FailureClass,
    Incident,
)


def _incident() -> Incident:
    """Build a minimal Incident with stg_customers as the failing model."""
    return Incident(
        id=uuid4(),
        repo_full_name="acme/demo",
        commit_sha="0" * 40,
        failing_model=FailingModel(
            unique_id="model.demo.stg_customers",
            name="stg_customers",
            relation_name="demo.stg_customers",
            error="Referenced column 'id' not found in FROM clause!",
            raw_status="error",
            failure_class_hint=FailureClass.SCHEMA_DRIFT,
        ),
        manifest_excerpt={
            "nodes": {
                "model.demo.stg_customers": {
                    "original_file_path": "models/staging/stg_customers.sql",
                },
                "seed.demo.raw_customers": {
                    "original_file_path": "seeds/raw_customers.csv",
                },
            },
        },
        recent_commits=[],
        detected_at=datetime.now(UTC),
    )


def _terminal_call(
    *, root_cause: str = "renamed column", confidence: float = 0.95
) -> ToolCallBlock:
    return ToolCallBlock(
        id="tu_terminal",
        name="submit_diagnosis",
        input={
            "failure_class": FailureClass.SCHEMA_DRIFT.value,
            "root_cause": root_cause,
            "explanation": "stg_customers references id; raw_customers seed renamed it.",
            "confidence": confidence,
            "proposed_fix": {
                "rationale": "Replace `id as customer_id` with `customer_id`.",
                "diff": (
                    "--- a/models/staging/stg_customers.sql\n"
                    "+++ b/models/staging/stg_customers.sql\n"
                    "@@ -1 +1 @@\n"
                    "-        id as customer_id,\n"
                    "+        customer_id,\n"
                ),
            },
        },
    )


def _read_file_call(call_id: str, path: str) -> ToolCallBlock:
    return ToolCallBlock(id=call_id, name="read_file", input={"path": path})


# ────────────────────────────────────────────────────────────────────────
# Happy-path: the model submits diagnosis on the first turn
# ────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_terminal_call_on_first_turn_ends_run(tmp_path: Path) -> None:
    incident = _incident()
    provider = MockProvider(
        completions=[make_completion(tool_calls=[_terminal_call()])],
    )
    run = await bench_run(incident=incident, project_root=tmp_path, provider=provider)

    assert run.stop_reason is AgentStopReason.DIAGNOSIS_SUBMITTED
    assert run.final_diagnosis is not None
    assert run.final_diagnosis.failure_class is FailureClass.SCHEMA_DRIFT
    assert run.final_diagnosis.confidence == pytest.approx(0.95)
    assert run.final_fix is not None
    assert "customer_id" in run.final_fix.diff
    assert len(run.iterations) == 1
    assert provider.remaining == 0


# ────────────────────────────────────────────────────────────────────────
# read_file dispatch — model asks for a file, gets content, then submits
# ────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_read_file_loop_then_submit(tmp_path: Path) -> None:
    (tmp_path / "models/staging").mkdir(parents=True)
    (tmp_path / "models/staging/stg_customers.sql").write_text(
        "select id as customer_id from {{ ref('raw_customers') }}\n",
    )

    incident = _incident()
    provider = MockProvider(
        completions=[
            # Turn 1: model asks for the file
            make_completion(
                tool_calls=[_read_file_call("tu_1", "models/staging/stg_customers.sql")],
                stop_reason="tool_use",
            ),
            # Turn 2: model submits diagnosis
            make_completion(tool_calls=[_terminal_call()]),
        ],
    )

    run = await bench_run(incident=incident, project_root=tmp_path, provider=provider)

    assert run.stop_reason is AgentStopReason.DIAGNOSIS_SUBMITTED
    assert len(run.iterations) == 2
    assert run.iterations[0].tool_calls[0].name == "read_file"
    assert not run.iterations[0].tool_results[0].is_error
    # The file's actual content should have been returned to the model
    assert "customer_id" in run.iterations[0].tool_results[0].content


# ────────────────────────────────────────────────────────────────────────
# Lab-leak filter integration — read_file refuses scenarios/expected.yaml
# ────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_read_file_denies_lab_artifact(tmp_path: Path) -> None:
    (tmp_path / "scenarios/01-schema-drift").mkdir(parents=True)
    (tmp_path / "scenarios/01-schema-drift/expected.yaml").write_text("answer: secret\n")

    incident = _incident()
    provider = MockProvider(
        completions=[
            make_completion(
                tool_calls=[_read_file_call("tu_1", "scenarios/01-schema-drift/expected.yaml")],
                stop_reason="tool_use",
            ),
            make_completion(tool_calls=[_terminal_call()]),
        ],
    )

    run = await bench_run(incident=incident, project_root=tmp_path, provider=provider)

    # First iteration's read_file got denied
    first = run.iterations[0]
    assert first.tool_results[0].is_error
    assert "Access denied" in first.tool_results[0].content
    # Crucially, the actual file content did NOT leak through
    assert "secret" not in first.tool_results[0].content


# ────────────────────────────────────────────────────────────────────────
# Unknown tool — model can recover next turn
# ────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_unknown_tool_surfaces_error_then_recovers(tmp_path: Path) -> None:
    incident = _incident()
    provider = MockProvider(
        completions=[
            make_completion(
                tool_calls=[
                    ToolCallBlock(
                        id="tu_bogus",
                        name="run_sql",  # not a tool we expose
                        input={"query": "select 1"},
                    ),
                ],
                stop_reason="tool_use",
            ),
            make_completion(tool_calls=[_terminal_call()]),
        ],
    )

    run = await bench_run(incident=incident, project_root=tmp_path, provider=provider)

    assert run.stop_reason is AgentStopReason.DIAGNOSIS_SUBMITTED
    err_result = run.iterations[0].tool_results[0]
    assert err_result.is_error
    assert "unknown tool: run_sql" in err_result.content
    assert "read_file" in err_result.content  # tells the model what IS available


# ────────────────────────────────────────────────────────────────────────
# Stop conditions — max iterations, no progress, cost cap
# ────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_max_iterations_when_model_keeps_reading_files(tmp_path: Path) -> None:
    (tmp_path / "dbt_project.yml").write_text("name: demo\n")
    incident = _incident()
    # Model loops forever asking for the same file
    provider = MockProvider(
        completions=[
            make_completion(
                tool_calls=[_read_file_call(f"tu_{i}", "dbt_project.yml")],
                stop_reason="tool_use",
            )
            for i in range(5)
        ],
    )

    run = await bench_run(
        incident=incident,
        project_root=tmp_path,
        provider=provider,
        max_iterations=5,
    )

    assert run.stop_reason is AgentStopReason.MAX_ITERATIONS
    assert len(run.iterations) == 5
    assert run.final_diagnosis is None


@pytest.mark.asyncio
async def test_no_tool_calls_and_no_diagnosis_is_error(tmp_path: Path) -> None:
    incident = _incident()
    provider = MockProvider(
        completions=[make_completion(text="I don't know.", tool_calls=[])],
    )

    run = await bench_run(incident=incident, project_root=tmp_path, provider=provider)

    assert run.stop_reason is AgentStopReason.ERROR
    assert run.error is not None
    assert "no tool calls" in run.error
    assert run.final_diagnosis is None


@pytest.mark.asyncio
async def test_cost_cap_halts_before_max_iterations(tmp_path: Path) -> None:
    (tmp_path / "dbt_project.yml").write_text("name: demo\n")
    incident = _incident()
    expensive = make_completion(
        tool_calls=[_read_file_call("tu_1", "dbt_project.yml")],
        cost_usd=0.10,
        stop_reason="tool_use",
    )
    provider = MockProvider(completions=[expensive] * 10)

    run = await bench_run(
        incident=incident,
        project_root=tmp_path,
        provider=provider,
        max_iterations=10,
        max_cost_usd=0.25,
    )

    # 0.10 + 0.10 + 0.10 = 0.30 → after the 3rd call total >= 0.25 cap → stop
    assert run.stop_reason is AgentStopReason.COST_CAP
    assert len(run.iterations) == 3
    assert run.total_cost_usd >= 0.25
