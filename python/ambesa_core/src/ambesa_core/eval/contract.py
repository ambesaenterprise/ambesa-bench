# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Ambesa Enterprise Ltd.

"""ExpectedOutcome — the typed contract loaded from each scenario's expected.yaml.

The schema documented in this file is the source of truth. Pydantic
validates on load so a malformed contract fails before the harness runs.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Self

import yaml
from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, model_validator

from ambesa_core.types import FailureClass


class ProvenanceType(StrEnum):
    """Where this scenario came from. Determines public-benchmark eligibility.

    - ``canonical_fixture`` — synthetic break authored from scratch (jaffle_shop
      variants, scenarios 01-03). Counts toward the public benchmark.
    - ``public_incident_replay`` — reproduction of a public, externally-verifiable
      incident: a real PR / issue / commit in a public dbt project. Counts toward
      the public benchmark; provenance fields locate the source artifact.
    - ``production_incident`` — sanitized capture from a customer's private
      production warehouse. **Excluded from the public benchmark by design.**
      Lives in private scenario sets for grading but never aggregates into
      the public score.
    """

    CANONICAL_FIXTURE = "canonical_fixture"
    PUBLIC_INCIDENT_REPLAY = "public_incident_replay"
    PRODUCTION_INCIDENT = "production_incident"


class FixByteEquivalenceTarget(StrEnum):
    """What the agent's fix is being compared against, byte-for-byte.

    - ``exact`` — for canonical fixtures where the contract IS the truth.
    - ``upstream_fix`` — agent's fix should match the upstream maintainer's
      merged diff. Strong claim; fragile.
    - ``consumer_workaround`` — agent's fix should match a defensible
      consumer-side workaround (filter / coalesce / pin) — what a real DE
      would write at 3am while waiting for the upstream fix. Most realistic
      claim for ``public_incident_replay`` scenarios.
    """

    EXACT = "exact"
    UPSTREAM_FIX = "upstream_fix"
    CONSUMER_WORKAROUND = "consumer_workaround"


class Provenance(BaseModel):
    """Where this scenario came from and what claim it backs.

    Machine-readable so the public benchmark can structurally exclude
    ``production_incident`` types and the leaderboard can render the
    source artifact for ``public_incident_replay`` types. Every scenario
    declares one.
    """

    model_config = ConfigDict(extra="forbid")

    type: ProvenanceType

    source_pr: AnyHttpUrl | None = None
    """URL of the public PR / issue / merge request the incident came from.

    Required for ``public_incident_replay``. Optional otherwise.
    """

    source_commit: str | None = None
    """Full SHA of the pre-fix commit (the broken state) in the source repo.

    Required for ``public_incident_replay`` so reviewers can git-checkout
    the exact state the agent diagnoses against.
    """

    reproduction_method: str | None = None
    """One-line description of how the original incident was rebuilt as a
    deterministic fixture (e.g. "dbt-duckdb fixture against dbt-utils@<sha>").

    Optional but informative — surfaced in PR bodies and the public leaderboard.
    """

    fix_byte_equivalence_target: FixByteEquivalenceTarget | None = None
    """What anchor the fix-equivalence claim is made against.

    Optional. If absent, the contract makes no equivalence claim — only
    that the fix applies and lands in the expected files (the structural
    pins). When present, surfaced in the leaderboard alongside the diff.
    """

    notes: str | None = None
    """Free-form provenance commentary — privacy redactions, attribution
    caveats, license notes. Optional.
    """

    @model_validator(mode="after")
    def _validate_required_by_type(self) -> Self:
        if self.type is ProvenanceType.PUBLIC_INCIDENT_REPLAY:
            if self.source_pr is None:
                msg = "provenance.source_pr is required for public_incident_replay"
                raise ValueError(msg)
            if not self.source_commit:
                msg = "provenance.source_commit is required for public_incident_replay"
                raise ValueError(msg)
        return self

    @property
    def counts_toward_public_benchmark(self) -> bool:
        """True for canonical_fixture and public_incident_replay; False for
        production_incident. The public ``ambesa-bench`` aggregator uses
        this to enforce the public/private boundary structurally.
        """
        return self.type is not ProvenanceType.PRODUCTION_INCIDENT


class ExpectedOutcome(BaseModel):
    """The contract every scenario commits to.

    Field-by-field rationale is in this docstring and the per-field
    docstrings below; reading the class top-to-bottom is the spec.
    """

    model_config = ConfigDict(extra="forbid")  # typo in YAML = hard fail

    # Provenance ────────────────────────────────────────
    provenance: Provenance

    # Diagnosis ─────────────────────────────────────────
    expected_failure_class: FailureClass
    min_confidence: float = Field(ge=0.0, le=1.0)

    # Tool usage shape ──────────────────────────────────
    min_evidence_calls: int = Field(default=1, ge=0)
    at_least_one_of: list[str] = Field(default_factory=list)
    forbidden_tool_calls: list[str] = Field(default_factory=list)

    # Iteration / cost ceilings ─────────────────────────
    max_iterations: int = Field(default=12, ge=1, le=30)
    max_cost_usd: float = Field(default=0.20, gt=0.0)

    # Diff shape ────────────────────────────────────────
    expected_files_touched: list[str] = Field(default_factory=list)
    forbidden_files_touched: list[str] = Field(default_factory=list)
    fix_must_apply_cleanly: bool = True

    # Optional text assertions on diagnosis ─────────────
    must_mention_columns: list[str] = Field(default_factory=list)
    must_mention_models: list[str] = Field(default_factory=list)


def load_expected(path: str | Path) -> ExpectedOutcome:
    """Load and validate an ``expected.yaml`` file. Raises on schema errors."""
    raw = yaml.safe_load(Path(path).read_text())
    if raw is None:
        raise ValueError(f"empty contract file: {path}")
    if not isinstance(raw, dict):
        raise TypeError(f"contract file must be a YAML mapping at top level: {path}")
    return ExpectedOutcome.model_validate(raw)


__all__ = [
    "ExpectedOutcome",
    "FixByteEquivalenceTarget",
    "Provenance",
    "ProvenanceType",
    "load_expected",
]
