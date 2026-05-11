# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Ambesa Enterprise Ltd.

"""Stripped reference agent — the minimal example that scores against
ambesa-bench scenarios.

This agent uses two evidence-gathering tools (``read_file`` and
``read_manifest_node``), a terminal ``submit_diagnosis`` sentinel, and a
vendor-neutral :class:`ambesa_core.llm.LLMProvider` abstraction. It is
intentionally minimal — Ambesa's hosted production agent uses a richer
tool stack and a tuned prompt, and lives behind the cloud product. The
bench reference exists so anyone reading the benchmark has a working
baseline to reproduce locally and improve on.

Returns an :class:`ambesa_core.types.AgentRun` in the same shape the public
:func:`ambesa_core.eval.grader.grade` consumes — the bench runner grades
this output against the scenario's ``expected.yaml`` golden contract.

Usage from another agent:

    from ambesa_bench import run

    agent_run = await run(
        incident=my_incident,
        project_root=Path("/tmp/snapshot"),
        provider=my_llm_provider,
    )

The loop body below is short and read-top-down by design; copy it as the
template for richer agents that swap in their own prompts, tools, or
control flow.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ambesa_bench._prompt import PROMPT_VERSION, build_prompt
from ambesa_core.llm import CachePolicy, LLMProvider, ModelId
from ambesa_core.tools.context import ToolContext
from ambesa_core.tools.read_file import read_file as read_file_tool
from ambesa_core.tools.read_manifest_node import (
    read_manifest_node as read_manifest_node_tool,
)
from ambesa_core.types import (
    AgentIteration,
    AgentRun,
    AgentStopReason,
    Diagnosis,
    FailureClass,
    FixProposal,
    Incident,
    TokenUsage,
    ToolCall,
    ToolResult,
)

_TERMINAL_TOOL = "submit_diagnosis"
_READ_FILE_TOOL = "read_file"
_READ_MANIFEST_NODE_TOOL = "read_manifest_node"


_READ_FILE_TOOL_SPEC: dict[str, Any] = {
    "name": _READ_FILE_TOOL,
    "description": (
        "Read a file from the dbt project. Path is project-relative "
        "(e.g. 'models/staging/stg_customers.sql', 'seeds/raw_customers.csv', "
        "'dbt_project.yml'). Returns file text, or an <error> sentinel if "
        "the path doesn't exist or is denied (eval-harness artifacts are "
        "denied — diagnose from the real project state, not the answer key)."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Project-relative file path.",
            },
        },
        "required": ["path"],
    },
}


_READ_MANIFEST_NODE_TOOL_SPEC: dict[str, Any] = {
    "name": _READ_MANIFEST_NODE_TOOL,
    "description": (
        "Look up a node in dbt's manifest by unique_id "
        "(e.g. 'model.jaffle_shop.stg_customers' or 'source.jaffle_shop.raw.raw_customers'). "
        "Returns columns, compiled SQL, depends_on, and original_file_path — "
        "use this to localize which model file is the right place to fix, vs "
        "which files (sources, seeds-as-sources) you should NOT touch."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "unique_id": {
                "type": "string",
                "description": "Dbt manifest unique_id of the node.",
            },
        },
        "required": ["unique_id"],
    },
}


_SUBMIT_DIAGNOSIS_TOOL_SPEC: dict[str, Any] = {
    "name": _TERMINAL_TOOL,
    "description": (
        "Submit your final diagnosis. Call this exactly once when you have "
        "gathered enough evidence to commit to a root cause. Include a "
        "concrete unified-diff proposed_fix when the failure_class is one "
        "you can safely repair; pass null otherwise."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "failure_class": {
                "type": "string",
                "enum": [c.value for c in FailureClass],
            },
            "root_cause": {
                "type": "string",
                "description": "One sentence.",
            },
            "explanation": {
                "type": "string",
                "description": "2-4 sentences citing evidence from files you read.",
            },
            "confidence": {
                "type": "number",
                "minimum": 0,
                "maximum": 1,
            },
            "proposed_fix": {
                "anyOf": [
                    {
                        "type": "object",
                        "properties": {
                            "rationale": {"type": "string"},
                            "diff": {
                                "type": "string",
                                "description": (
                                    "Unified diff that applies cleanly with `git apply`."
                                ),
                            },
                        },
                        "required": ["rationale", "diff"],
                    },
                    {"type": "null"},
                ],
            },
        },
        "required": ["failure_class", "root_cause", "explanation", "confidence"],
    },
}


# Loop knobs — exposed as kwargs on `run()` for callers who need to tune
# them per-scenario or per-vendor. Defaults are tuned to grade green on
# the four scenarios shipped with ambesa-bench.
_DEFAULT_MAX_ITERATIONS = 10
_DEFAULT_MAX_COST_USD = 0.50
_DEFAULT_MAX_TOKENS_PER_CALL = 2048


async def run(  # noqa: PLR0915 — orchestrator naturally has many statements; splitting would obscure the read-top-down loop shape that's the point of a reference impl
    *,
    incident: Incident,
    project_root: str | Path,
    provider: LLMProvider,
    model: ModelId = ModelId.CLAUDE_SONNET_4_6,
    max_iterations: int = _DEFAULT_MAX_ITERATIONS,
    max_cost_usd: float = _DEFAULT_MAX_COST_USD,
    max_tokens_per_call: int = _DEFAULT_MAX_TOKENS_PER_CALL,
    cache: CachePolicy = CachePolicy.AGGRESSIVE,
) -> AgentRun:
    """Drive the reference loop until it submits a diagnosis or stops.

    Returns a fully-traced ``AgentRun`` regardless of outcome — caller
    inspects ``stop_reason`` to know what happened.
    """
    project_root_p = Path(str(project_root)).resolve()
    ctx = ToolContext(
        project_root=project_root_p,
        target_dir=project_root_p / "target",
    )

    prompt = build_prompt(incident)

    run_record = AgentRun(
        incident_id=incident.id,
        tenant_id=incident.tenant_id,
        started_at=datetime.now(UTC),
    )

    user_open_text = (
        f"{prompt.dynamic_context}\n\n{prompt.instruction}"
        if prompt.dynamic_context
        else prompt.instruction
    )
    messages: list[dict[str, Any]] = [
        {"role": "user", "content": user_open_text},
    ]
    tools_payload = [
        _READ_FILE_TOOL_SPEC,
        _READ_MANIFEST_NODE_TOOL_SPEC,
        _SUBMIT_DIAGNOSIS_TOOL_SPEC,
    ]

    for iter_n in range(1, max_iterations + 1):
        # Cost cap before the next call (post-hoc check).
        if run_record.total_cost_usd >= max_cost_usd:
            run_record.stop_reason = AgentStopReason.COST_CAP
            break

        completion = await provider.complete(
            prompt=prompt,
            model=model,
            max_tokens=max_tokens_per_call,
            cache=cache,
            tenant_id=str(incident.tenant_id),
            purpose=prompt.purpose,
            tools=tools_payload,
            messages=messages,
            tool_choice="auto",
        )

        iteration = AgentIteration(
            n=iter_n,
            model=model.value,
            prompt_tokens=completion.token_usage.prompt,
            cached_tokens=completion.token_usage.cached,
            completion_tokens=completion.token_usage.completion,
            cost_usd=completion.cost_usd,
            latency_ms=completion.latency_ms,
            text=completion.text,
        )
        run_record.iterations.append(iteration)
        run_record.total_token_usage = TokenUsage(
            prompt=run_record.total_token_usage.prompt + completion.token_usage.prompt,
            cached=run_record.total_token_usage.cached + completion.token_usage.cached,
            completion=run_record.total_token_usage.completion + completion.token_usage.completion,
        )
        run_record.total_cost_usd += completion.cost_usd

        # Did the model submit a diagnosis?
        terminal_call = next(
            (c for c in completion.tool_calls if c.name == _TERMINAL_TOOL),
            None,
        )
        if terminal_call is not None:
            args = terminal_call.input
            run_record.final_diagnosis = Diagnosis(
                incident_id=incident.id,
                failure_class=FailureClass(args["failure_class"]),
                root_cause=args["root_cause"],
                explanation=args["explanation"],
                confidence=float(args["confidence"]),
                prompt_version=PROMPT_VERSION,
                model=model.value,
                token_usage=run_record.total_token_usage,
                cost_usd=run_record.total_cost_usd,
                latency_ms=sum(it.latency_ms for it in run_record.iterations),
            )
            fix_args = args.get("proposed_fix")
            if isinstance(fix_args, dict):
                run_record.final_fix = FixProposal(
                    rationale=fix_args["rationale"],
                    diff=fix_args["diff"],
                )
            run_record.stop_reason = AgentStopReason.DIAGNOSIS_SUBMITTED
            break

        # No tool calls and no terminal — model gave up.
        if not completion.tool_calls:
            run_record.stop_reason = AgentStopReason.ERROR
            run_record.error = "model returned no tool calls and no diagnosis"
            break

        # Dispatch every tool call (read_file + read_manifest_node are the
        # valid ones; anything else gets an explicit error result so the
        # model can course-correct on the next turn).
        tool_calls: list[ToolCall] = []
        tool_results: list[ToolResult] = []
        for tc in completion.tool_calls:
            tool_calls.append(ToolCall(id=tc.id, name=tc.name, arguments=tc.input))
            if tc.name == _READ_FILE_TOOL:
                path = str(tc.input.get("path", ""))
                content = await read_file_tool(ctx, path)
                tool_results.append(
                    ToolResult(
                        tool_use_id=tc.id,
                        content=content,
                        is_error=content.startswith("<error>"),
                        latency_ms=0,
                    ),
                )
            elif tc.name == _READ_MANIFEST_NODE_TOOL:
                unique_id = str(tc.input.get("unique_id", ""))
                content = await read_manifest_node_tool(ctx, unique_id)
                tool_results.append(
                    ToolResult(
                        tool_use_id=tc.id,
                        content=content,
                        is_error=content.startswith("<error>"),
                        latency_ms=0,
                    ),
                )
            else:
                tool_results.append(
                    ToolResult(
                        tool_use_id=tc.id,
                        content=(
                            f"<error>unknown tool: {tc.name}; only "
                            f"{_READ_FILE_TOOL}, {_READ_MANIFEST_NODE_TOOL}, "
                            f"and {_TERMINAL_TOOL} are available</error>"
                        ),
                        is_error=True,
                        latency_ms=0,
                    ),
                )

        iteration.tool_calls = tool_calls
        iteration.tool_results = tool_results

        # Append the assistant turn (text + tool_use blocks) and the user
        # tool_result blocks for the next iteration's context.
        assistant_blocks: list[dict[str, Any]] = []
        if completion.text:
            assistant_blocks.append({"type": "text", "text": completion.text})
        for tc in completion.tool_calls:
            assistant_blocks.append(
                {
                    "type": "tool_use",
                    "id": tc.id,
                    "name": tc.name,
                    "input": tc.input,
                },
            )
        messages.append({"role": "assistant", "content": assistant_blocks})
        messages.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": r.tool_use_id,
                        "content": r.content,
                        "is_error": r.is_error,
                    }
                    for r in tool_results
                ],
            },
        )

    if run_record.stop_reason is None:
        run_record.stop_reason = AgentStopReason.MAX_ITERATIONS
    run_record.ended_at = datetime.now(UTC)
    return run_record


__all__ = ["run"]
