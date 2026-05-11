# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Ambesa Enterprise Ltd.

"""Agent tool implementations.

One file per tool. Each tool is a pure function: ``ToolContext`` + typed
args → string result. No tool calls the LLM. No tool mutates persistent
state. All filesystem operations are rooted at ``ToolContext.project_root``
and refuse path traversal.

The public surface in this package is ``ToolContext`` (the per-run handle)
plus the ``Tool`` / ``ToolSpec`` types. Concrete tools (``read_file``,
``read_manifest_node``) are imported from their own modules.
"""

from __future__ import annotations

from ambesa_core.tools.context import ToolContext
from ambesa_core.tools.spec import Tool, ToolSpec

__all__ = ["Tool", "ToolContext", "ToolSpec"]
