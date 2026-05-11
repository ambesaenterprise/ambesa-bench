# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Ambesa Enterprise Ltd.

"""LLM provider abstraction — the chokepoint for every model call.

Every LLM call in the codebase goes through ``LLMProvider``. Keeping the
abstraction single-entry makes the agent loop model-agnostic, isolates the
vendor SDK to one place, and makes cost / latency observability uniform.
"""

from __future__ import annotations

import os
import time
from collections.abc import Sequence
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Literal, Protocol, cast, runtime_checkable

import structlog
from anthropic import AsyncAnthropic
from anthropic.types import Message as AnthropicMessage
from anthropic.types import TextBlock, ToolUseBlock
from pydantic import BaseModel, Field

from ambesa_core._errors import ConfigError, LLMError
from ambesa_core.types import Prompt, TokenUsage

if TYPE_CHECKING:
    from anthropic.types import MessageParam, TextBlockParam, ToolParam

log = structlog.get_logger(__name__)


class CachePolicy(StrEnum):
    """Prompt-caching strategy for an LLM call."""

    NONE = "none"
    AGGRESSIVE = "aggressive"  # cache static context block (~5min Anthropic TTL)


class ModelId(StrEnum):
    """Models we currently support. Adding a new one requires a code change.

    Pricing as of 2026-05; verify before changes.
    """

    CLAUDE_OPUS_4_7 = "claude-opus-4-7"
    CLAUDE_SONNET_4_6 = "claude-sonnet-4-6"
    CLAUDE_HAIKU_4_5 = "claude-haiku-4-5-20251001"


# Cost per 1M tokens (USD). Numbers are illustrative; refresh from billing periodically.
_PRICING: dict[ModelId, tuple[float, float, float]] = {
    # (prompt, cached_read, completion) per 1M tokens
    ModelId.CLAUDE_OPUS_4_7: (15.00, 1.50, 75.00),
    ModelId.CLAUDE_SONNET_4_6: (3.00, 0.30, 15.00),
    ModelId.CLAUDE_HAIKU_4_5: (1.00, 0.10, 5.00),
}


class ToolCallBlock(BaseModel):
    """A tool_use block returned by the model."""

    id: str
    name: str
    input: dict[str, Any]


class Completion(BaseModel):
    """Result of a single LLM call.

    For tool-using calls, ``stop_reason`` distinguishes between "model wants
    tools run" vs. "model is done", and ``tool_calls`` lists what was asked.
    """

    text: str
    model: ModelId
    token_usage: TokenUsage
    cost_usd: float
    latency_ms: int
    stop_reason: str = ""
    tool_calls: list[ToolCallBlock] = Field(default_factory=list)
    raw: dict[str, Any]


@runtime_checkable
class LLMProvider(Protocol):
    """The single abstraction every LLM-calling code path uses."""

    async def complete(
        self,
        *,
        prompt: Prompt,
        model: ModelId,
        max_tokens: int,
        cache: CachePolicy,
        tenant_id: str,
        purpose: str,
        tools: Sequence[dict[str, Any]] | None = ...,
        messages: Sequence[dict[str, Any]] | None = ...,
        tool_choice: Literal["auto", "any"] | None = ...,
    ) -> Completion: ...


def _estimate_cost(model: ModelId, usage: TokenUsage) -> float:
    rates = _PRICING.get(model)
    if rates is None:
        return 0.0
    in_rate, cached_rate, out_rate = rates
    uncached_prompt = max(0, usage.prompt - usage.cached)
    return (
        (uncached_prompt / 1_000_000) * in_rate
        + (usage.cached / 1_000_000) * cached_rate
        + (usage.completion / 1_000_000) * out_rate
    )


class AnthropicProvider:
    """v1 LLMProvider implementation backed by the Anthropic SDK."""

    def __init__(self, *, api_key: str | None = None) -> None:
        key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise ConfigError("ANTHROPIC_API_KEY is not set")
        self._client = AsyncAnthropic(api_key=key)

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
        bound = log.bind(
            tenant_id=tenant_id,
            purpose=purpose,
            model=model.value,
            prompt_version=prompt.version,
            cache=cache.value,
            tool_count=len(tools) if tools else 0,
            message_turns=len(messages) if messages else 0,
        )
        bound.info("llm.complete.start")

        # Construct the system block. With AGGRESSIVE caching we mark the
        # static context as a cache breakpoint so subsequent calls within
        # ~5min reuse it for ~10x cheaper input tokens.
        system_blocks: list[dict[str, Any]] = [{"type": "text", "text": prompt.system}]
        if prompt.static_context:
            block: dict[str, Any] = {"type": "text", "text": prompt.static_context}
            if cache is CachePolicy.AGGRESSIVE:
                block["cache_control"] = {"type": "ephemeral"}
            system_blocks.append(block)

        # If caller didn't supply messages, fall back to the single-shot
        # prompt shape (dynamic + instruction). This keeps single-shot
        # callers working unchanged.
        if messages is None:
            user_text = (
                f"{prompt.dynamic_context}\n\n{prompt.instruction}"
                if prompt.dynamic_context
                else prompt.instruction
            )
            built_messages: list[dict[str, Any]] = [{"role": "user", "content": user_text}]
        else:
            built_messages = list(messages)

        started = time.perf_counter()
        resp: AnthropicMessage
        try:
            if tools:
                tool_choice_param: dict[str, str] = (
                    {"type": "any"} if tool_choice == "any" else {"type": "auto"}
                )
                resp = await self._client.messages.create(
                    model=model.value,
                    max_tokens=max_tokens,
                    system=cast("list[TextBlockParam]", system_blocks),
                    messages=cast("list[MessageParam]", built_messages),
                    tools=cast("list[ToolParam]", list(tools)),
                    tool_choice=cast("Any", tool_choice_param),
                )
            else:
                resp = await self._client.messages.create(
                    model=model.value,
                    max_tokens=max_tokens,
                    system=cast("list[TextBlockParam]", system_blocks),
                    messages=cast("list[MessageParam]", built_messages),
                )
        except Exception as exc:
            bound.error("llm.complete.error", error=str(exc))
            raise LLMError(f"Anthropic call failed: {exc}") from exc

        latency_ms = int((time.perf_counter() - started) * 1000)

        text_parts: list[str] = []
        tool_calls: list[ToolCallBlock] = []
        for raw_block in resp.content:
            if isinstance(raw_block, TextBlock):
                text_parts.append(raw_block.text)
            elif isinstance(raw_block, ToolUseBlock):
                tool_calls.append(
                    ToolCallBlock(
                        id=raw_block.id,
                        name=raw_block.name,
                        input=(dict(raw_block.input) if isinstance(raw_block.input, dict) else {}),
                    ),
                )

        usage = TokenUsage(
            prompt=resp.usage.input_tokens,
            cached=getattr(resp.usage, "cache_read_input_tokens", 0) or 0,
            completion=resp.usage.output_tokens,
        )
        cost = _estimate_cost(model, usage)

        bound.info(
            "llm.complete.ok",
            prompt_tokens=usage.prompt,
            cached_tokens=usage.cached,
            completion_tokens=usage.completion,
            cost_usd=round(cost, 6),
            latency_ms=latency_ms,
            stop_reason=resp.stop_reason or "",
            tool_calls=len(tool_calls),
        )

        return Completion(
            text="".join(text_parts),
            model=model,
            token_usage=usage,
            cost_usd=cost,
            latency_ms=latency_ms,
            stop_reason=resp.stop_reason or "",
            tool_calls=tool_calls,
            raw=resp.model_dump(),
        )


def get_provider(name: str = "anthropic") -> LLMProvider:
    """Factory — extension point when we add OpenAI / open-source providers."""
    if name == "anthropic":
        return AnthropicProvider()
    raise ConfigError(f"Unknown LLM provider: {name}")
