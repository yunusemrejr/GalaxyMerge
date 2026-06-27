from pathlib import Path
from typing import Any

from galaxy_merge.tools.schemas import ToolSchema, ToolResult
from galaxy_merge.workspace.indexer import WorkspaceIndexer


def make_index_tools(workroot: Path) -> list[tuple[ToolSchema, Any]]:
    indexer = WorkspaceIndexer(workroot)

    async def index_refresh() -> ToolResult:
        result = indexer.refresh()
        return ToolResult(success=True, data=result)

    return [
        (ToolSchema("workspace.index", "Refresh workspace index", mutates=True, requires_safety=False),
         index_refresh),
    ]
