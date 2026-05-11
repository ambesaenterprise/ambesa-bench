# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Ambesa Enterprise Ltd.

"""Tool execution context.

Carries everything a tool needs to do its job without each tool
reimplementing project-root discovery or manifest parsing.
"""

from __future__ import annotations

import json
from functools import cached_property
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict


class ToolContext(BaseModel):
    """Read-only context handed to every tool dispatch.

    The project_root is resolved once and used to safely scope filesystem
    operations: every tool that takes a path resolves the user-supplied
    string against this root and refuses anything that escapes.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    project_root: Path
    target_dir: Path
    """``<project_root>/target/`` — where dbt writes manifest.json + run_results.json."""

    @cached_property
    def manifest(self) -> dict[str, Any]:
        path = self.target_dir / "manifest.json"
        if not path.exists():
            raise FileNotFoundError(f"manifest.json not found at {path}")
        return dict(json.loads(path.read_text()))

    @cached_property
    def run_results(self) -> dict[str, Any]:
        path = self.target_dir / "run_results.json"
        if not path.exists():
            raise FileNotFoundError(f"run_results.json not found at {path}")
        return dict(json.loads(path.read_text()))

    def resolve(self, user_path: str) -> Path:
        """Resolve a user-supplied path against project_root, refusing escape.

        Raises ``ValueError`` for any path traversal attempt.
        """
        candidate = (self.project_root / user_path).resolve()
        try:
            candidate.relative_to(self.project_root.resolve())
        except ValueError as exc:
            raise ValueError(
                f"path '{user_path}' escapes project root {self.project_root}",
            ) from exc
        return candidate
