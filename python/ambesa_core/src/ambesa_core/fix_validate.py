# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Ambesa Enterprise Ltd.

"""Validate that a proposed unified-diff fix applies cleanly against a working tree.

Used by both the public eval grader (``ambesa_core.eval.grader`` for the
bench's ``fix_must_apply_cleanly`` rubric) and the production Ambesa Watch
dispatcher (the Tier-2 pre-post fix-apply gate). Single source of truth so
the public bench number and the private accept-rate stay aligned.

Public API
~~~~~~~~~~

- :class:`FixApplyStatus` — enum of validation outcomes.
- :class:`FixValidationResult` — frozen dataclass carrying the outcome,
  the raw stderr from the last ``git apply --check`` attempt (when the
  fix didn't apply), and whether the validator had to resynthesize the
  diff to make it apply.
- :func:`validate_fix` — full validation, returns a
  :class:`FixValidationResult`.
- :func:`fix_applies_cleanly` — boolean convenience wrapper.

Validation strategy
~~~~~~~~~~~~~~~~~~~

Two passes:

  1. ``git apply --check`` on the diff as-is.
  2. If that fails, try to resynthesize a clean diff from the agent's
     changes (handles the common LLM failure mode where the diff content
     is right but the hunk header line numbers and counts are wrong —
     git rejects those as "corrupt patch" before any recount logic
     runs).

Does NOT fall back to ``patch -p1`` fuzz matching — that can mask
genuinely-wrong fixes. Resynthesis only succeeds when the agent's
deletion+context lines actually exist contiguously in the target file
at exactly one position; ambiguous matches and multi-file diffs are
refused rather than guessed at.
"""

from __future__ import annotations

import difflib
import re
import subprocess
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class FixApplyStatus(StrEnum):
    """Outcome of :func:`validate_fix`.

    - ``APPLIES_CLEANLY`` — the diff applies (either as-is or after
      resynthesis). Check ``used_resynthesis`` on the result to tell
      which path succeeded.
    - ``EMPTY_DIFF`` — the input was empty or whitespace-only. Treated
      as failure for the bench rubric and for the Watch dispatcher
      gate; downstream code can render an explicit "no fix proposed"
      label.
    - ``APPLY_FAILED`` — the diff did not apply, even after resynthesis
      was attempted. ``failure_stderr`` carries the last ``git apply
      --check`` stderr for triage / metrics.
    """

    APPLIES_CLEANLY = "applies_cleanly"
    EMPTY_DIFF = "empty_diff"
    APPLY_FAILED = "apply_failed"


@dataclass(frozen=True)
class FixValidationResult:
    """Structured outcome of a fix-apply validation."""

    status: FixApplyStatus
    failure_stderr: str | None = None
    used_resynthesis: bool = False

    @property
    def applies_cleanly(self) -> bool:
        """True iff status is :attr:`FixApplyStatus.APPLIES_CLEANLY`."""
        return self.status is FixApplyStatus.APPLIES_CLEANLY


_FILE_HEADER_RE = re.compile(r"^\+\+\+ (?:b/)?(.+)$")


def fix_applies_cleanly(diff: str, project_dir: Path) -> bool:
    """Boolean convenience wrapper around :func:`validate_fix`.

    Drop-in replacement for callers that only need a yes/no answer.
    """
    return validate_fix(diff, project_dir).applies_cleanly


def validate_fix(diff: str, project_dir: Path) -> FixValidationResult:
    """Validate ``diff`` against the working tree at ``project_dir``.

    Returns a :class:`FixValidationResult` with the outcome, the last
    stderr observed if the diff didn't apply, and a flag for whether
    the validator had to resynthesize the diff to make it apply.
    """
    if not diff.strip():
        return FixValidationResult(status=FixApplyStatus.EMPTY_DIFF)

    rc, stderr = _git_apply_check(diff, project_dir)
    if rc == 0:
        return FixValidationResult(status=FixApplyStatus.APPLIES_CLEANLY)
    last_stderr = stderr

    resynth = _resynthesize_diff(diff, project_dir)
    if resynth and resynth != diff:
        rc, stderr = _git_apply_check(resynth, project_dir)
        if rc == 0:
            return FixValidationResult(
                status=FixApplyStatus.APPLIES_CLEANLY,
                used_resynthesis=True,
            )
        last_stderr = stderr

    return FixValidationResult(
        status=FixApplyStatus.APPLY_FAILED,
        failure_stderr=last_stderr or None,
    )


def _git_apply_check(diff: str, project_dir: Path) -> tuple[int, str]:
    """Run ``git apply --check`` and return ``(returncode, stderr)``.

    Returns ``(-1, error_message)`` on timeout / OS errors so callers
    can record the failure mode without distinguishing them in the
    public API. Timeout is 10s — patches at agent scale apply in
    milliseconds; anything slower means something pathological.
    """
    try:
        result = subprocess.run(
            ["git", "apply", "--check", "-"],  # noqa: S607 — git on PATH is intentional
            check=False,
            cwd=str(project_dir),
            input=diff,
            text=True,
            capture_output=True,
            timeout=10,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return (-1, str(exc))
    return (result.returncode, result.stderr)


def _resynthesize_diff(  # noqa: PLR0912, PLR0915 — multi-pass diff parser, splitting hurts readability
    diff_text: str,
    project_dir: Path,
) -> str | None:
    """Try to rebuild a malformed unified diff into a valid one.

    Strategy: extract the agent's intended changes per file (the ``-``
    and ``+`` lines, treating `` `` lines as context anchors), find
    the matching anchor block in the actual file, and regenerate a
    clean diff using :func:`difflib.unified_diff`. This handles the
    very common LLM failure mode where the diff content is right but
    the hunk header line numbers and counts are wrong — git rejects
    those as "corrupt patch" before any recount logic runs.

    Returns ``None`` if the diff has no recoverable structure (e.g.
    zero context, multiple files, or anchor block not found in the
    target).
    """
    target_path: Path | None = None
    context_lines: list[str] = []
    deletions: list[str] = []
    additions: list[str] = []

    in_hunk = False
    saw_change = False
    for raw in diff_text.split("\n"):
        m = _FILE_HEADER_RE.match(raw)
        if m:
            if target_path is not None:
                # Multi-file diff — refuse to resynthesize, too risky
                return None
            target_path = project_dir / m.group(1)
            continue
        if raw.startswith("@@"):
            in_hunk = True
            continue
        if not in_hunk:
            continue
        if raw.startswith(" "):
            context_lines.append(raw[1:])
        elif raw.startswith("-"):
            deletions.append(raw[1:])
            saw_change = True
        elif raw.startswith("+"):
            additions.append(raw[1:])
            saw_change = True

    if target_path is None or not saw_change or not target_path.is_file():
        return None

    # Reconstruct OLD content (context interleaved with deletions, in original order)
    # and NEW content (context interleaved with additions). The hunk linearity
    # property: agent emits lines in target file order, so concatenating the
    # recovered ` `+`-` body in the order seen IS the OLD slice.
    old_block: list[str] = []
    new_block: list[str] = []
    in_hunk = False
    for raw in diff_text.split("\n"):
        if raw.startswith("@@"):
            in_hunk = True
            continue
        if not in_hunk:
            continue
        if raw.startswith(" "):
            old_block.append(raw[1:])
            new_block.append(raw[1:])
        elif raw.startswith("-"):
            old_block.append(raw[1:])
        elif raw.startswith("+"):
            new_block.append(raw[1:])

    if not old_block:
        return None

    # Find old_block as a contiguous run in the target file. Must match
    # at EXACTLY one position — multiple matches mean the deletion+context
    # is ambiguous (common when context is too short or the file repeats),
    # and picking one would be guessing. Refuse instead.
    file_lines = target_path.read_text().split("\n")
    if file_lines and file_lines[-1] == "":
        file_lines = file_lines[:-1]

    matches = [
        start
        for start in range(len(file_lines) - len(old_block) + 1)
        if file_lines[start : start + len(old_block)] == old_block
    ]
    if len(matches) != 1:
        return None
    found_at = matches[0]

    # Rebuild the file as: prefix + new_block + suffix, then unified_diff.
    new_file = file_lines[:found_at] + new_block + file_lines[found_at + len(old_block) :]
    rel = target_path.resolve().relative_to(project_dir.resolve())
    rebuilt = "".join(
        difflib.unified_diff(
            [line + "\n" for line in file_lines],
            [line + "\n" for line in new_file],
            fromfile=f"a/{rel}",
            tofile=f"b/{rel}",
            n=3,
        ),
    )
    return rebuilt or None


__all__ = [
    "FixApplyStatus",
    "FixValidationResult",
    "fix_applies_cleanly",
    "validate_fix",
]
