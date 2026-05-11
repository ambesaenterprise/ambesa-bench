# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Ambesa Enterprise Ltd.

"""Shared types for the tool layer.

These are the wire types between the agent loop and the dispatcher. Kept
here (rather than in ``ambesa_core.agent``) to avoid the circular import
that would result from the dispatcher needing them: tools is a leaf, agent
sits above it.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ToolCall(BaseModel):
    """A single tool invocation requested by the model."""

    id: str
    name: str
    arguments: dict[str, Any]


class ToolResult(BaseModel):
    """The dispatcher's response to a single ``ToolCall``."""

    tool_use_id: str
    content: str
    is_error: bool = False
    latency_ms: int = 0
