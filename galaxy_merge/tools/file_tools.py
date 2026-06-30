import hashlib
from pathlib import Path
from typing import Any

from galaxy_merge.core.locks import FileLock, atomic_write
from galaxy_merge.safety.path_utils import resolve_inside
from galaxy_merge.tools.schemas import ToolSchema, ToolResult


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def _file_hash(path: Path) -> str:
    if not path.exists():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def make_file_tools(workroot: Path) -> list[tuple[ToolSchema, Any]]:
    tools: list[tuple[ToolSchema, Any]] = []

    async def file_read(
        path: str, offset: int = 0, limit: int | None = None
    ) -> ToolResult:
        target = resolve_inside(workroot, path)
        if target is None:
            return ToolResult(success=False, error="path outside WorkRoot")
        if not target.exists():
            return ToolResult(success=False, error="file not found")
        if not target.is_file():
            return ToolResult(success=False, error="not a file")

        content = target.read_text(encoding="utf-8", errors="replace")
        lines = content.splitlines(keepends=True)
        if limit:
            lines = lines[offset : offset + limit]
        else:
            lines = lines[offset:]

        return ToolResult(
            success=True,
            data={
                "path": str(target.relative_to(workroot)),
                "content": "".join(lines),
                "size": len(content),
                "line_count": content.count("\n") + 1,
                "content_hash": _content_hash(content),
            },
        )

    async def file_write(
        path: str,
        content: str,
        expected_hash: str | None = None,
    ) -> ToolResult:
        target = resolve_inside(workroot, path)
        if target is None:
            return ToolResult(success=False, error="path outside WorkRoot")

        target.parent.mkdir(parents=True, exist_ok=True)
        lock_path = target.with_suffix(target.suffix + ".lock")
        with FileLock(lock_path, timeout=10.0):
            current_hash = _file_hash(target)
            if expected_hash is not None and current_hash != expected_hash:
                return ToolResult(
                    success=False,
                    error="file conflict: content changed before write",
                    data={
                        "path": str(target.relative_to(workroot)),
                        "expected_hash": expected_hash,
                        "current_hash": current_hash,
                        "conflict": True,
                    },
                )
            atomic_write(target, content, _nested_lock=True)
        return ToolResult(
            success=True,
            data={
                "path": str(target.relative_to(workroot)),
                "size": len(content),
                "content_hash": _content_hash(content),
            },
        )

    async def file_search(
        pattern: str, path: str = ".", include: str | None = None
    ) -> ToolResult:
        import subprocess

        search_root = resolve_inside(workroot, path)
        if search_root is None:
            return ToolResult(success=False, error="path outside WorkRoot")

        cmd = ["rg", "-n", "--no-heading", pattern, str(search_root)]
        if include:
            cmd.extend(["-g", include])

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            lines = result.stdout.splitlines()[:200]
            return ToolResult(
                success=True,
                data={
                    "matches": lines,
                    "count": len(lines),
                    "truncated": len(result.stdout.splitlines()) > 200,
                },
            )
        except FileNotFoundError:
            return ToolResult(success=False, error="ripgrep (rg) not found on system")
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    async def file_tree(path: str = "") -> ToolResult:
        target = resolve_inside(workroot, path) if path else workroot
        if target is None:
            return ToolResult(success=False, error="path outside WorkRoot")

        def build(p: Path) -> dict[str, Any]:
            result: dict[str, Any] = {
                "name": p.name,
                "type": "directory",
                "children": [],
            }
            if p.is_dir():
                try:
                    for child in sorted(p.iterdir()):
                        if child.name.startswith(".") and child.name != ".gm":
                            continue
                        if child.name == "node_modules":
                            continue
                        if child.is_dir():
                            result["children"].append(build(child))
                        else:
                            try:
                                size = child.stat().st_size
                                result["children"].append(
                                    {
                                        "name": child.name,
                                        "type": "file",
                                        "size": size,
                                    }
                                )
                            except OSError:
                                pass
                except PermissionError:
                    pass
            return result

        tree = build(target)
        return ToolResult(success=True, data=tree)

    tools.append(
        (
            ToolSchema(
                "file.read",
                "Read a file from the workspace",
                parameters={
                    "path": {"type": "string", "required": True},
                    "offset": {"type": "integer", "default": 0},
                    "limit": {"type": "integer", "default": None},
                },
            ),
            file_read,
        )
    )

    tools.append(
        (
            ToolSchema(
                "file.write",
                "Write content to a file",
                mutates=True,
                parameters={
                    "path": {"type": "string", "required": True},
                    "content": {"type": "string", "required": True},
                    "expected_hash": {"type": "string", "default": None},
                },
            ),
            file_write,
        )
    )

    tools.append(
        (
            ToolSchema(
                "file.search",
                "Search file contents with ripgrep",
                parameters={
                    "pattern": {"type": "string", "required": True},
                    "path": {"type": "string", "default": "."},
                    "include": {"type": "string", "default": None},
                },
            ),
            file_search,
        )
    )

    tools.append(
        (
            ToolSchema(
                "file.tree",
                "List directory tree",
                parameters={
                    "path": {"type": "string", "default": ""},
                },
            ),
            file_tree,
        )
    )

    async def file_patch(
        path: str,
        hunks: list[dict[str, Any]],
        expected_hash: str | None = None,
    ) -> ToolResult:
        target = resolve_inside(workroot, path)
        if target is None:
            return ToolResult(success=False, error="path outside WorkRoot")
        if not target.exists():
            return ToolResult(success=False, error="file not found")

        lock_path = target.with_suffix(target.suffix + ".lock")
        with FileLock(lock_path, timeout=10.0):
            current_hash = _file_hash(target)
            if expected_hash is not None and current_hash != expected_hash:
                return ToolResult(
                    success=False,
                    error="file conflict: content changed before patch",
                    data={
                        "path": str(target.relative_to(workroot)),
                        "expected_hash": expected_hash,
                        "current_hash": current_hash,
                        "conflict": True,
                    },
                )
            content = target.read_text(encoding="utf-8", errors="replace")

            for hunk in hunks:
                old = hunk.get("old_text", "")
                new = hunk.get("new_text", "")
                if not old:
                    return ToolResult(success=False, error="hunk missing old_text")
                if old not in content:
                    return ToolResult(
                        success=False, error=f"hunk not found in file:\n{old[:200]}"
                    )
                content = content.replace(old, new, 1)

            atomic_write(target, content, _nested_lock=True)
        return ToolResult(
            success=True,
            data={
                "path": str(target.relative_to(workroot)),
                "hunks_applied": len(hunks),
                "size": len(content),
                "content_hash": _content_hash(content),
            },
        )

    tools.append(
        (
            ToolSchema(
                "file.patch",
                "Apply patch hunks to a file (search-and-replace)",
                mutates=True,
                parameters={
                    "path": {"type": "string", "required": True},
                    "hunks": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "old_text": {"type": "string"},
                                "new_text": {"type": "string"},
                            },
                        },
                        "required": True,
                    },
                    "expected_hash": {"type": "string", "default": None},
                },
            ),
            file_patch,
        )
    )

    return tools
