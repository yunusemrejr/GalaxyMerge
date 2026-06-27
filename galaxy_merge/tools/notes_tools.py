import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from galaxy_merge.core.locks import FileLock, atomic_write
from galaxy_merge.tools.schemas import ToolSchema, ToolResult


NOTES_DIR_NAME = "notes"


def _get_notes_dir(gm_dir: Path) -> Path:
    return gm_dir / NOTES_DIR_NAME


def _get_index(notes_dir: Path) -> dict[str, Any]:
    index_path = notes_dir / "index.json"
    if index_path.exists():
        with FileLock(index_path.with_suffix(".lock"), timeout=5.0):
            return json.loads(index_path.read_text())
    return {"schema_version": 1, "notes": []}


def _save_index(notes_dir: Path, index: dict[str, Any]) -> None:
    index_path = notes_dir / "index.json"
    atomic_write(index_path, json.dumps(index, indent=2))


def _save_note_version(notes_dir: Path, note_id: str, content: str) -> str:
    history_dir = notes_dir / "history"
    history_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    version_path = history_dir / f"{note_id}_{timestamp}.md"
    atomic_write(version_path, content)
    return version_path.name


def _notes_lock(notes_dir: Path) -> FileLock:
    return FileLock(notes_dir / ".notes.lock", timeout=10.0)


_note_usage: dict[str, dict[str, Any]] = {}
NOTES_INJECTED_FOR_GOAL: list[str] = []


def get_injected_notes() -> list[str]:
    return list(NOTES_INJECTED_FOR_GOAL)


def get_note_usage() -> dict[str, dict[str, Any]]:
    return dict(_note_usage)


def clear_goal_injections() -> None:
    NOTES_INJECTED_FOR_GOAL.clear()


def make_notes_tools(gm_dir: Path) -> list[tuple[ToolSchema, Any]]:
    notes_dir = _get_notes_dir(gm_dir)

    async def notes_create(name: str, content: str = "", title: str | None = None) -> ToolResult:
        notes_dir.mkdir(parents=True, exist_ok=True)
        path = notes_dir / f"{name}.md"
        with _notes_lock(notes_dir):
            if path.exists():
                return ToolResult(success=False, error=f"note '{name}' already exists")
            atomic_write(path, content)

            index = _get_index(notes_dir)
            note_id = f"note_{name}"
            index.setdefault("notes", []).append({
                "id": note_id,
                "path": f"{name}.md",
                "title": title or name,
                "tags": [],
                "pinned": False,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            })
            _save_index(notes_dir, index)
        return ToolResult(success=True, data={"note_id": note_id, "name": name, "created": True})

    async def notes_read(name: str | None = None) -> ToolResult:
        if name:
            path = notes_dir / f"{name}.md"
            if not path.exists():
                return ToolResult(success=False, error=f"note '{name}' not found")
            return ToolResult(success=True, data={"name": name, "content": path.read_text()})

        notes = {}
        if notes_dir.exists():
            for f in sorted(notes_dir.iterdir()):
                if f.suffix == ".md" and f.stem != "index":
                    notes[f.stem] = f.read_text()
        return ToolResult(success=True, data={"notes": notes})

    async def notes_update(name: str, content: str) -> ToolResult:
        path = notes_dir / f"{name}.md"
        if not path.exists():
            return ToolResult(success=False, error=f"note '{name}' not found")

        with _notes_lock(notes_dir):
            if not path.exists():
                return ToolResult(success=False, error=f"note '{name}' not found")
            _save_note_version(notes_dir, name, path.read_text())
            atomic_write(path, content)

            index = _get_index(notes_dir)
            for entry in index.get("notes", []):
                if entry.get("path", "").startswith(name):
                    entry["updated_at"] = datetime.now(timezone.utc).isoformat()
            _save_index(notes_dir, index)
        return ToolResult(success=True, data={"name": name, "updated": True})

    async def notes_rename(name: str, new_name: str) -> ToolResult:
        old_path = notes_dir / f"{name}.md"
        new_path = notes_dir / f"{new_name}.md"
        with _notes_lock(notes_dir):
            if not old_path.exists():
                return ToolResult(success=False, error=f"note '{name}' not found")
            if new_path.exists():
                return ToolResult(success=False, error=f"note '{new_name}' already exists")
            old_path.rename(new_path)

            index = _get_index(notes_dir)
            for entry in index.get("notes", []):
                if entry.get("path", "") == f"{name}.md":
                    entry["path"] = f"{new_name}.md"
                    entry["id"] = f"note_{new_name}"
                    entry["updated_at"] = datetime.now(timezone.utc).isoformat()
            _save_index(notes_dir, index)
        return ToolResult(success=True, data={"from": name, "to": new_name, "renamed": True})

    async def notes_delete(name: str) -> ToolResult:
        path = notes_dir / f"{name}.md"
        with _notes_lock(notes_dir):
            if not path.exists():
                return ToolResult(success=False, error=f"note '{name}' not found")

            trash_dir = notes_dir / ".trash"
            trash_dir.mkdir(parents=True, exist_ok=True)
            _save_note_version(notes_dir, name, path.read_text())
            path.rename(trash_dir / f"{name}.md")

            index = _get_index(notes_dir)
            target_path = f"{name}.md"
            index["notes"] = [n for n in index.get("notes", []) if n.get("path") != target_path]
            _save_index(notes_dir, index)
        return ToolResult(success=True, data={"name": name, "deleted": True, "trashed": True})

    async def notes_restore(name: str) -> ToolResult:
        trash_dir = notes_dir / ".trash"
        trashed = trash_dir / f"{name}.md"
        with _notes_lock(notes_dir):
            if not trashed.exists():
                return ToolResult(success=False, error=f"no trashed note '{name}' found")
            target = notes_dir / f"{name}.md"

            index = _get_index(notes_dir)
            existing = [n for n in index.get("notes", []) if n.get("path") == f"{name}.md"]
            if existing:
                return ToolResult(success=False, error=f"note '{name}' already exists in active notes")

            trashed.rename(target)
            index.setdefault("notes", []).append({
                "id": f"note_{name}",
                "path": f"{name}.md",
                "title": name,
                "tags": [],
                "pinned": False,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            })
            _save_index(notes_dir, index)
        return ToolResult(success=True, data={"name": name, "restored": True})

    async def notes_tag(name: str, tags: list[str]) -> ToolResult:
        with _notes_lock(notes_dir):
            index = _get_index(notes_dir)
            for entry in index.get("notes", []):
                if entry.get("path", "").startswith(name):
                    existing = set(entry.get("tags", []))
                    existing.update(tags)
                    entry["tags"] = list(existing)
            _save_index(notes_dir, index)
        return ToolResult(success=True, data={"name": name, "tags": tags})

    async def notes_pin(name: str, pinned: bool = True) -> ToolResult:
        with _notes_lock(notes_dir):
            index = _get_index(notes_dir)
            for entry in index.get("notes", []):
                if entry.get("path", "").startswith(name):
                    entry["pinned"] = pinned
            _save_index(notes_dir, index)
        return ToolResult(success=True, data={"name": name, "pinned": pinned})

    async def notes_list_indexed() -> ToolResult:
        """Return the note index with metadata (tags, pin, timestamps), not full content."""
        index = _get_index(notes_dir)
        return ToolResult(success=True, data=index)

    async def notes_history_list(name: str) -> ToolResult:
        """List all available versions of a note from history."""
        history_dir = notes_dir / "history"
        if not history_dir.exists():
            return ToolResult(success=True, data={"name": name, "versions": []})
        versions = sorted(history_dir.glob(f"{name}_*.md"))
        result = []
        for v in versions:
            stem = v.stem
            timestamp = "_".join(stem.split("_")[-2:]) if "_" in stem else ""
            result.append({"version": v.name, "timestamp": timestamp})
        return ToolResult(success=True, data={"name": name, "versions": result})

    async def notes_history_read(name: str, version: str) -> ToolResult:
        """Read a specific version of a note from history."""
        history_dir = notes_dir / "history"
        path = history_dir / version
        if not path.exists():
            return ToolResult(success=False, error=f"version '{version}' not found")
        return ToolResult(success=True, data={"name": name, "version": version, "content": path.read_text()})

    async def notes_search(query: str, scope: str = "all") -> ToolResult:
        """Search notes by keyword in content, title, or tags."""
        query_lower = query.lower()
        results = []
        for f in sorted(notes_dir.glob("*.md")):
            if f.stem == "index":
                continue
            if f.parent.name == ".trash":
                continue
            content = f.read_text()
            matched = False
            match_type = []

            if query_lower in content.lower():
                matched = True
                match_type.append("content")
            if query_lower in f.stem.lower():
                matched = True
                match_type.append("title")

            if matched:
                idx = _get_index(notes_dir)
                meta = next((n for n in idx.get("notes", []) if n.get("path") == f.name), {})
                results.append({
                    "name": f.stem,
                    "title": meta.get("title", f.stem),
                    "tags": meta.get("tags", []),
                    "pinned": meta.get("pinned", False),
                    "preview": content[:200],
                    "match_type": match_type,
                })
        return ToolResult(success=True, data={"query": query, "results": results, "count": len(results)})

    async def notes_inject(name: str) -> ToolResult:
        """Inject a selected note into the current goal context."""
        path = notes_dir / f"{name}.md"
        if not path.exists():
            return ToolResult(success=False, error=f"note '{name}' not found")
        content = path.read_text()
        NOTES_INJECTED_FOR_GOAL.append(name)
        return ToolResult(success=True, data={"name": name, "injected": True, "content": content[:500]})

    async def notes_write(name: str, content: str, title: str | None = None) -> ToolResult:
        notes_dir.mkdir(parents=True, exist_ok=True)
        path = notes_dir / f"{name}.md"
        with _notes_lock(notes_dir):
            existed = path.exists()
            if existed:
                _save_note_version(notes_dir, name, path.read_text())
            atomic_write(path, content)

            index = _get_index(notes_dir)
            note_id = f"note_{name}"
            target_path = f"{name}.md"
            existing = [n for n in index.get("notes", []) if n.get("path") == target_path]

            if existing:
                entry = existing[0]
                entry["updated_at"] = datetime.now(timezone.utc).isoformat()
                if title:
                    entry["title"] = title
            else:
                index.setdefault("notes", []).append({
                    "id": note_id,
                    "path": target_path,
                    "title": title or name,
                    "tags": [],
                    "pinned": False,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                })
            _save_index(notes_dir, index)
        return ToolResult(success=True, data={"name": name, "written": True, "created": not existed})

    return [
        (ToolSchema("notes.create", "Create a new project note", mutates=True, parameters={
            "name": {"type": "string", "required": True},
            "content": {"type": "string", "default": ""},
            "title": {"type": "string", "default": None},
        }), notes_create),
        (ToolSchema("notes.write", "Write a note (create or overwrite with history)", mutates=True, parameters={
            "name": {"type": "string", "required": True},
            "content": {"type": "string", "required": True},
            "title": {"type": "string", "default": None},
        }), notes_write),
        (ToolSchema("notes.read", "Read project note(s)", parameters={
            "name": {"type": "string", "default": None},
        }), notes_read),
        (ToolSchema("notes.update", "Update a project note (saves history)", mutates=True, parameters={
            "name": {"type": "string", "required": True},
            "content": {"type": "string", "required": True},
        }), notes_update),
        (ToolSchema("notes.rename", "Rename a project note", mutates=True, parameters={
            "name": {"type": "string", "required": True},
            "new_name": {"type": "string", "required": True},
        }), notes_rename),
        (ToolSchema("notes.delete", "Soft-delete a project note", mutates=True, parameters={
            "name": {"type": "string", "required": True},
        }), notes_delete),
        (ToolSchema("notes.restore", "Restore a soft-deleted note", mutates=True, parameters={
            "name": {"type": "string", "required": True},
        }), notes_restore),
        (ToolSchema("notes.tag", "Tag a project note", mutates=True, parameters={
            "name": {"type": "string", "required": True},
            "tags": {"type": "array", "items": {"type": "string"}, "required": True},
        }), notes_tag),
        (ToolSchema("notes.pin", "Pin or unpin a project note", mutates=True, parameters={
            "name": {"type": "string", "required": True},
            "pinned": {"type": "boolean", "default": True},
        }), notes_pin),
        (ToolSchema("notes.list", "List notes with index metadata (tags, pinned, timestamps)"), notes_list_indexed),
        (ToolSchema("notes.history.list", "List available versions of a note", parameters={
            "name": {"type": "string", "required": True},
        }), notes_history_list),
        (ToolSchema("notes.history.read", "Read a specific version of a note from history", parameters={
            "name": {"type": "string", "required": True},
            "version": {"type": "string", "required": True},
        }), notes_history_read),
        (ToolSchema("notes.search", "Search notes by keyword in content, title, or tags", parameters={
            "query": {"type": "string", "required": True},
            "scope": {"type": "string", "default": "all"},
        }), notes_search),
        (ToolSchema("notes.inject", "Inject a note into the current goal context", mutates=True, parameters={
            "name": {"type": "string", "required": True},
        }), notes_inject),
    ]
