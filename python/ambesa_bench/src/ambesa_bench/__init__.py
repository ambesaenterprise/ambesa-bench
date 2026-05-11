# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Ambesa Enterprise Ltd.

"""ambesa-bench — public reference adapter for the dbt-diagnosis benchmark.

The reference agent and bench runner live here. Both depend only on the
public-safe surface of ``ambesa_core`` (types, eval, tools.read_file,
llm.LLMProvider) — never on the production agent loop, prompts, or the
multi-tool dispatcher.
"""

from __future__ import annotations

from ambesa_bench.reference_agent import run

__all__ = ["run"]
