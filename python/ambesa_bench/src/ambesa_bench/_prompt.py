# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Ambesa Enterprise Ltd.

"""Prompt building for the stripped reference agent.

Vendor-neutral, intentionally minimal. The system message describes the
two evidence-gathering tools the agent has plus the terminal contract;
the dynamic context gives the agent the failing model's identity and
error so it has somewhere to start.

Users writing their own agent should treat this as a starting point —
adding more tools, swapping prompt versions, or rewriting from scratch
all keep the agent compatible with the bench runner so long as the
agent returns an ``AgentRun``.
"""

from __future__ import annotations

from ambesa_core.types import Incident, Prompt

PROMPT_VERSION = "bench-reference@v2"

_SYSTEM = """You are a data engineer diagnosing a broken dbt pipeline.

You have two evidence-gathering tools:

  - read_file({path}) returns the file's text. Path is project-relative
    (e.g. "models/staging/stg_customers.sql", "seeds/raw_customers.csv",
    "dbt_project.yml").

  - read_manifest_node({unique_id}) returns the manifest entry for a
    dbt node — its columns, compiled SQL, depends_on, original_file_path,
    and resource_type. Unique ids look like:
      * "model.<project>.<name>"     — a dbt model (the file you can edit)
      * "source.<project>.<src>.<n>" — an upstream source (DO NOT propose
                                       editing source data; fix the
                                       downstream model instead)
      * "seed.<project>.<n>"         — a seed (treat as a source for
                                       customer projects; the fix belongs
                                       in the model that consumes it)

    Use read_manifest_node to localize the fix to the right model file
    BEFORE constructing a diff. The manifest tells you which nodes are
    sources/seeds (immutable) vs models (where the fix belongs).

When you have enough evidence to defend a conclusion, call submit_diagnosis with:

  - failure_class: one of schema_drift, type_mismatch, null_violation,
    missing_source, stale_ref, cast_failure, permissions, logic, unknown
  - root_cause: one sentence
  - explanation: 2-4 sentences citing specific evidence from what you read
  - confidence: number 0-1
  - proposed_fix (optional): {rationale, diff} — diff must be a unified diff
    that applies cleanly with `git apply`, touches only model files (never
    sources/seeds/schema.yml/dbt_project.yml). Set to null when the failure
    is out of scope or you cannot construct a safe fix.

Be concise and evidence-driven. Submit the diagnosis within ~5 tool calls.
Do not hallucinate file contents; only reason from what the tools returned."""


def build_prompt(incident: Incident) -> Prompt:
    """Build a Prompt from an Incident.

    Includes the failing model's identity and error in the dynamic context
    so the agent has enough to bootstrap with read_file alone.
    """
    failing = incident.failing_model

    # Suggest paths the agent might want to read first. We pull these from
    # the manifest excerpt's nodes when available — generic dbt path
    # conventions otherwise. This is a hint, not a constraint; the agent
    # is free to read any project-relative path.
    paths_hint = ""
    if incident.manifest_excerpt:
        nodes = incident.manifest_excerpt.get("nodes", {}) or {}
        paths = sorted(
            {
                n.get("original_file_path", "")
                for n in nodes.values()
                if isinstance(n, dict) and n.get("original_file_path")
            },
        )
        if paths:
            shown = paths[:10]
            paths_hint = "\n\nFiles in scope (try read_file on these first):\n" + "\n".join(
                f"- {p}" for p in shown
            )

    return Prompt(
        version=PROMPT_VERSION,
        system=_SYSTEM,
        static_context="",
        dynamic_context=(
            f"Failing model: {failing.unique_id}\n"
            f"Status: {failing.raw_status}\n"
            f"Error: {failing.error}"
            f"{paths_hint}"
        ),
        instruction=(
            "Diagnose the root cause and call submit_diagnosis. "
            "Start with read_manifest_node to localize which model file is the right "
            "place to fix; use read_file to inspect that model's SQL and any seeds it "
            "depends on. Submit when you can defend the conclusion."
        ),
        purpose="diagnose",
    )


__all__ = ["PROMPT_VERSION", "build_prompt"]
