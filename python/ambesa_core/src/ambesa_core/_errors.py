# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Ambesa Enterprise Ltd.

"""Exception hierarchy for ambesa_core.

Every error raised out of this package extends ``AmbesaError`` so callers
can catch the umbrella when needed and the specific subclass when not.
"""

from __future__ import annotations


class AmbesaError(Exception):
    """Base for every ambesa_core exception."""


class LLMError(AmbesaError):
    """Failures around LLM provider calls (network, rate limit, malformed response)."""


class DiagnosisError(AmbesaError):
    """Failures inside the diagnosis loop (parsing, prompt construction, no candidate)."""


class IntegrationError(AmbesaError):
    """Failures in third-party integrations (dbt manifest, GitHub, warehouse)."""


class ConfigError(AmbesaError):
    """Misconfiguration — missing env vars, invalid prompt versions."""
