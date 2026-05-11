# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Ambesa Enterprise Ltd.

"""Core domain types.

These types are deliberately dependency-free at the package boundary —
they import from ``ambesa_core.tools.tool_types`` (also pure data) but
not from anything that drags in a particular agent-loop implementation
or vendor SDK. That shape lets ``ambesa_core.eval`` and ``ambesa_bench``
consume the data shapes without inheriting heavier dependencies.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from ambesa_core.tools.tool_types import ToolCall, ToolResult


class FailureClass(StrEnum):
    """Canonical taxonomy of dbt failure modes.

    Mirrors ``packages/types/src/failure-class.ts::FailureClass``.
    """

    SCHEMA_DRIFT = "schema_drift"
    TYPE_MISMATCH = "type_mismatch"
    NULL_VIOLATION = "null_violation"
    MISSING_SOURCE = "missing_source"
    STALE_REF = "stale_ref"
    CAST_FAILURE = "cast_failure"
    PERMISSIONS = "permissions"
    LOGIC = "logic"
    UNKNOWN = "unknown"


# v1 scope — the agent only attempts fixes for these.
V1_SUPPORTED_CLASSES: frozenset[FailureClass] = frozenset(
    {FailureClass.SCHEMA_DRIFT, FailureClass.TYPE_MISMATCH, FailureClass.NULL_VIOLATION},
)


class FailingModel(BaseModel):
    """A single failed dbt model extracted from run_results.json."""

    unique_id: str
    name: str
    relation_name: str | None = None
    error: str
    raw_status: str
    failure_class_hint: FailureClass = FailureClass.UNKNOWN


class Incident(BaseModel):
    """A diagnosable failure, with all the context the agent needs to reason."""

    id: UUID
    tenant_id: UUID | Literal["local"] = "local"
    repo_full_name: str
    commit_sha: str
    failing_model: FailingModel
    manifest_excerpt: dict[str, Any] | None = None
    recent_commits: list[dict[str, Any]] = Field(default_factory=list)
    detected_at: datetime


class TokenUsage(BaseModel):
    """LLM token accounting for a single call."""

    prompt: int
    cached: int = 0
    completion: int


class Prompt(BaseModel):
    """A structured LLM prompt with explicit cache breakpoints.

    The provider implementation translates this into provider-specific
    request shapes (e.g., Anthropic's prompt-caching markers).
    """

    version: str
    system: str
    static_context: str = ""
    dynamic_context: str = ""
    instruction: str
    purpose: str


class Diagnosis(BaseModel):
    """The agent's hypothesis about why an incident happened."""

    incident_id: UUID
    failure_class: FailureClass
    root_cause: str
    explanation: str
    confidence: float = Field(ge=0.0, le=1.0)
    prompt_version: str
    model: str
    token_usage: TokenUsage
    cost_usd: float
    latency_ms: int


# ────────────────────────────────────────────────────────────────────────
# Agent run shapes — the data an agent loop produces on each diagnosis.
# Kept in this module so both ``ambesa_core.eval`` and ``ambesa_bench``
# can grade against the shape without inheriting an agent-loop dependency.
# ────────────────────────────────────────────────────────────────────────


class AgentStopReason(StrEnum):
    """Why an :class:`AgentRun` ended."""

    DIAGNOSIS_SUBMITTED = "diagnosis_submitted"
    MAX_ITERATIONS = "max_iterations"
    COST_CAP = "cost_cap"
    ERROR = "error"


class AgentIteration(BaseModel):
    """One round-trip: LLM call + dispatched tool calls."""

    n: int
    model: str
    prompt_tokens: int
    cached_tokens: int = 0
    completion_tokens: int
    cost_usd: float
    latency_ms: int
    tool_calls: list[ToolCall] = Field(default_factory=list)
    tool_results: list[ToolResult] = Field(default_factory=list)
    text: str = ""


class FixProposal(BaseModel):
    """Concrete fix proposed alongside the diagnosis."""

    rationale: str
    diff: str


class AgentRun(BaseModel):
    """A complete agent execution — the unit of trace, billing, and learning."""

    id: UUID = Field(default_factory=uuid4)
    incident_id: UUID | Literal["local"] = "local"
    tenant_id: UUID | Literal["local"] = "local"
    started_at: datetime
    ended_at: datetime | None = None
    iterations: list[AgentIteration] = Field(default_factory=list)
    final_diagnosis: Diagnosis | None = None
    final_fix: FixProposal | None = None
    total_token_usage: TokenUsage = Field(
        default_factory=lambda: TokenUsage(prompt=0, cached=0, completion=0),
    )
    total_cost_usd: float = 0.0
    stop_reason: AgentStopReason | None = None
    error: str | None = None


__all__ = [
    "V1_SUPPORTED_CLASSES",
    "AgentIteration",
    "AgentRun",
    "AgentStopReason",
    "Diagnosis",
    "FailingModel",
    "FailureClass",
    "FixProposal",
    "Incident",
    "Prompt",
    "TokenUsage",
    "ToolCall",
    "ToolResult",
]
