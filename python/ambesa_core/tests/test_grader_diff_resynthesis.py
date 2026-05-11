# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Ambesa Enterprise Ltd.

"""Unit tests for the diff-resynthesizer in ambesa_core.fix_validate.

The resynthesizer rebuilds malformed unified diffs (right content,
wrong hunk math) into valid ones by finding the deletion/context lines
in the target file and regenerating with difflib. These tests are the
white-box coverage; black-box public-API tests live in test_fix_validate.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from ambesa_core.fix_validate import _resynthesize_diff, fix_applies_cleanly


def _git_apply_check(diff: str, project: Path) -> int:
    """Run `git apply --check` and return the exit code."""
    return subprocess.run(
        ["git", "apply", "--check", "-"],
        check=False,
        cwd=str(project),
        input=diff,
        text=True,
        capture_output=True,
        timeout=5,
    ).returncode


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """A 'project' with a tiny model file we'll patch in tests."""
    proj = tmp_path / "proj"
    (proj / "models").mkdir(parents=True)
    # Deterministic 6-line file. Line numbers below are exact.
    (proj / "models" / "x.sql").write_text(
        "select\n    id,\n    name,\n    email\nfrom raw_users\nwhere active\n",
    )
    return proj


def test_resynthesis_recovers_wrong_hunk_math(project: Path) -> None:
    """LLM-style failure: hunk header lies, content is correct.

    The agent wants to add ``where id is not null`` before ``where active``.
    It writes a hunk header that's syntactically valid but mathematically
    wrong. ``git apply --check`` rejects it; the resynthesizer fixes it.
    """
    # Wrong: claims @@ -3,2 +3,2 @@ but we're modifying line 6 area.
    bad_diff = (
        "--- a/models/x.sql\n"
        "+++ b/models/x.sql\n"
        "@@ -3,2 +3,2 @@\n"
        "from raw_users\n"
        "-where active\n"
        "+where active and id is not null\n"
    )
    # Strict path rejects it.
    assert _git_apply_check(bad_diff, project) != 0, "premise: bad diff is rejected"

    # Resynthesizer rebuilds.
    rebuilt = _resynthesize_diff(bad_diff, project)
    assert rebuilt is not None, "resynthesizer should recover this"
    assert _git_apply_check(rebuilt, project) == 0, "rebuilt diff must apply cleanly"

    # Full grader path returns True via the resynth fallback.
    assert fix_applies_cleanly(bad_diff, project) is True


def test_resynthesis_returns_none_when_anchor_not_in_file(project: Path) -> None:
    """If the agent's deletion lines don't exist in the target, refuse to fix."""
    bogus = (
        "--- a/models/x.sql\n"
        "+++ b/models/x.sql\n"
        "@@ -1,3 +1,4 @@\n"
        "-    SELECT this_column_does_not_exist FROM nowhere\n"
        "+    select 1\n"
    )
    rebuilt = _resynthesize_diff(bogus, project)
    assert rebuilt is None
    assert fix_applies_cleanly(bogus, project) is False


def test_fix_applies_cleanly_rejects_empty_diff(project: Path) -> None:
    assert fix_applies_cleanly("", project) is False
    assert fix_applies_cleanly("   \n\n", project) is False


def test_resynthesis_refuses_ambiguous_anchors(tmp_path: Path) -> None:
    """If the deletion+context block matches in 2+ places, refuse to fix.

    Picking one match would be guessing. The contract should fail loudly
    in this case so a human disambiguates rather than the harness
    silently picking the wrong one.
    """
    proj = tmp_path / "proj"
    (proj / "models").mkdir(parents=True)
    # Two identical "select x" blocks in the same file — anchor is ambiguous.
    (proj / "models" / "x.sql").write_text(
        "select 1\nfrom a\nunion all\nselect 1\nfrom b\n",
    )
    ambiguous = "--- a/models/x.sql\n+++ b/models/x.sql\n@@ -1,2 +1,2 @@\n-select 1\n+select 2\n"
    assert _resynthesize_diff(ambiguous, proj) is None
    assert fix_applies_cleanly(ambiguous, proj) is False


def test_resynthesis_returns_none_for_multi_file_diff(project: Path) -> None:
    """Resynthesizer is single-file only; multi-file diffs are too risky."""
    multi = (
        "--- a/models/x.sql\n"
        "+++ b/models/x.sql\n"
        "@@ -1,1 +1,1 @@\n"
        "-select\n"
        "+SELECT\n"
        "--- a/models/y.sql\n"
        "+++ b/models/y.sql\n"
        "@@ -1,1 +1,1 @@\n"
        "-foo\n"
        "+bar\n"
    )
    assert _resynthesize_diff(multi, project) is None
