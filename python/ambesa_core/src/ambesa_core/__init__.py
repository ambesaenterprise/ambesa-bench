# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Ambesa Enterprise Ltd.

"""ambesa-core — shared types, LLM provider abstraction, and tool surface.

This package contains the vendor-neutral primitives the public bench builds
on: typed data shapes (Incident, AgentRun, Diagnosis, FixProposal), the
``LLMProvider`` Protocol with an Anthropic implementation, and the public
tool surface (``read_file``, ``read_manifest_node``) plus the lab-artifact
filter that prevents agents from peeking at golden-outcome contracts.
"""

from __future__ import annotations

from ambesa_core._errors import AmbesaError, DiagnosisError, IntegrationError, LLMError
from ambesa_core.types import (
    Diagnosis,
    FailingModel,
    FailureClass,
    Incident,
    Prompt,
    TokenUsage,
)

__all__ = [
    "AmbesaError",
    "Diagnosis",
    "DiagnosisError",
    "FailingModel",
    "FailureClass",
    "Incident",
    "IntegrationError",
    "LLMError",
    "Prompt",
    "TokenUsage",
]

__version__ = "0.0.1"
