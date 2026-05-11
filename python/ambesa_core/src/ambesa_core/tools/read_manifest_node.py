# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Ambesa Enterprise Ltd.

"""Tool: ``read_manifest_node`` — fetch a trimmed manifest entry by unique_id."""

from __future__ import annotations

import json

from ambesa_core.tools.context import ToolContext
from ambesa_core.tools.spec import ToolSpec

_KEEP_KEYS = (
    "unique_id",
    "name",
    "resource_type",
    "package_name",
    "path",
    "original_file_path",
    "compiled_code",
    "raw_code",
    "columns",
    "depends_on",
    "config",
    "schema",
    "alias",
    "database",
    "tags",
    "meta",
)


async def read_manifest_node(ctx: ToolContext, unique_id: str) -> str:
    nodes = {**ctx.manifest.get("nodes", {}), **ctx.manifest.get("sources", {})}
    node = nodes.get(unique_id)
    if node is None:
        return f"<error>node not found in manifest: {unique_id}</error>"
    trimmed = {k: node[k] for k in _KEEP_KEYS if k in node}
    return json.dumps(trimmed, indent=2)


SPEC = ToolSpec(
    name="read_manifest_node",
    description=(
        "Get the manifest entry for a model, source, or test by its dbt "
        "unique_id (e.g. 'model.jaffle_shop.stg_customers' or "
        "'source.jaffle_shop.raw.raw_customers'). Returns columns, "
        "compiled SQL, depends_on, and config — bounded to relevant fields."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "unique_id": {
                "type": "string",
                "description": "Dbt manifest unique_id of the node.",
            },
        },
        "required": ["unique_id"],
    },
    impl=read_manifest_node,
)
