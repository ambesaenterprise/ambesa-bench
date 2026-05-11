# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Ambesa Enterprise Ltd.

"""Record one live Anthropic agent run against scenario 02 → JSON fixture.

Identical pattern to scenarios/01-schema-drift/record.py. Run this once
when the scenario or prompt changes; commit the resulting agent_run.json
as the regression anchor for future PRs.

    AMBESA_FIXTURE_PROJECT_DIR=/tmp/ambesa-fixture-XX  uv run python \\
      python/ambesa_fixtures/jaffle_shop/scenarios/02-type-mismatch/record.py
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from ambesa_core.agent import AgentConfig, run as agent_run
from ambesa_core.llm import CachePolicy, ModelId, get_provider
from ambesa_core.types import Incident
from ambesa_integrations import dbt as dbt_adapter

SCENARIO_DIR = Path(__file__).resolve().parent
CAPTURED_DIR = SCENARIO_DIR / "captured"
SETUP_SCRIPT = SCENARIO_DIR / "setup.sh"


async def main() -> int:
    project_dir = os.environ.get("AMBESA_FIXTURE_PROJECT_DIR")
    if not project_dir:
        result = subprocess.run(  # noqa: S603, S607 — setup.sh path is build-time-known
            [str(SETUP_SCRIPT)],
            check=True,
            capture_output=True,
            text=True,
        )
        project_dir = result.stdout.strip().splitlines()[-1]

    project_path = Path(project_dir).resolve()
    target_path = project_path / "target"

    print(f"project_dir: {project_path}", file=sys.stderr)
    print(f"target_dir:  {target_path}", file=sys.stderr)

    dbt_target = dbt_adapter.DbtTarget.from_dir(target_path)
    failing = dbt_adapter.parse_failing_models(dbt_target)
    if not failing:
        print("error: no failing models in run_results.json", file=sys.stderr)
        return 2
    failing_model = failing[0]
    print(
        f"failing_model: {failing_model.unique_id}  "
        f"(hint: {failing_model.failure_class_hint.value})",
        file=sys.stderr,
    )

    incident = Incident(
        id=uuid4(),
        repo_full_name="local/ambesa-fixture",
        commit_sha="fixture",
        failing_model=failing_model,
        manifest_excerpt=dbt_adapter.manifest_excerpt_for(
            dbt_target.manifest(),
            failing_model.unique_id,
        ),
        recent_commits=[],
        detected_at=datetime.now(UTC),
    )

    provider = get_provider("anthropic")
    cfg = AgentConfig(
        model=ModelId.CLAUDE_SONNET_4_6,
        cache=CachePolicy.AGGRESSIVE,
        max_iterations=10,
        max_cost_usd=0.30,
    )

    print("running agent live (this costs cents)…", file=sys.stderr)
    run = await agent_run(
        incident,
        project_root=project_path,
        target_dir=target_path,
        provider=provider,
        config=cfg,
    )

    print(
        f"stop_reason: {run.stop_reason.value if run.stop_reason else '?'}",
        file=sys.stderr,
    )
    print(f"iterations: {len(run.iterations)}", file=sys.stderr)
    print(f"cost_usd:   ${run.total_cost_usd:.4f}", file=sys.stderr)
    if run.final_diagnosis:
        print(
            f"diagnosis:  {run.final_diagnosis.failure_class.value} "
            f"(confidence {run.final_diagnosis.confidence:.2f})",
            file=sys.stderr,
        )

    CAPTURED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = CAPTURED_DIR / "agent_run.json"
    out_path.write_text(run.model_dump_json(indent=2))
    print(f"\nwrote {out_path}", file=sys.stderr)
    return 0 if run.final_diagnosis is not None else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
