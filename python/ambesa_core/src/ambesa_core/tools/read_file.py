# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Ambesa Enterprise Ltd.

"""Tool: ``read_file`` — read a file in the dbt project safely."""

from __future__ import annotations

from ambesa_core.tools._lab_filter import LAB_ARTIFACT_DENY_MESSAGE, is_lab_artifact
from ambesa_core.tools.context import ToolContext
from ambesa_core.tools.spec import ToolSpec


async def read_file(ctx: ToolContext, path: str, max_bytes: int = 32_000) -> str:
    if is_lab_artifact(path):
        return f"<error>{LAB_ARTIFACT_DENY_MESSAGE}</error>"
    file_path = ctx.resolve(path)
    if not file_path.exists():
        return f"<error>file not found: {path}</error>"
    if not file_path.is_file():
        return f"<error>not a file: {path}</error>"
    data = file_path.read_bytes()
    if len(data) > max_bytes:
        truncated = data[:max_bytes].decode("utf-8", errors="replace")
        return f"<truncated bytes={len(data)} shown={max_bytes}>\n{truncated}\n</truncated>"
    return data.decode("utf-8", errors="replace")


SPEC = ToolSpec(
    name="read_file",
    description=(
        "Read the contents of a file in the dbt project. Path is relative "
        "to the project root. Use this to inspect SQL models, schema.yml, "
        "dbt_project.yml, seed CSVs, etc."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Project-relative path, e.g. 'models/staging/stg_customers.sql'.",
            },
            "max_bytes": {
                "type": "integer",
                "description": "Max bytes to return; truncates with marker if exceeded.",
                "default": 32000,
            },
        },
        "required": ["path"],
    },
    impl=read_file,
)
