# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Ambesa Enterprise Ltd.

"""Tests for the eval-harness lab-leak filter.

Confirms the agent's file-reading tool refuses to surface scenario answer
keys from the snapshot. These files exist inside any repo that vendors
``ambesa-bench``; reading them during diagnosis is cheating.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from ambesa_core.tools._lab_filter import is_lab_artifact
from ambesa_core.tools.context import ToolContext
from ambesa_core.tools.read_file import read_file

# ────────────────────────────────────────────────────────────────────────
# is_lab_artifact — pure-function semantics
# ────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "path",
    [
        # Directly under any scenarios/ ancestor.
        "scenarios/01-schema-drift/expected.yaml",
        "scenarios/01-schema-drift/expected.patch",
        "scenarios/01-schema-drift/captured/manifest.json",
        "scenarios/01-schema-drift/captured/agent_run.json",
        "scenarios/01-schema-drift/overlay/seeds/raw_customers.csv",
        # Nested inside a deep project layout.
        "python/ambesa_fixtures/jaffle_shop/scenarios/02-type-mismatch/expected.yaml",
        "python/ambesa_fixtures/jaffle_shop/scenarios/03-null-violation/captured/run_results.json",
        "python/ambesa_fixtures/jaffle_shop/scenarios/04-recency-miss-on-empty/overlay/tests/recency.sql",
    ],
)
def test_lab_artifacts_are_denied(path: str) -> None:
    assert is_lab_artifact(path) is True


@pytest.mark.parametrize(
    "path",
    [
        # Allowed scenario meta-files: README + setup script + record script.
        "scenarios/01-schema-drift/README.md",
        "scenarios/01-schema-drift/setup.sh",
        "scenarios/01-schema-drift/record.py",
        "python/ambesa_fixtures/jaffle_shop/scenarios/01-schema-drift/README.md",
        # The scenarios/ directory itself (no leaf — listing is fine).
        "python/ambesa_fixtures/jaffle_shop/scenarios",
        # Non-scenario paths are obviously allowed.
        "models/staging/stg_customers.sql",
        "python/ambesa_fixtures/jaffle_shop/baseline/seeds/raw_customers.csv",
        "dbt_project.yml",
        # A customer repo that *happens* to have a top-level "expected.yaml"
        # outside any scenarios/ ancestor is allowed — the deny is structural,
        # not based on filename alone.
        "expected.yaml",
        "config/expected.yaml",
    ],
)
def test_non_lab_paths_are_allowed(path: str) -> None:
    assert is_lab_artifact(path) is False


# ────────────────────────────────────────────────────────────────────────
# read_file — refuses lab artifacts with a structured error
# ────────────────────────────────────────────────────────────────────────


def _write(root: Path, rel: str, content: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)


def test_read_file_denies_expected_yaml(tmp_path: Path) -> None:
    _write(tmp_path, "scenarios/01-schema-drift/expected.yaml", "secret: answer\n")
    ctx = ToolContext(project_root=tmp_path, target_dir=tmp_path / "target")
    out = asyncio.run(read_file(ctx, "scenarios/01-schema-drift/expected.yaml"))
    assert "Access denied" in out
    assert "answer" not in out  # the actual content must NOT leak


def test_read_file_denies_overlay_seed(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "python/ambesa_fixtures/jaffle_shop/scenarios/01-schema-drift/overlay/seeds/raw_customers.csv",
        "customer_id,first_name\n",
    )
    ctx = ToolContext(project_root=tmp_path, target_dir=tmp_path / "target")
    out = asyncio.run(
        read_file(
            ctx,
            "python/ambesa_fixtures/jaffle_shop/scenarios/01-schema-drift/overlay/seeds/raw_customers.csv",
        ),
    )
    assert "Access denied" in out
    assert "customer_id" not in out


def test_read_file_allows_scenario_readme(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "scenarios/01-schema-drift/README.md",
        "# Scenario 01\n\nWhat's broken: …\n",
    )
    ctx = ToolContext(project_root=tmp_path, target_dir=tmp_path / "target")
    out = asyncio.run(read_file(ctx, "scenarios/01-schema-drift/README.md"))
    assert "Scenario 01" in out
