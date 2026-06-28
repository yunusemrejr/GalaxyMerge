import asyncio
import json
from datetime import datetime, timezone
import threading
from pathlib import Path
from typing import Any
from base64 import b64encode
import time

import uvicorn
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

import os
from galaxy_merge.core.session import Session
from galaxy_merge.core.orchestrator import Orchestrator
from galaxy_merge.web.search import WebSearch
from galaxy_merge.github.scanner import GitHubScanner
from galaxy_merge.locations.classifier import LocationClassifier
from galaxy_merge.locations.registry import LocationRegistry
from galaxy_merge.safety.credential_policy import CredentialPolicy
from galaxy_merge.core.concurrency import read_active_port_map
from galaxy_merge.core.locks import FileLock, atomic_write
from galaxy_merge.safety.path_utils import is_relative_to, resolve_inside
from galaxy_merge.browser.manager import BrowserManager
from galaxy_merge.app.ports import reserve_socket

STATIC_DIR = Path(__file__).resolve().parent.parent / "gui" / "static"
APP_INSTALL_DIR = Path(__file__).resolve().parent.parent.parent


def build_locations_payload(workroot: Path, gm_dir: Path, app_install_dir: Path = APP_INSTALL_DIR) -> dict[str, Any]:
    registry = LocationRegistry(gm_dir)
    registry.init_from_project(workroot, gm_dir)
    data = registry.to_dict()
    classifier = LocationClassifier(workroot, gm_dir, app_install_dir)
    classified = [
        classifier.classify(str(workroot), "path"),
        classifier.classify(str(gm_dir), "path"),
    ]
    for remote in data.get("remote_targets", []):
        classified.append({
            "target": remote.get("id", ""),
            "classification": remote.get("classification", "unknown"),
            "host": remote.get("host", ""),
            "path": remote.get("path", ""),
            "repo": remote.get("repo", ""),
            "risk": "high" if remote.get("classification") in ("production_target", "staging_target") else "medium",
            "policy_decision": remote.get("write_policy", "blocked_by_default"),
            "is_remote": True,
            "is_production": remote.get("classification") == "production_target",
            "is_local": False,
        })
    data["classified_locations"] = classified
    return data


def build_logs_payload(log_path: Path, limit: int = 500, offset: int = 0) -> dict[str, Any]:
    safe_limit = max(1, min(limit, 2000))
    safe_offset = max(0, offset)
    if not log_path.exists():
        return {"lines": [], "total": 0, "offset": safe_offset, "limit": safe_limit, "truncated": False}
    lines = log_path.read_text().splitlines()
    window = lines[safe_offset:safe_offset + safe_limit]
    return {
        "lines": window,
        "total": len(lines),
        "offset": safe_offset,
        "limit": safe_limit,
        "truncated": safe_offset + len(window) < len(lines),
    }


def build_notes_payload(notes_dir: Path, limit: int = 100, offset: int = 0) -> dict[str, Any]:
    safe_limit = max(1, min(limit, 500))
    safe_offset = max(0, offset)
    if not notes_dir.exists():
        return {"notes": [], "total": 0, "offset": safe_offset, "limit": safe_limit, "truncated": False}
    index = {}
    index_path = notes_dir / "index.json"
    if index_path.exists():
        try:
            index_data = json.loads(index_path.read_text())
            for item in index_data.get("notes", []):
                index[item.get("path", "").replace(".md", "")] = item
        except (json.JSONDecodeError, OSError):
            index = {}
    files = [
        f for f in sorted(notes_dir.iterdir())
        if f.suffix in (".md", ".txt", ".json") and f.name != "index.json"
    ]
    entries = []
    legacy_notes = {}
    for f in files[safe_offset:safe_offset + safe_limit]:
        content = f.read_text()
        meta = index.get(f.stem, {})
        entries.append({
            "name": f.stem,
            "path": f.name,
            "content": content,
            "preview": content[:200],
            "id": meta.get("id", f"note_{f.stem}"),
            "title": meta.get("title", f.stem),
            "tags": meta.get("tags", []),
            "pinned": bool(meta.get("pinned", False)),
            "created_at": meta.get("created_at", ""),
            "updated_at": meta.get("updated_at", ""),
        })
        legacy_notes[f.stem] = content
    return {
        **legacy_notes,
        "notes": entries,
        "total": len(files),
        "offset": safe_offset,
        "limit": safe_limit,
        "truncated": safe_offset + len(entries) < len(files),
    }


def _read_json_file(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return fallback


def _load_notes_index(notes_dir: Path) -> dict[str, Any]:
    index_path = notes_dir / "index.json"
    payload = _read_json_file(index_path, {"schema_version": 1, "notes": []})
    if not isinstance(payload, dict):
        return {"schema_version": 1, "notes": []}
    payload.setdefault("schema_version", 1)
    notes = payload.get("notes", [])
    if not isinstance(notes, list):
        payload["notes"] = []
    return payload


def _save_notes_index(notes_dir: Path, index: dict[str, Any]) -> None:
    index_path = notes_dir / "index.json"
    atomic_write(index_path, json.dumps(index, indent=2), _nested_lock=True)


def _upsert_note_index(notes_dir: Path, note_name: str, path: str, *, created_at: str | None = None, tags: list[str] | None = None, pinned: bool = False, title: str | None = None, updated_at: str | None = None) -> None:
    notes_dir.mkdir(parents=True, exist_ok=True)
    index = _load_notes_index(notes_dir)
    entries = index.setdefault("notes", [])
    normalized_path = path.strip()
    target = None
    for item in entries:
        if item.get("path") == normalized_path:
            target = item
            break
    if target is None:
        target = {
            "id": f"note_{note_name}",
            "path": normalized_path,
            "title": title or note_name,
            "created_at": created_at or datetime.now(timezone.utc).isoformat(),
            "updated_at": updated_at or datetime.now(timezone.utc).isoformat(),
            "tags": sorted(set(tags or [])),
            "pinned": pinned,
        }
        entries.append(target)
    else:
        if title is not None:
            target["title"] = title
        if created_at is not None:
            target["created_at"] = created_at
        target["updated_at"] = updated_at or datetime.now(timezone.utc).isoformat()
        if tags is not None:
            target["tags"] = sorted(set(tags))
        if pinned:
            target["pinned"] = pinned
        elif pinned is False:
            target["pinned"] = False
    _save_notes_index(notes_dir, index)


def _remove_note_from_index(notes_dir: Path, note_name: str) -> None:
    notes_dir.mkdir(parents=True, exist_ok=True)
    index = _load_notes_index(notes_dir)
    notes = index.get("notes", [])
    if not isinstance(notes, list):
        return
    target_name = f"{note_name}.md"
    index["notes"] = [item for item in notes if item.get("path") != target_name]
    _save_notes_index(notes_dir, index)


def _read_active_sessions(gm_dir: Path, current_session_id: str) -> list[dict[str, Any]]:
    ports = read_active_port_map(gm_dir)
    now = time.time()
    hb_dir = gm_dir / "sessions" / "heartbeats"
    sessions: list[dict[str, Any]] = []
    seen: set[str] = set()
    for session_id, record in sorted(ports.items()):
        seen.add(session_id)
        state_path = gm_dir / "sessions" / session_id / "state.json"
        state = _read_json_file(state_path, {})
        hb = hb_dir / f"{session_id}.hb"
        hb_age = now - hb.stat().st_mtime if hb.exists() else None
        active = hb_age is not None and hb_age < 300
        sessions.append({
            "session_id": session_id,
            "port": record.get("port"),
            "pid": record.get("pid"),
            "workroot": state.get("workroot", gm_dir.parent.as_posix()),
            "status": state.get("status", "unknown"),
            "goal": state.get("goal", ""),
            "active": bool(active),
            "heartbeat_age": round(hb_age, 1) if hb_age is not None else None,
            "error": state.get("error"),
            "goal_state": state.get("status", "unknown"),
            "last_heartbeat": record.get("updated_at"),
        })

    if current_session_id not in seen:
        current_state = _read_json_file(gm_dir / "sessions" / current_session_id / "state.json", {})
        hb = hb_dir / f"{current_session_id}.hb"
        hb_age = now - hb.stat().st_mtime if hb.exists() else None
        current_record = ports.get(current_session_id, {})
        sessions.append({
            "session_id": current_session_id,
            "port": current_record.get("port"),
            "pid": current_record.get("pid"),
            "workroot": current_state.get("workroot", gm_dir.parent.as_posix()),
            "status": current_state.get("status", "unknown"),
            "goal": current_state.get("goal", ""),
            "active": hb_age is not None and hb_age < 300,
            "heartbeat_age": round(hb_age, 1) if hb_age is not None else None,
            "error": current_state.get("error"),
            "goal_state": current_state.get("status", "unknown"),
            "last_heartbeat": hb.stat().st_mtime if hb.exists() else None,
        })

    sessions.sort(key=lambda item: (not item["active"], item["session_id"]))
    return sessions


def _redact_nested(value: Any, policy: CredentialPolicy) -> Any:
    if isinstance(value, str):
        return policy.redact(value)
    if isinstance(value, list):
        return [_redact_nested(item, policy) for item in value]
    if isinstance(value, dict):
        return {key: _redact_nested(item, policy) for key, item in value.items()}
    return value


def build_council_event_summary(events: list[dict[str, Any]], workroot: Path, limit: int = 200) -> dict[str, Any]:
    policy = CredentialPolicy(workroot)
    recent = events[-max(1, min(limit, 1000)):]
    rows_by_key: dict[tuple[str, str, str], dict[str, Any]] = {}
    provider_failures: list[dict[str, Any]] = []
    fallback_events: list[dict[str, Any]] = []

    for raw_event in recent:
        event = _redact_nested(raw_event, policy)
        event_name = event.get("event", "")
        role = event.get("role", "")
        provider_id = event.get("provider_id") or event.get("provider") or event.get("to_provider", "")
        model = event.get("model", "")
        key = (role, provider_id, model)

        if event_name == "provider_called":
            rows_by_key[key] = {
                "role": role,
                "provider": provider_id,
                "provider_id": provider_id,
                "model": model,
                "status": "called",
                "attempt": event.get("attempt"),
                "time": event.get("time"),
            }
        elif event_name == "role_execution_failed":
            rows_by_key[key] = {
                "role": role,
                "provider": provider_id,
                "provider_id": provider_id,
                "model": model,
                "status": "degraded",
                "error": event.get("error", ""),
                "error_type": event.get("error_type", ""),
                "attempt": event.get("attempt"),
                "retry_count": event.get("retry_count"),
                "fallback_decision": event.get("fallback_decision", ""),
                "duration_ms": event.get("duration_ms"),
                "time": event.get("time"),
            }
        elif event_name == "provider_failed":
            failure = {
                "role": role,
                "provider": provider_id,
                "provider_id": provider_id,
                "model": model,
                "status": "failed",
                "error": event.get("error", ""),
                "error_type": event.get("error_type", ""),
                "attempt": event.get("attempt"),
                "retry_count": event.get("retry_count"),
                "fallback_decision": event.get("fallback_decision", ""),
                "duration_ms": event.get("duration_ms"),
                "time": event.get("time"),
            }
            provider_failures.append(failure)
            rows_by_key[key] = failure
        elif event_name == "role_fallback":
            fallback = {
                "role": role,
                "from_provider": event.get("from_provider", ""),
                "to_provider": event.get("to_provider", ""),
                "provider": event.get("to_provider", ""),
                "model": model,
                "status": "fallback",
                "fallback_decision": event.get("fallback_decision", ""),
                "retry_count": event.get("retry_count"),
                "time": event.get("time"),
            }
            fallback_events.append(fallback)

    return {
        "roles": list(rows_by_key.values()),
        "degraded_roles": sorted({
            row.get("role", "")
            for row in rows_by_key.values()
            if row.get("role") and row.get("status") in {"degraded", "failed"}
        }),
        "provider_failures": provider_failures,
        "fallback_events": fallback_events,
    }


class SessionServer:
    def __init__(self, session: Session, port: int = 0):
        self.session = session
        self._socket = reserve_socket(port)
        self.port = self._socket.getsockname()[1]
        self.config_dir = session.gm_dir.parent / "config_templates"
        if not self.config_dir.exists():
            self.config_dir = Path(__file__).resolve().parent.parent / "config_templates"
        self._is_readonly = self._check_launch_inside_codebase()
        self.app = self._build_app()
        self._ws_clients: list[WebSocket] = []
        self._server: uvicorn.Server | None = None
        self._orchestrator: Orchestrator | None = None
        self._goal_task: asyncio.Task | None = None
        self._browser_manager = BrowserManager(session.gm_dir)

    def _check_launch_inside_codebase(self) -> bool:
        try:
            import galaxy_merge
            pkg_path = Path(galaxy_merge.__file__).resolve().parent
            workroot = self.session.workroot.resolve()
            if is_relative_to(workroot, pkg_path.parent):
                return True
        except Exception:
            pass
        return False

    def _browser_session_id(self, label: str = "gui") -> str:
        if label in ("gui", ""):
            return f"{self.session.session_id}:gui"
        if label.startswith(f"{self.session.session_id}:"):
            return label
        return f"{self.session.session_id}:{label}"

    def _build_app(self) -> FastAPI:
        app = FastAPI(title="Galaxy Merge Harness")

        @app.get("/api/session")
        def get_session():
            data = self.session.to_dict()
            data["readonly_mode"] = self._is_readonly
            data["goal_state"] = data.get("status", "idle")
            return data

        @app.get("/api/project")
        def get_project():
            gm_dir = self.session.gm_dir
            project_json = gm_dir / "project.json"
            if project_json.exists():
                data = json.loads(project_json.read_text())
                data["readonly_mode"] = self._is_readonly
                return data
            return {"workroot": str(self.session.workroot), "readonly_mode": self._is_readonly}

        @app.get("/api/sessions")
        def get_active_sessions():
            sessions = _read_active_sessions(self.session.gm_dir, self.session.session_id)
            return {
                "sessions": sessions,
                "current_session_id": self.session.session_id,
            }

        @app.get("/api/tree")
        def get_tree(path: str = "", max_entries: int = 500):
            base = self.session.workroot
            target = resolve_inside(base, path) if path else base
            if target is None:
                return JSONResponse(content={"error": "path outside WorkRoot"}, status_code=403)
            result = _build_tree(target, base, max_entries=max(1, min(max_entries, 5000)))
            return result

        _api_cred_policy = CredentialPolicy(self.session.workroot)

        @app.get("/api/file")
        def get_file(path: str):
            target = resolve_inside(self.session.workroot, path)
            if target is None:
                return JSONResponse(content={"error": "path outside WorkRoot"}, status_code=403)
            if not target.exists() or not target.is_file():
                return JSONResponse(content={"error": "file not found"}, status_code=404)
            cred_result = _api_cred_policy.check_path(target)
            if cred_result["decision"] == "block":
                return JSONResponse(content={"error": "access denied: sensitive file"}, status_code=403)
            content = target.read_text(encoding="utf-8", errors="replace")
            content = _api_cred_policy.redact(content)
            return {"path": path, "content": content}

        @app.post("/api/goal")
        async def post_goal(data: dict[str, Any]):
            goal = data.get("goal", "")
            if not goal:
                return JSONResponse(content={"error": "goal is required"}, status_code=400)
            if self._is_readonly:
                return JSONResponse(content={"error": "read-only mode: cannot execute goals on Galaxy Merge codebase"}, status_code=403)
            if self._goal_task and not self._goal_task.done():
                return JSONResponse(content={"error": "goal already in progress"}, status_code=409)

            self.session.set_goal(goal)
            self.session.event_log.emit("goal_received", session_id=self.session.session_id, goal=goal)
            await self._broadcast({"type": "goal_set", "goal": goal, "status": "understanding"})

            if self._orchestrator is None:
                self._orchestrator = Orchestrator(self.session, self.config_dir, APP_INSTALL_DIR)

            self._goal_task = asyncio.create_task(self._execute_goal_and_broadcast(goal))
            return {"status": "accepted", "goal": goal}

        @app.post("/api/stop")
        async def stop_session():
            if self._goal_task and not self._goal_task.done():
                self._goal_task.cancel()
            self.session.mark_stopped("stopped")
            self.session.event_log.emit("session_stopped", session_id=self.session.session_id)
            await self._broadcast({"type": "session_stopped"})
            return {"status": "stopped"}

        @app.post("/api/resume")
        async def resume_session():
            if not self.session.can_resume():
                return JSONResponse(content={"error": "session cannot be resumed"}, status_code=409)
            if not self.session.resume():
                return JSONResponse(content={"error": "session resume blocked"}, status_code=409)
            self.session.mark_running()
            self.session.event_log.emit(
                "session_resumed",
                session_id=self.session.session_id,
                goal=self.session._state.get("goal", ""),
            )
            await self._broadcast({"type": "session_resumed"})
            return {
                "status": "resumed",
                "session_id": self.session.session_id,
                "goal": self.session._state.get("goal", ""),
            }

        @app.get("/api/events")
        def get_events(
            request: Request,
            limit: int = 500,
            offset: int = 0,
            since: int | None = None,
            redact: bool = True,
        ):
            events, total, next_offset = self._events_payload(
                limit=limit,
                offset=offset,
                since=since,
                redact=redact,
            )
            if request.url.query:
                return {
                    "events": events,
                    "offset": offset,
                    "since": since,
                    "limit": limit,
                    "next_offset": next_offset,
                    "total": total,
                    "truncated": next_offset < total,
                }
            return events

        @app.get("/api/logs")
        def get_logs(limit: int = 500, offset: int = 0):
            return build_logs_payload(self.session.gm_dir / "logs" / "project.log", limit, offset)

        @app.get("/api/council")
        def get_council():
            if self._orchestrator:
                policy = CredentialPolicy(self.session.workroot)
                summary = build_council_event_summary(
                    self.session.event_log.replay(),
                    self.session.workroot,
                )
                providers = _redact_nested(self._orchestrator.providers.available_providers(), policy)
                warnings = _redact_nested(self._orchestrator.providers.load_errors(), policy)
                return {
                    "tools": self._orchestrator.tool_kernel.list_tools(),
                    "providers": providers,
                    "warnings": warnings,
                    **summary,
                }
            return {"tools": [], "providers": [], "roles": [], "degraded_roles": []}

        @app.get("/api/tools")
        def get_tools():
            if self._orchestrator:
                return {"tools": self._orchestrator.tool_kernel.list_tools()}
            return {"tools": []}

        @app.get("/api/notes")
        def get_notes(limit: int = 100, offset: int = 0):
            note_usage = {}
            if self._orchestrator and self._orchestrator.memory_retriever:
                note_usage = self._orchestrator.memory_retriever.get_note_usage()
            data = build_notes_payload(self.session.gm_dir / "notes", limit, offset)
            data["usage"] = note_usage
            return data

        @app.post("/api/notes")
        async def create_note(data: dict[str, Any]):
            name = data.get("name", "")
            content = data.get("content", "")
            tags = data.get("tags", [])
            if not name:
                return JSONResponse(content={"error": "name required"}, status_code=400)
            notes_dir = self.session.gm_dir / "notes"
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
            notes_dir = self.session.gm_dir / "notes"
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
            notes_dir = self.session.gm_dir / "notes"
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
                index = _read_json_file(index_path, {"schema_version": 1, "notes": []})
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
            notes_dir = self.session.gm_dir / "notes"
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
                index = _read_json_file(index_path, {"schema_version": 1, "notes": []})
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
            notes_dir = self.session.gm_dir / "notes"
            pinned = bool(data.get("pinned", True))
            index_path = notes_dir / "index.json"
            with FileLock(notes_dir / ".notes.lock", timeout=10.0):
                path = notes_dir / f"{note_id}.md"
                if not path.exists():
                    return JSONResponse(content={"error": "not found"}, status_code=404)
                index = _read_json_file(index_path, {"schema_version": 1, "notes": []})
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
            notes_dir = self.session.gm_dir / "notes"
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
            notes_dir = self.session.gm_dir / "notes"
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
        async def search_notes(q: str = ""):
            if not q:
                return {"results": []}
            notes_dir = self.session.gm_dir / "notes"
            results = []
            q_lower = q.lower()
            for f in sorted(notes_dir.glob("*.md")):
                if f.stem == "index" or f.parent.name == ".trash":
                    continue
                content = f.read_text()
                matched = q_lower in content.lower() or q_lower in f.stem.lower()
                if matched:
                    results.append({"name": f.stem, "preview": content[:200]})
            return {"query": q, "results": results, "count": len(results)}

        @app.post("/api/notes/{note_id}/inject")
        async def inject_note(note_id: str):
            from galaxy_merge.tools.notes_tools import _injected_by_gm_dir
            notes_dir = self.session.gm_dir / "notes"
            path = notes_dir / f"{note_id}.md"
            if not path.exists():
                return JSONResponse(content={"error": "not found"}, status_code=404)
            _injected_by_gm_dir.setdefault(str(self.session.gm_dir), []).append(note_id)
            return {"status": "injected", "name": note_id}

        @app.get("/api/notes/injected")
        async def get_injected_notes():
            from galaxy_merge.tools.notes_tools import get_injected_notes
            return {"injected": get_injected_notes(self.session.gm_dir)}

        @app.get("/api/notes/history")
        async def list_note_history(name: str):
            notes_dir = self.session.gm_dir / "notes"
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
            notes_dir = self.session.gm_dir / "notes"
            trash_dir = notes_dir / ".trash"
            if not trash_dir.exists():
                return {"notes": []}
            files = [f for f in sorted(trash_dir.iterdir()) if f.suffix in (".md", ".txt", ".json")]
            notes = [{"name": f.stem, "path": f.name} for f in files]
            return {"notes": notes}

        @app.get("/api/notes/usage")
        async def get_note_usage():
            if self._orchestrator and self._orchestrator.memory_retriever:
                usage = self._orchestrator.memory_retriever.get_note_usage()
                return {"usage": usage}
            return {"usage": {}}

        @app.get("/api/web/search")
        async def web_search(q: str, source: str = "duckduckgo"):
            searcher = WebSearch()
            results = searcher.search(q, source)
            return {"query": q, "source": source, "results": results}

        @app.post("/api/web/fetch")
        async def web_fetch(data: dict[str, Any]):
            url = data.get("url", "")
            if not url:
                return JSONResponse(content={"error": "url required"}, status_code=400)
            from galaxy_merge.web.fetch import fetch_page
            result = fetch_page(url)
            return result

        @app.get("/api/browser/sessions")
        def browser_sessions():
            sessions = []
            for session in self._browser_manager.list_sessions():
                sid = session.get("session_id", "")
                if sid == f"{self.session.session_id}:gui":
                    sessions.append({**session, "session_id": "gui"})
            return {"sessions": sessions}

        @app.post("/api/browser/open")
        async def browser_open(data: dict[str, Any]):
            url = data.get("url", "about:blank")
            result = self._browser_manager.open_session(f"{self.session.session_id}:gui", url)
            if result.get("success"):
                result["session_id"] = "gui"
            return result

        @app.get("/api/browser/console")
        def browser_console():
            from galaxy_merge.browser.console_logs import ConsoleLogCollector
            collector = ConsoleLogCollector(f"{self.session.session_id}:gui", self.session.gm_dir)
            return {"logs": collector.get_logs()}

        @app.get("/api/browser/network")
        def browser_network():
            from galaxy_merge.browser.network_logs import NetworkLogCollector
            collector = NetworkLogCollector(self.session.gm_dir, f"{self.session.session_id}:gui")
            return {"logs": collector.get_logs()}

        @app.get("/api/browser/errors")
        def browser_errors():
            from galaxy_merge.browser.page_errors import PageErrorCollector
            collector = PageErrorCollector(self.session.gm_dir, f"{self.session.session_id}:gui")
            return {"errors": collector.get_errors()}

        @app.get("/api/browser/screenshot")
        def browser_screenshot(session_id: str = "gui"):
            target = self._browser_session_id(session_id)
            result = self._browser_manager.screenshot(target)
            if not result.get("success"):
                return result
            screenshot_path = result.get("screenshot_path", "")
            if screenshot_path:
                path = Path(screenshot_path)
                if path.exists():
                    result["screenshot_file"] = path.name
                    with path.open("rb") as fp:
                        result["image_data"] = b64encode(fp.read()).decode("ascii")
            return result

        @app.get("/api/github/scan")
        async def github_scan(url: str):
            import os
            token = os.environ.get("GITHUB_TOKEN", os.environ.get("GH_TOKEN", ""))
            scanner = GitHubScanner(token=token)
            result = await scanner.scan_repo(url)
            return result

        @app.get("/api/locations")
        def get_locations():
            return build_locations_payload(self.session.workroot, self.session.gm_dir, APP_INSTALL_DIR)

        @app.get("/api/memory")
        async def get_memory(kind: str = "all"):
            from galaxy_merge.memory.store import MemoryStore
            store = MemoryStore(self.session.gm_dir / "memory")
            if kind == "all":
                kinds = ["facts", "failures", "fixes", "lessons"]
                result = {}
                for k in kinds:
                    records = store.read_recent(k, 20)
                    result[k] = records
                return {"memory": result}
            else:
                records = store.read_recent(kind, 20)
                return {"kind": kind, "records": records}

        @app.get("/api/skills")
        async def get_skills():
            from galaxy_merge.skills.registry import SkillRegistry
            registry = SkillRegistry(self.session.gm_dir)
            return {"skills": registry.list_all(), "count": registry.count()}

        @app.get("/api/safety")
        def get_safety():
            import galaxy_merge.safety.governor as gov
            from galaxy_merge.safety.command_policy import BLOCKED_COMMANDS
            blocked_actions = []
            if self._orchestrator and self._orchestrator.safety_audit:
                blocked_actions = self._orchestrator.safety_audit.recent(200)
            return {
                "active_policy": "default",
                "readonly_mode": self._is_readonly,
                "blocked_commands": list(BLOCKED_COMMANDS),
                "blocked_actions": blocked_actions,
            }

        @app.post("/api/secret-scan")
        async def secret_scan(data: dict[str, Any] | None = None):
            data = data or {}
            include_history = data.get("include_history", False)
            from galaxy_merge.tools.security_tools import make_security_tools
            schemas_and_handlers = make_security_tools(self.session.workroot, APP_INSTALL_DIR)
            for schema, handler in schemas_and_handlers:
                if schema.name == "secret.scan":
                    result = await handler(include_history=include_history)
                    return {"success": result.success, "data": result.data, "error": result.error}
            return JSONResponse(content={"error": "secret scan tool not available"}, status_code=500)

        @app.websocket("/ws/session/{session_id}")
        async def websocket_endpoint(ws: WebSocket, session_id: str, since: int | None = 0):
            if session_id != self.session.session_id:
                await ws.close(code=4004)
                return
            await ws.accept()
            self._ws_clients.append(ws)
            await self._send_replay(ws, since=since or 0)
            try:
                while True:
                    payload = await ws.receive_json()
                    if not isinstance(payload, dict):
                        continue
                    cursor = payload.get("since")
                    if cursor is not None:
                        try:
                            cursor_int = int(cursor)
                        except (TypeError, ValueError):
                            continue
                        await self._send_replay(ws, since=cursor_int)
            except WebSocketDisconnect:
                pass
            except asyncio.CancelledError:
                pass
            except Exception:
                pass
            finally:
                try:
                    self._ws_clients.remove(ws)
                except ValueError:
                    pass

        @app.on_event("startup")
        async def on_startup():
            self._orchestrator = Orchestrator(self.session, self.config_dir, APP_INSTALL_DIR)
            await self._orchestrator.initialize()

        if STATIC_DIR.exists():
            app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")

        return app

    async def _execute_goal_and_broadcast(self, goal: str) -> None:
        if self._orchestrator is None:
            self._orchestrator = Orchestrator(self.session, self.config_dir, APP_INSTALL_DIR)
            await self._orchestrator.initialize()
        try:
            result = await self._orchestrator.execute_goal(goal)
        except asyncio.CancelledError:
            self.session.event_log.emit(
                "goal_cancelled",
                session_id=self.session.session_id,
                goal=goal,
            )
            return
        except Exception as exc:
            result = {"error": str(exc), "complete": False}
            self.session.event_log.emit(
                "goal_failed",
                session_id=self.session.session_id,
                error=str(exc),
            )
        await self._broadcast({"type": "goal_result", "result": result})

    async def _broadcast(self, data: dict[str, Any]) -> None:
        clients = list(self._ws_clients)
        dead = []
        for ws in clients:
            sent = await self._send_with_timeout(ws, data)
            if not sent:
                dead.append(ws)
        for ws in dead:
            try:
                self._ws_clients.remove(ws)
            except ValueError:
                pass

    def _events_payload(
        self,
        limit: int = 500,
        offset: int = 0,
        since: int | None = None,
        redact: bool = True,
    ) -> tuple[list[dict[str, Any]], int, int]:
        safe_limit = max(1, min(limit, 2000))
        safe_offset = max(0, offset)
        start = max(0, since if since is not None else safe_offset)
        events = self.session.event_log.replay()
        total = len(events)
        window = events[start:start + safe_limit]
        if redact:
            policy = CredentialPolicy(self.session.workroot)
            window = [_redact_nested(event, policy) for event in window]
        next_offset = start + len(window)
        return window, total, next_offset

    async def _send_with_timeout(self, ws: WebSocket, payload: dict[str, Any], timeout: float = 1.5) -> bool:
        try:
            await asyncio.wait_for(ws.send_json(payload), timeout=timeout)
            return True
        except (asyncio.TimeoutError, Exception):
            return False

    async def _send_replay(self, ws: WebSocket, since: int = 0, limit: int = 200) -> None:
        start = max(0, since)
        events, _, _ = self._events_payload(limit=limit, since=start)
        for event in events:
            if not await self._send_with_timeout(ws, event):
                return
        await self._send_with_timeout(
            ws,
            {
                "type": "events_replayed",
                "count": len(events),
                "since": start,
            },
        )

    def get_url(self) -> str:
        return f"http://127.0.0.1:{self.port}/"

    def serve(self) -> None:
        config = uvicorn.Config(
            self.app,
            host="127.0.0.1",
            port=self.port,
            log_level="warning",
            access_log=False,
        )
        self._server = uvicorn.Server(config)
        self._server.run(sockets=[self._socket])


def _build_tree(path: Path, base: Path, max_entries: int = 500) -> dict[str, Any]:
    counter = {"count": 0, "truncated": False}

    def build(current: Path) -> dict[str, Any]:
        result: dict[str, Any] = {"name": current.name, "type": "directory", "children": []}
        if current.is_dir():
            try:
                for child in sorted(current.iterdir()):
                    if counter["count"] >= max_entries:
                        counter["truncated"] = True
                        break
                    if child.name.startswith(".") and child.name != ".gm":
                        continue
                    if child.name == "node_modules":
                        continue
                    counter["count"] += 1
                    if child.is_dir():
                        result["children"].append(build(child))
                    else:
                        size = child.stat().st_size if child.exists() else 0
                        result["children"].append({"name": child.name, "type": "file", "size": size})
            except PermissionError:
                pass
        return result

    tree = build(path)
    tree["entry_count"] = counter["count"]
    tree["truncated"] = counter["truncated"]
    tree["max_entries"] = max_entries
    return tree


def start_server(session: Session, port: int = 0) -> dict:
    server = SessionServer(session, port=port)
    return {"server": server, "port": server.port, "url": server.get_url()}
