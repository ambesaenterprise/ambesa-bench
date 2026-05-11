# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Ambesa Enterprise Ltd.

"""Public-API tests for :mod:`ambesa_core.fix_validate`.

Black-box coverage of :func:`validate_fix`, :func:`fix_applies_cleanly`,
:class:`FixApplyStatus`, and :class:`FixValidationResult`. The
white-box resynthesizer tests live in ``test_grader_diff_resynthesis.py``.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from ambesa_core.fix_validate import (
    FixApplyStatus,
    FixValidationResult,
    fix_applies_cleanly,
    validate_fix,
)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """A 'project' with a deterministic 6-line file the tests will patch."""
    proj = tmp_path / "proj"
    (proj / "models").mkdir(parents=True)
    (proj / "models" / "x.sql").write_text(
        "select\n    id,\n    name,\n    email\nfrom raw_users\nwhere active\n",
    )
    return proj


_CLEAN_DIFF = (
    "--- a/models/x.sql\n"
    "+++ b/models/x.sql\n"
    "@@ -5,2 +5,2 @@\n"
    " from raw_users\n"
    "-where active\n"
    "+where active and id is not null\n"
)


_BAD_HUNK_HEADER_DIFF = (
    # Wrong hunk math — claims @@ -3,2 +3,2 @@ but we're modifying line 6 area.
    "--- a/models/x.sql\n"
    "+++ b/models/x.sql\n"
    "@@ -3,2 +3,2 @@\n"
    "from raw_users\n"
    "-where active\n"
    "+where active and id is not null\n"
)


_BOGUS_ANCHOR_DIFF = (
    "--- a/models/x.sql\n"
    "+++ b/models/x.sql\n"
    "@@ -1,3 +1,4 @@\n"
    "-    SELECT this_column_does_not_exist FROM nowhere\n"
    "+    select 1\n"
)


# ────────────────────────────────────────────────────────────────────────
# validate_fix — status enum coverage
# ────────────────────────────────────────────────────────────────────────


def test_clean_diff_returns_applies_cleanly(project: Path) -> None:
    result = validate_fix(_CLEAN_DIFF, project)
    assert result.status is FixApplyStatus.APPLIES_CLEANLY
    assert result.applies_cleanly is True
    assert result.used_resynthesis is False
    assert result.failure_stderr is None


def test_empty_diff_returns_empty_diff_status(project: Path) -> None:
    result = validate_fix("", project)
    assert result.status is FixApplyStatus.EMPTY_DIFF
    assert result.applies_cleanly is False


def test_whitespace_only_diff_returns_empty_diff_status(project: Path) -> None:
    result = validate_fix("   \n\n\t\n", project)
    assert result.status is FixApplyStatus.EMPTY_DIFF
    assert result.applies_cleanly is False


def test_bad_hunk_math_recovered_via_resynthesis(project: Path) -> None:
    """The LLM failure mode the resynthesizer exists to fix: content right,
    line numbers wrong. ``used_resynthesis`` distinguishes this from the
    first-pass-clean path."""
    result = validate_fix(_BAD_HUNK_HEADER_DIFF, project)
    assert result.status is FixApplyStatus.APPLIES_CLEANLY
    assert result.applies_cleanly is True
    assert result.used_resynthesis is True


def test_bogus_anchor_returns_apply_failed_with_stderr(project: Path) -> None:
    """When the agent's deletion lines don't exist in the file, both
    the as-is apply AND the resynthesis fail. ``failure_stderr`` carries
    the last ``git apply --check`` error for triage."""
    result = validate_fix(_BOGUS_ANCHOR_DIFF, project)
    assert result.status is FixApplyStatus.APPLY_FAILED
    assert result.applies_cleanly is False
    assert result.used_resynthesis is False
    assert result.failure_stderr is not None
    assert len(result.failure_stderr) > 0


# ────────────────────────────────────────────────────────────────────────
# fix_applies_cleanly — boolean convenience wrapper
# ────────────────────────────────────────────────────────────────────────


def test_fix_applies_cleanly_returns_true_for_clean_diff(project: Path) -> None:
    assert fix_applies_cleanly(_CLEAN_DIFF, project) is True


def test_fix_applies_cleanly_returns_true_for_resynth_recoverable(project: Path) -> None:
    assert fix_applies_cleanly(_BAD_HUNK_HEADER_DIFF, project) is True


def test_fix_applies_cleanly_returns_false_for_empty(project: Path) -> None:
    assert fix_applies_cleanly("", project) is False


def test_fix_applies_cleanly_returns_false_for_bogus(project: Path) -> None:
    assert fix_applies_cleanly(_BOGUS_ANCHOR_DIFF, project) is False


# ────────────────────────────────────────────────────────────────────────
# FixValidationResult — immutability + property semantics
# ────────────────────────────────────────────────────────────────────────


def test_result_is_frozen() -> None:
    """The result dataclass is frozen — mutation should raise FrozenInstanceError."""
    result = FixValidationResult(status=FixApplyStatus.APPLIES_CLEANLY)
    with pytest.raises(FrozenInstanceError):
        result.status = FixApplyStatus.EMPTY_DIFF  # type: ignore[misc]


def test_applies_cleanly_property_matches_status() -> None:
    assert FixValidationResult(status=FixApplyStatus.APPLIES_CLEANLY).applies_cleanly is True
    assert FixValidationResult(status=FixApplyStatus.EMPTY_DIFF).applies_cleanly is False
    assert FixValidationResult(status=FixApplyStatus.APPLY_FAILED).applies_cleanly is False


def test_status_enum_values_are_stable() -> None:
    """These enum string values land in Postgres + Axiom; stability matters."""
    assert FixApplyStatus.APPLIES_CLEANLY.value == "applies_cleanly"
    assert FixApplyStatus.EMPTY_DIFF.value == "empty_diff"
    assert FixApplyStatus.APPLY_FAILED.value == "apply_failed"
