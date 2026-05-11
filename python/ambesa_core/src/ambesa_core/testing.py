# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Ambesa Enterprise Ltd.

"""Test helpers — :class:`MockProvider` for replaying recorded conversations.

Every Anthropic call in unit tests goes through this. The live API is never
called on a code path the agent loop drives. Recordings live next to the
tests that use them as JSON fixtures.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from os import PathLike
from pathlib import Path
from typing import Any, Literal

from ambesa_core._errors import ConfigError
from ambesa_core.llm import (
    CachePolicy,
    Completion,
    LLMProvider,
    ModelId,
    ToolCallBlock,
)
from ambesa_core.types import Prompt, TokenUsage


class MockProvider(LLMProvider):
    """An LLMProvider that returns pre-canned :class:`Completion` objects.

    Construct with a list of completions; each :meth:`complete` call pops
    the next one. Raises if you run out of canned responses (i.e. the
    agent loop made more calls than the recording covers — a real bug).
    """

    def __init__(self, completions: Sequence[Completion]) -> None:
        self._queue: list[Completion] = list(completions)
        self.call_log: list[dict[str, Any]] = []

    async def complete(
        self,
        *,
        prompt: Prompt,
        model: ModelId,
        max_tokens: int,
        cache: CachePolicy,
        tenant_id: str,
        purpose: str,
        tools: Sequence[dict[str, Any]] | None = None,
        messages: Sequence[dict[str, Any]] | None = None,
        tool_choice: Literal["auto", "any"] | None = None,
    ) -> Completion:
        self.call_log.append(
            {
                "prompt_version": prompt.version,
                "model": model.value,
                "max_tokens": max_tokens,
                "cache": cache.value,
                "tenant_id": tenant_id,
                "purpose": purpose,
                "tool_count": len(tools) if tools else 0,
                "message_turns": len(messages) if messages else 0,
                "tool_choice": tool_choice,
            },
        )
        if not self._queue:
            raise ConfigError(
                "MockProvider exhausted — agent made more LLM calls than the "
                f"recording covers (logged {len(self.call_log)} calls).",
            )
        return self._queue.pop(0)

    @property
    def remaining(self) -> int:
        return len(self._queue)


def make_completion(
    *,
    text: str = "",
    model: ModelId = ModelId.CLAUDE_SONNET_4_6,
    tool_calls: Sequence[ToolCallBlock] = (),
    stop_reason: str = "end_turn",
    prompt_tokens: int = 100,
    cached_tokens: int = 0,
    completion_tokens: int = 50,
    cost_usd: float = 0.001,
    latency_ms: int = 100,
) -> Completion:
    """Convenience builder for hand-written test fixtures."""
    return Completion(
        text=text,
        model=model,
        token_usage=TokenUsage(
            prompt=prompt_tokens,
            cached=cached_tokens,
            completion=completion_tokens,
        ),
        cost_usd=cost_usd,
        latency_ms=latency_ms,
        stop_reason=stop_reason,
        tool_calls=list(tool_calls),
        raw={},
    )


def completions_from_agent_run(path: str | PathLike[str]) -> list[Completion]:
    """Reconstruct ``list[Completion]`` from a recorded ``AgentRun`` JSON.

    Pair with :class:`MockProvider` to feed the same model decisions back
    into the agent loop in a replay test. Tools are still dispatched live,
    so the test exercises the loop AND the tool surface — only the model
    is frozen.

    The agent loop's per-iteration ``tool_calls`` field captures only the
    evidence-gathering calls (read_file / read_manifest_node), not the
    terminal ``submit_diagnosis`` call that triggers loop exit. When the
    recording's top-level ``final_diagnosis`` is populated, a synthetic
    final completion with a ``submit_diagnosis`` tool_use block is appended
    so replay reaches the same DIAGNOSIS_SUBMITTED stop reason.
    """
    data = json.loads(Path(path).read_text())
    iterations = data["iterations"]
    final_diag = data.get("final_diagnosis")
    final_fix = data.get("final_fix")
    last_index = len(iterations) - 1

    terminal_block: ToolCallBlock | None = None
    if final_diag:
        terminal_input: dict[str, Any] = {
            "failure_class": final_diag["failure_class"],
            "root_cause": final_diag["root_cause"],
            "explanation": final_diag["explanation"],
            "confidence": final_diag["confidence"],
        }
        if isinstance(final_fix, dict):
            terminal_input["proposed_fix"] = {
                "rationale": final_fix.get("rationale", ""),
                "diff": final_fix.get("diff", ""),
            }
        terminal_block = ToolCallBlock(
            id="toolu_replay_submit",
            name="submit_diagnosis",
            input=terminal_input,
        )

    completions: list[Completion] = []
    for idx, it in enumerate(iterations):
        tool_calls = [
            ToolCallBlock(id=tc["id"], name=tc["name"], input=tc["arguments"])
            for tc in it.get("tool_calls", [])
        ]
        is_last = idx == last_index
        has_terminal = any(tc.name == "submit_diagnosis" for tc in tool_calls)
        if is_last and terminal_block is not None and not has_terminal:
            tool_calls.append(terminal_block)

        completions.append(
            Completion(
                text=it.get("text", ""),
                model=ModelId(it["model"]),
                token_usage=TokenUsage(
                    prompt=it["prompt_tokens"],
                    cached=it.get("cached_tokens", 0),
                    completion=it["completion_tokens"],
                ),
                cost_usd=it["cost_usd"],
                latency_ms=it["latency_ms"],
                stop_reason="tool_use" if tool_calls else "end_turn",
                tool_calls=tool_calls,
                raw={},
            ),
        )
    return completions


__all__ = ["MockProvider", "completions_from_agent_run", "make_completion"]
