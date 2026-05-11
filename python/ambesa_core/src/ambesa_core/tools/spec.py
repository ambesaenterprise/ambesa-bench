# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Ambesa Enterprise Ltd.

"""Tool spec — the JSON schema the model sees + the Python callable behind it.

Each per-tool module exposes a top-level ``SPEC: ToolSpec`` constant. Tools
are wired into an agent loop by importing the relevant ``SPEC`` constants
directly; there is no global registry and no import-as-side-effect.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from pydantic import BaseModel, Field

from ambesa_core.tools.context import ToolContext


class Tool(Protocol):
    """A tool implementation: context + arguments → string result."""

    async def __call__(self, ctx: ToolContext, **kwargs: Any) -> str: ...


class ToolSpec(BaseModel):
    """Combined spec: schema for the model + the implementation we dispatch to."""

    model_config = {"arbitrary_types_allowed": True}

    name: str
    description: str
    input_schema: dict[str, Any]
    impl: Callable[..., Awaitable[str]] = Field(exclude=True)

    def to_anthropic_tool(self) -> dict[str, Any]:
        """Render in Anthropic's tool-use schema."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }
