# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Ambesa Enterprise Ltd.

"""Filter paths inside the snapshotted project that are eval-harness artifacts.

These files exist only because the snapshot is the *Ambesa* repo (or any
repo that vendors the public ``ambesa-bench`` benchmark). A real customer
repo has none of them. Inside Ambesa's own repo they are answer keys —
exposing them to the agent during diagnosis would be cheating, and
specifically would inflate the apparent quality of demos / Show-HN casts
/ self-graded eval runs.

Denied artifacts:

* ``scenarios/<name>/expected.yaml`` — golden-outcome contract the eval
  harness grades the agent against. Contains the failure_class, the
  acceptable root_cause language, and confidence bands. **Reading this
  IS reading the answer key.**
* ``scenarios/<name>/expected.patch`` — a known-good fix shape for the
  scenario. Reading it is reading the answer to "what should the diff be."
* ``scenarios/<name>/captured/**`` — recordings of past Anthropic calls
  + the resulting AgentRun JSON for the public stripped reference agent.
  Past reasoning the agent wouldn't have produced organically; replaying
  it is also cheating.
* ``scenarios/<name>/production-runs/**`` — same idea but for the
  production agent's recordings (read only by the private eval). The
  agent must not surface either flavor of recording during diagnosis.
* ``scenarios/<name>/overlay/**`` — the deliberate breakage diff applied
  on top of baseline. Reading the overlay tells the agent exactly what
  the fixture changed; that's the work the diagnose loop is supposed
  to do unaided.

Not denied (intentionally available):

* ``scenarios/<name>/README.md`` — narrative description of what's broken.
  Same kind of context a human DE would write in a runbook.
* ``scenarios/<name>/setup.sh`` and ``record.py`` — scaffolding scripts.
  They describe the harness, not the answer.
* ``scenarios/`` itself as a directory listing — fine.

The filter operates on **project-relative** paths (the form the agent
passes), not absolute paths under the snapshot tempdir. This keeps the
rules portable across snapshots and across customer repos that happen
to have a ``scenarios/`` directory of their own.
"""

from __future__ import annotations

from pathlib import Path, PurePath, PurePosixPath


def is_lab_artifact(rel_path: str | PurePath | Path) -> bool:
    """Return True if ``rel_path`` is an eval-harness artifact.

    ``rel_path`` is project-relative (e.g.
    ``"python/ambesa_fixtures/jaffle_shop/scenarios/01-schema-drift/expected.yaml"``).
    Comparison is by path components, not string matching, so OS-specific
    separators don't change the answer.
    """
    parts = PurePosixPath(str(rel_path)).parts
    # Look for ".../scenarios/<scenario-name>/<artifact>..." pattern.
    # We need at least three components after "scenarios" to land in the
    # denylist (scenarios / <name> / <something>).
    for i, part in enumerate(parts):
        if part != "scenarios":
            continue
        if i + 2 >= len(parts):
            # ".../scenarios/<name>" with no leaf — not an artifact in
            # itself; allow listing.
            continue
        leaf = parts[i + 2]
        if leaf in {"expected.yaml", "expected.patch"}:
            return True
        if leaf in {"captured", "overlay", "production-runs"}:
            # Anything inside captured/, overlay/, or production-runs/ is denied.
            return True
    return False


LAB_ARTIFACT_DENY_MESSAGE = (
    "Access denied. The path is an Ambesa eval-harness artifact "
    "(golden-outcome contract, captured agent run, or overlay diff). "
    "These files exist only inside Ambesa's own repo and exposing them "
    "to the agent would short-circuit the diagnosis. Reason about the "
    "real project state instead — model SQL, manifest.json, "
    "run_results.json, recent commits."
)


__all__ = ["LAB_ARTIFACT_DENY_MESSAGE", "is_lab_artifact"]
