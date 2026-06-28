from pathlib import Path
from typing import Any

from galaxy_merge.tools.schemas import ToolSchema, ToolResult
from galaxy_merge.memory.store import MemoryStore


def make_memory_tools(gm_dir: Path) -> list[tuple[ToolSchema, Any]]:
    store = MemoryStore(gm_dir)

    async def memory_read(kind: str, recent: int = 20) -> ToolResult:
        records = store.read_recent(kind, recent)
        return ToolResult(
            success=True,
            data={
                "kind": kind,
                "records": records,
                "count": len(records),
            },
        )

    async def memory_write(kind: str, data: dict[str, Any]) -> ToolResult:
        store.append(kind, data)
        return ToolResult(
            success=True,
            data={
                "kind": kind,
                "written": True,
            },
        )

    return [
        (
            ToolSchema(
                "memory.read",
                "Read from project memory",
                parameters={
                    "kind": {"type": "string", "required": True},
                    "recent": {"type": "integer", "default": 20},
                },
            ),
            memory_read,
        ),
        (
            ToolSchema(
                "memory.write",
                "Write to project memory",
                mutates=True,
                parameters={
                    "kind": {"type": "string", "required": True},
                    "data": {"type": "object", "required": True},
                },
            ),
            memory_write,
        ),
    ]
