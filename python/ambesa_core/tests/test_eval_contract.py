# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Ambesa Enterprise Ltd.

"""Unit tests for the eval contract schema — provenance + scenario taxonomy.

The provenance field is the public/private boundary made enforceable:
scenarios declare their type, the harness aggregator excludes
``production_incident`` from the public benchmark structurally. These
tests pin that contract.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ambesa_core.eval.contract import (
    FixByteEquivalenceTarget,
    Provenance,
    ProvenanceType,
)


class TestProvenanceTypeRequirements:
    """Type-conditional field requirements."""

    def test_public_incident_replay_requires_source_pr(self) -> None:
        with pytest.raises(ValidationError, match="source_pr is required"):
            Provenance(
                type=ProvenanceType.PUBLIC_INCIDENT_REPLAY,
                source_commit="abc123",
            )

    def test_public_incident_replay_requires_source_commit(self) -> None:
        with pytest.raises(ValidationError, match="source_commit is required"):
            Provenance(
                type=ProvenanceType.PUBLIC_INCIDENT_REPLAY,
                source_pr="https://github.com/dbt-labs/dbt-utils/pull/1065",
            )

    def test_public_incident_replay_with_required_fields_passes(self) -> None:
        p = Provenance(
            type=ProvenanceType.PUBLIC_INCIDENT_REPLAY,
            source_pr="https://github.com/dbt-labs/dbt-utils/pull/1065",
            source_commit="abc123def456",
        )
        assert p.type is ProvenanceType.PUBLIC_INCIDENT_REPLAY
        assert str(p.source_pr) == "https://github.com/dbt-labs/dbt-utils/pull/1065"
        assert p.source_commit == "abc123def456"

    def test_canonical_fixture_does_not_require_source_fields(self) -> None:
        """Canonical fixtures are synthetic — no source_pr to point at."""
        p = Provenance(type=ProvenanceType.CANONICAL_FIXTURE)
        assert p.source_pr is None
        assert p.source_commit is None

    def test_production_incident_does_not_require_source_fields(self) -> None:
        """Production incidents come from private customer data — no public source."""
        p = Provenance(type=ProvenanceType.PRODUCTION_INCIDENT)
        assert p.source_pr is None


class TestPublicBenchmarkBoundary:
    """The structural public/private split: production_incident is excluded from public counting."""

    def test_canonical_fixture_counts_toward_public_benchmark(self) -> None:
        p = Provenance(type=ProvenanceType.CANONICAL_FIXTURE)
        assert p.counts_toward_public_benchmark is True

    def test_public_incident_replay_counts_toward_public_benchmark(self) -> None:
        p = Provenance(
            type=ProvenanceType.PUBLIC_INCIDENT_REPLAY,
            source_pr="https://github.com/dbt-labs/dbt-utils/pull/1065",
            source_commit="abc123",
        )
        assert p.counts_toward_public_benchmark is True

    def test_production_incident_excluded_from_public_benchmark(self) -> None:
        """The public/private boundary — customer-private scenarios never aggregate publicly."""
        p = Provenance(type=ProvenanceType.PRODUCTION_INCIDENT)
        assert p.counts_toward_public_benchmark is False


class TestProvenanceStrictness:
    """``extra=forbid`` catches typos that would otherwise silently drift."""

    def test_unknown_field_raises(self) -> None:
        with pytest.raises(ValidationError):
            Provenance(  # type: ignore[call-arg]
                type=ProvenanceType.CANONICAL_FIXTURE,
                garbage_field="nope",
            )

    def test_invalid_url_in_source_pr_raises(self) -> None:
        with pytest.raises(ValidationError):
            Provenance(
                type=ProvenanceType.PUBLIC_INCIDENT_REPLAY,
                source_pr="not a url",
                source_commit="abc",
            )

    def test_unknown_provenance_type_raises(self) -> None:
        with pytest.raises(ValidationError):
            Provenance(type="customer_native")


class TestFixByteEquivalenceTarget:
    """All three targets are accepted; unknown values rejected."""

    @pytest.mark.parametrize(
        "target",
        [
            FixByteEquivalenceTarget.EXACT,
            FixByteEquivalenceTarget.UPSTREAM_FIX,
            FixByteEquivalenceTarget.CONSUMER_WORKAROUND,
        ],
    )
    def test_valid_targets_accepted(self, target: FixByteEquivalenceTarget) -> None:
        p = Provenance(
            type=ProvenanceType.CANONICAL_FIXTURE,
            fix_byte_equivalence_target=target,
        )
        assert p.fix_byte_equivalence_target is target

    def test_unknown_target_raises(self) -> None:
        with pytest.raises(ValidationError):
            Provenance(
                type=ProvenanceType.CANONICAL_FIXTURE, fix_byte_equivalence_target="upstream_patch"
            )
