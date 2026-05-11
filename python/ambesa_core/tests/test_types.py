# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Ambesa Enterprise Ltd.

from __future__ import annotations

import pytest

from ambesa_core.types import V1_SUPPORTED_CLASSES, FailureClass


@pytest.mark.unit
def test_failure_class_values_match_db_enum() -> None:
    expected = {
        "schema_drift",
        "type_mismatch",
        "null_violation",
        "missing_source",
        "stale_ref",
        "cast_failure",
        "permissions",
        "logic",
        "unknown",
    }
    assert {fc.value for fc in FailureClass} == expected


@pytest.mark.unit
def test_v1_scope_is_explicit() -> None:
    assert (
        frozenset(
            {FailureClass.SCHEMA_DRIFT, FailureClass.TYPE_MISMATCH, FailureClass.NULL_VIOLATION},
        )
        == V1_SUPPORTED_CLASSES
    )
