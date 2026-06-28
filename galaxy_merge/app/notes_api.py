"""Notes API endpoints for Galaxy Merge.

Extracted from server.py for modularity.
"""

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi.responses import JSONResponse

from galaxy_merge.app.payloads import (
    _load_notes_index,
    _save_notes_index,
    _upsert_note_index,
    _remove_note_from_index,
    build_notes_payload,
)
from galaxy_merge.core.locks import FileLock, atomic_write


def register_notes_routes(app, session, get_orchestrator):
    """Register all notes-related routes on the FastAPI app."""

    @app.get("/api/notes")
    def get_notes(limit: int = 100, offset: int = 0):
        note_usage = {}
        orchestrator = get_orchestrator()
        if orchestrator and orchestrator.memory_retriever:
            note_usage = orchestrator.memory_retriever.get_note_usage()
        data = build_notes_payload(session.gm_dir / "notes", limit, offset)
        data["usage"] = note_usage
        return data

    @app.post("/api/notes")
    async def create_note(data: dict[str, Any]):
        name = data.get("name", "")
        content = data.get("content", "")
        tags = data.get("tags", [])
        if not name:
            return JSONResponse(content={"error": "name required"}, status_code=400)
        notes_dir = session.gm_dir / "notes"
        notes_dir.mkdir(parents=True, exist_ok=True)
        path = notes_dir / f"{name}.md"
        with FileLock(notes_dir / ".notes.lock", timeout=10.0):
            if path.exists():
                return JSONResponse(content={"error": "note exists"}, status_code=409)
            now = datetime.now(timezone.utc).isoformat()
            atomic_write(path, content, _nested_lock=True)
            _upsert_note_index(
                notes_dir,
                note_name=name,
                path=f"{name}.md",
                created_at=now,
                updated_at=now,
                tags=tags if isinstance(tags, list) else [],
            )
        return {"status": "created", "name": name}

    @app.patch("/api/notes/{note_id}")
    async def update_note(note_id: str, data: dict[str, Any]):
        notes_dir = session.gm_dir / "notes"
        path = notes_dir / f"{note_id}.md"
        content = data.get("content", "")
        with FileLock(notes_dir / ".notes.lock", timeout=10.0):
            if not path.exists():
                return JSONResponse(content={"error": "not found"}, status_code=404)
            if content:
                history_dir = notes_dir / "history"
                history_dir.mkdir(parents=True, exist_ok=True)
                atomic_write(history_dir / f"{note_id}_{int(time.time() * 1000)}.md", path.read_text(), _nested_lock=True)
                atomic_write(path, content, _nested_lock=True)
                index = _load_notes_index(notes_dir)
                for item in index.get("notes", []):
                    if item.get("path") == f"{note_id}.md":
                        item["updated_at"] = datetime.now(timezone.utc).isoformat()
                _save_notes_index(notes_dir, index)
        return {"status": "updated", "name": note_id}

    @app.patch("/api/notes/{note_id}/rename")
    async def rename_note(note_id: str, data: dict[str, Any]):
        notes_dir = session.gm_dir / "notes"
        new_name = str(data.get("new_name", "")).strip()
        if not new_name:
            return JSONResponse(content={"error": "new_name required"}, status_code=400)
        old_path = notes_dir / f"{note_id}.md"
        new_path = notes_dir / f"{new_name}.md"
        index_path = notes_dir / "index.json"
        with FileLock(notes_dir / ".notes.lock", timeout=10.0):
            if not old_path.exists():
                return JSONResponse(content={"error": "not found"}, status_code=404)
            if new_path.exists():
                return JSONResponse(content={"error": "target already exists"}, status_code=409)
            old_path.rename(new_path)
            index = _load_notes_index(index_path, {"schema_version": 1, "notes": []})
            updated = False
            for item in index.get("notes", []):
                if item.get("path") == old_path.name:
                    item["path"] = new_path.name
                    item["id"] = f"note_{new_name}"
                    item["title"] = item.get("title", new_name)
                    item["updated_at"] = datetime.now(timezone.utc).isoformat()
                    updated = True
                    break
            if not updated:
                index.setdefault("notes", []).append({
                    "id": f"note_{new_name}",
                    "path": new_path.name,
                    "title": new_name,
                    "tags": [],
                    "pinned": False,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                })
            _save_data = json.dumps(index, indent=2)
            atomic_write(index_path, _save_data)
        return {"status": "renamed", "from": note_id, "to": new_name}

    @app.patch("/api/notes/{note_id}/tag")
    async def tag_note(note_id: str, data: dict[str, Any]):
        notes_dir = session.gm_dir / "notes"
        tags = data.get("tags", [])
        if not isinstance(tags, list):
            return JSONResponse(content={"error": "tags must be a list"}, status_code=400)
        normalized = []
        for tag in tags:
            tag_value = str(tag).strip()
            if tag_value:
                normalized.append(tag_value)
        index_path = notes_dir / "index.json"
        with FileLock(notes_dir / ".notes.lock", timeout=10.0):
            path = notes_dir / f"{note_id}.md"
            if not path.exists():
                return JSONResponse(content={"error": "not found"}, status_code=404)
            index = _load_notes_index(index_path, {"schema_version": 1, "notes": []})
            target = None
            for item in index.get("notes", []):
                if item.get("path") == path.name:
                    target = item
                    break
            if target is None:
                target = {
                    "id": f"note_{note_id}",
                    "path": path.name,
                    "title": note_id,
                    "tags": [],
                    "pinned": False,
                    "created_at": "",
                    "updated_at": "",
                }
                index.setdefault("notes", []).append(target)
            target["tags"] = sorted(set(normalized))
            target["updated_at"] = datetime.now(timezone.utc).isoformat()
            _save_data = json.dumps(index, indent=2)
            atomic_write(index_path, _save_data)
        return {"status": "tagged", "name": note_id, "tags": normalized}

    @app.patch("/api/notes/{note_id}/pin")
    async def pin_note(note_id: str, data: dict[str, Any]):
        notes_dir = session.gm_dir / "notes"
        pinned = bool(data.get("pinned", True))
        index_path = notes_dir / "index.json"
        with FileLock(notes_dir / ".notes.lock", timeout=10.0):
            path = notes_dir / f"{note_id}.md"
            if not path.exists():
                return JSONResponse(content={"error": "not found"}, status_code=404)
            index = _load_notes_index(index_path, {"schema_version": 1, "notes": []})
            target = None
            for item in index.get("notes", []):
                if item.get("path") == path.name:
                    target = item
                    break
            if target is None:
                target = {
                    "id": f"note_{note_id}",
                    "path": path.name,
                    "title": note_id,
                    "tags": [],
                    "pinned": pinned,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
                index.setdefault("notes", []).append(target)
            target["pinned"] = pinned
            target["updated_at"] = datetime.now(timezone.utc).isoformat()
            _save_data = json.dumps(index, indent=2)
            atomic_write(index_path, _save_data)
        return {"status": "pinned", "name": note_id, "pinned": pinned}

    @app.delete("/api/notes/{note_id}")
    async def delete_note(note_id: str):
        notes_dir = session.gm_dir / "notes"
        path = notes_dir / f"{note_id}.md"
        with FileLock(notes_dir / ".notes.lock", timeout=10.0):
            if not path.exists():
                return JSONResponse(content={"error": "not found"}, status_code=404)
            trash_dir = notes_dir / ".trash"
            trash_dir.mkdir(parents=True, exist_ok=True)
            path.rename(trash_dir / f"{note_id}.md")
            _remove_note_from_index(notes_dir, note_id)
        return {"status": "deleted", "name": note_id}

    @app.post("/api/notes/{note_id}/restore")
    async def restore_note(note_id: str):
        notes_dir = session.gm_dir / "notes"
        trash_path = notes_dir / ".trash" / f"{note_id}.md"
        with FileLock(notes_dir / ".notes.lock", timeout=10.0):
            if not trash_path.exists():
                return JSONResponse(content={"error": "not found in trash"}, status_code=404)
            target = notes_dir / f"{note_id}.md"
            if target.exists():
                return JSONResponse(content={"error": "note exists"}, status_code=409)
            trash_path.rename(target)
            _upsert_note_index(notes_dir, note_id, f"{note_id}.md")
        return {"status": "restored", "name": note_id}

    @app.get("/api/notes/search")
    async def search_notes(q: str = "", limit: int = 50):
        if not q:
            return {"results": []}
        notes_dir = session.gm_dir / "notes"
        if not notes_dir.exists():
            return {"query": q, "results": [], "count": 0}

        index_payload = _load_notes_index(notes_dir / "index.json", {"schema_version": 1, "notes": []})
        index_map = {}
        for item in index_payload.get("notes", []):
            if not isinstance(item, dict):
                continue
            path_name = str(item.get("path", "")).strip()
            if not path_name:
                continue
            index_map[path_name.removesuffix(".md")] = item

        results = []
        q_lower = q.lower()
        for f in sorted(notes_dir.glob("*.md")):
            if f.stem == "index" or f.parent.name == ".trash":
                continue
            try:
                content = f.read_text(errors="replace")
            except OSError:
                continue
            matched = q_lower in content.lower() or q_lower in f.stem.lower()
            if matched:
                item = index_map.get(f.stem, {})
                results.append({
                    "name": f.stem,
                    "path": item.get("path", f"{f.stem}.md"),
                    "title": item.get("title", f.stem),
                    "tags": item.get("tags", []),
                    "pinned": bool(item.get("pinned", False)),
                    "created_at": item.get("created_at", ""),
                    "updated_at": item.get("updated_at", ""),
                    "preview": content[:200],
                })
        total = len(results)
        if limit is not None:
            limit = max(1, min(int(limit), 250))
            results = results[:limit]
        return {"query": q, "results": results, "count": total}

    @app.post("/api/notes/{note_id}/inject")
    async def inject_note(note_id: str):
        from galaxy_merge.tools.notes_tools import _injected_by_gm_dir
        notes_dir = session.gm_dir / "notes"
        path = notes_dir / f"{note_id}.md"
        if not path.exists():
            return JSONResponse(content={"error": "not found"}, status_code=404)
        _injected_by_gm_dir.setdefault(str(session.gm_dir), []).append(note_id)
        return {"status": "injected", "name": note_id}

    @app.get("/api/notes/injected")
    async def get_injected_notes():
        from galaxy_merge.tools.notes_tools import get_injected_notes
        return {"injected": get_injected_notes(session.gm_dir)}

    @app.get("/api/notes/history")
    async def list_note_history(name: str):
        notes_dir = session.gm_dir / "notes"
        history_dir = notes_dir / "history"
        if not history_dir.exists():
            return {"versions": []}
        versions = sorted(history_dir.glob(f"{name}_*.md"))
        result = []
        for v in versions:
            result.append({"version": v.name})
        return {"name": name, "versions": result}

    @app.get("/api/notes/trash")
    async def list_trashed_notes():
        notes_dir = session.gm_dir / "notes"
        trash_dir = notes_dir / ".trash"
        if not trash_dir.exists():
            return {"notes": []}
        files = [f for f in sorted(trash_dir.iterdir()) if f.suffix in (".md", ".txt", ".json")]
        notes = [{"name": f.stem, "path": f.name} for f in files]
        return {"notes": notes}

    @app.get("/api/notes/usage")
    async def get_note_usage():
        orchestrator = get_orchestrator()
        if orchestrator and orchestrator.memory_retriever:
            usage = orchestrator.memory_retriever.get_note_usage()
            return {"usage": usage}
        return {"usage": {}}
