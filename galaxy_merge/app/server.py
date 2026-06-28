import asyncio
import json
import threading
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
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
    files = [
        f for f in sorted(notes_dir.iterdir())
        if f.suffix in (".md", ".txt", ".json") and f.name != "index.json"
    ]
    entries = []
    legacy_notes = {}
    for f in files[safe_offset:safe_offset + safe_limit]:
        content = f.read_text()
        entries.append({
            "name": f.stem,
            "path": f.name,
            "content": content,
            "preview": content[:200],
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
    def __init__(self, session: Session, port: int = 0, strict_socket: bool = False):
        self.session = session
        self._socket = None
        try:
            self._socket = reserve_socket(port)
            self.port = self._socket.getsockname()[1]
        except OSError:
            if strict_socket:
                raise
            self.port = port
        self.config_dir = session.gm_dir.parent / "config_templates"
        if not self.config_dir.exists():
            self.config_dir = Path(__file__).resolve().parent.parent / "config_templates"
        self._is_readonly = self._check_launch_inside_codebase()
        self.app = self._build_app()
        self._ws_clients: list[WebSocket] = []
        self._server: uvicorn.Server | None = None
        self._orchestrator: Orchestrator | None = None
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

    def _build_app(self) -> FastAPI:
        app = FastAPI(title="Galaxy Merge Harness")

        @app.get("/api/session")
        def get_session():
            data = self.session.to_dict()
            data["readonly_mode"] = self._is_readonly
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

            self.session.set_goal(goal)
            self.session.event_log.emit("goal_received", session_id=self.session.session_id, goal=goal)
            await self._broadcast({"type": "goal_set", "goal": goal, "status": "understanding"})

            if self._orchestrator is None:
                self._orchestrator = Orchestrator(self.session, self.config_dir, APP_INSTALL_DIR)

            asyncio.create_task(self._execute_goal_and_broadcast(goal))
            return {"status": "accepted", "goal": goal}

        @app.post("/api/stop")
        async def stop_session():
            self.session.mark_completed()
            await self._broadcast({"type": "session_stopped"})
            return {"status": "stopped"}

        @app.post("/api/resume")
        async def resume_session():
            return {"status": "resumed", "session_id": self.session.session_id}

        @app.get("/api/events")
        def get_events():
            return self.session.event_log.replay()

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
            return build_notes_payload(self.session.gm_dir / "notes", limit, offset)

        @app.post("/api/notes")
        async def create_note(data: dict[str, Any]):
            name = data.get("name", "")
            content = data.get("content", "")
            if not name:
                return JSONResponse(content={"error": "name required"}, status_code=400)
            notes_dir = self.session.gm_dir / "notes"
            notes_dir.mkdir(parents=True, exist_ok=True)
            path = notes_dir / f"{name}.md"
            with FileLock(notes_dir / ".notes.lock", timeout=10.0):
                if path.exists():
                    return JSONResponse(content={"error": "note exists"}, status_code=409)
                atomic_write(path, content)
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
                    atomic_write(history_dir / f"{note_id}_{int(__import__('time').time() * 1000)}.md", path.read_text())
                    atomic_write(path, content)
            return {"status": "updated", "name": note_id}

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
            from galaxy_merge.tools.notes_tools import NOTES_INJECTED_FOR_GOAL
            notes_dir = self.session.gm_dir / "notes"
            path = notes_dir / f"{note_id}.md"
            if not path.exists():
                return JSONResponse(content={"error": "not found"}, status_code=404)
            NOTES_INJECTED_FOR_GOAL.append(note_id)
            return {"status": "injected", "name": note_id}

        @app.get("/api/notes/injected")
        async def get_injected_notes():
            from galaxy_merge.tools.notes_tools import get_injected_notes
            return {"injected": get_injected_notes()}

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

        @app.get("/api/safety")
        def get_safety():
            import galaxy_merge.safety.governor as gov
            from galaxy_merge.safety.command_policy import BLOCKED_COMMANDS
            return {
                "active_policy": "default",
                "readonly_mode": self._is_readonly,
                "blocked_commands": list(BLOCKED_COMMANDS),
            }

        @app.websocket("/ws/session/{session_id}")
        async def websocket_endpoint(ws: WebSocket, session_id: str):
            if session_id != self.session.session_id:
                await ws.close(code=4004)
                return
            await ws.accept()
            self._ws_clients.append(ws)
            try:
                while True:
                    await ws.receive_text()
            except WebSocketDisconnect:
                pass
            finally:
                self._ws_clients.remove(ws)

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
        except Exception as exc:
            result = {"error": str(exc), "complete": False}
            self.session.event_log.emit(
                "goal_failed",
                session_id=self.session.session_id,
                error=str(exc),
            )
        await self._broadcast({"type": "goal_result", "result": result})

    async def _broadcast(self, data: dict[str, Any]) -> None:
        dead = []
        for ws in self._ws_clients:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._ws_clients.remove(ws)

    def get_url(self) -> str:
        return f"http://127.0.0.1:{self.port}/"

    def serve(self) -> None:
        if self._socket is None:
            self._socket = reserve_socket(self.port)
            self.port = self._socket.getsockname()[1]
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
    server = SessionServer(session, port=port, strict_socket=True)
    return {"server": server, "port": server.port, "url": server.get_url()}
