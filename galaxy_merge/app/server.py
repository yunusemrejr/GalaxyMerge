"""Galaxy Merge Session Server — FastAPI application and WebSocket gateway.

This module coordinates the HTTP API, WebSocket event streaming, and browser
GUI serving. Business logic is delegated to focused modules:
- payloads: response builders (locations, logs, notes, council summaries, tree)
- notes_api: notes CRUD route registration
- orchestrator: goal execution and tool/provider coordination
- session: session state and event logging
"""

import asyncio
import json
import os
from base64 import b64encode
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from galaxy_merge.app.notes_api import register_notes_routes
from galaxy_merge.app.payloads import (
    build_council_event_summary,
    build_locations_payload,
    build_logs_payload,
    build_tree,
    _redact_nested,
)
from galaxy_merge.app.ports import reserve_socket
from galaxy_merge.browser.manager import BrowserManager
from galaxy_merge.browser.console_logs import ConsoleLogCollector
from galaxy_merge.browser.network_logs import NetworkLogCollector
from galaxy_merge.browser.page_errors import PageErrorCollector
from galaxy_merge.core.orchestrator import Orchestrator
from galaxy_merge.core.session import Session
from galaxy_merge.github.scanner import GitHubScanner
from galaxy_merge.safety.credential_policy import CredentialPolicy
from galaxy_merge.safety.path_utils import is_relative_to, resolve_inside
from galaxy_merge.web.fetch import fetch_page
from galaxy_merge.web.search import WebSearch

STATIC_DIR = Path(__file__).resolve().parent.parent / "gui" / "static"
APP_INSTALL_DIR = Path(__file__).resolve().parent.parent.parent
_build_tree = build_tree


class SessionServer:
    def __init__(self, session: Session, port: int = 0):
        self.session = session
        self._socket = reserve_socket(port)
        self.port = self._socket.getsockname()[1]
        self.config_dir = session.gm_dir.parent / "config_templates"
        if not self.config_dir.exists():
            self.config_dir = (
                Path(__file__).resolve().parent.parent / "config_templates"
            )
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

    def _get_orchestrator(self) -> Orchestrator | None:
        return self._orchestrator

    def _build_app(self) -> FastAPI:
        app = FastAPI(title="Galaxy Merge Harness")

        # --- Session & Project ---
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
            return {
                "workroot": str(self.session.workroot),
                "readonly_mode": self._is_readonly,
            }

        @app.get("/api/sessions")
        def get_active_sessions():
            from galaxy_merge.app.payloads import _read_active_sessions

            sessions = _read_active_sessions(
                self.session.gm_dir, self.session.session_id
            )
            return {
                "sessions": sessions,
                "current_session_id": self.session.session_id,
            }

        # --- File Tree & File Content ---
        @app.get("/api/tree")
        def get_tree(path: str = "", max_entries: int = 500):
            base = self.session.workroot
            target = resolve_inside(base, path) if path else base
            if target is None:
                return JSONResponse(
                    content={"error": "path outside WorkRoot"}, status_code=403
                )
            return build_tree(target, base, max_entries=max(1, min(max_entries, 5000)))

        _api_cred_policy = CredentialPolicy(self.session.workroot)

        @app.get("/api/file")
        def get_file(path: str):
            target = resolve_inside(self.session.workroot, path)
            if target is None:
                return JSONResponse(
                    content={"error": "path outside WorkRoot"}, status_code=403
                )
            if not target.exists() or not target.is_file():
                return JSONResponse(
                    content={"error": "file not found"}, status_code=404
                )
            cred_result = _api_cred_policy.check_path(target)
            if cred_result["decision"] == "block":
                return JSONResponse(
                    content={"error": "access denied: sensitive file"}, status_code=403
                )
            content = target.read_text(encoding="utf-8", errors="replace")
            content = _api_cred_policy.redact(content)
            return {"path": path, "content": content}

        # --- Goal Management ---
        @app.post("/api/goal")
        async def post_goal(data: dict[str, Any]):
            goal = data.get("goal", "")
            if not goal:
                return JSONResponse(
                    content={"error": "goal is required"}, status_code=400
                )
            if self._is_readonly:
                return JSONResponse(
                    content={
                        "error": "read-only mode: cannot execute goals on Galaxy Merge codebase"
                    },
                    status_code=403,
                )
            if self._goal_task and not self._goal_task.done():
                return JSONResponse(
                    content={"error": "goal already in progress"}, status_code=409
                )

            self.session.set_goal(goal)
            self.session.event_log.emit(
                "goal_received", session_id=self.session.session_id, goal=goal
            )
            await self._broadcast(
                {"type": "goal_set", "goal": goal, "status": "understanding"}
            )

            if self._orchestrator is None:
                self._orchestrator = Orchestrator(
                    self.session, self.config_dir, APP_INSTALL_DIR
                )

            self._goal_task = asyncio.create_task(
                self._execute_goal_and_broadcast(goal)
            )
            return {"status": "accepted", "goal": goal}

        @app.post("/api/stop")
        async def stop_session():
            if self._goal_task and not self._goal_task.done():
                self._goal_task.cancel()
            self.session.mark_stopped("stopped")
            self.session.event_log.emit(
                "session_stopped", session_id=self.session.session_id
            )
            await self._broadcast({"type": "session_stopped"})
            return {"status": "stopped"}

        @app.post("/api/resume")
        async def resume_session():
            if not self.session.can_resume():
                return JSONResponse(
                    content={"error": "session cannot be resumed"}, status_code=409
                )
            if not self.session.resume():
                return JSONResponse(
                    content={"error": "session resume blocked"}, status_code=409
                )
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

        # --- Events & Logs ---
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
            return build_logs_payload(
                self.session.gm_dir / "logs" / "project.log", limit, offset
            )

        # --- Council & Tools ---
        @app.get("/api/council")
        def get_council():
            if self._orchestrator:
                policy = CredentialPolicy(self.session.workroot)
                summary = build_council_event_summary(
                    self.session.event_log.replay(),
                    self.session.workroot,
                )
                providers = _redact_nested(
                    self._orchestrator.providers.available_providers(), policy
                )
                warnings = _redact_nested(
                    self._orchestrator.providers.load_errors(), policy
                )
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

        # --- Notes (delegated to notes_api module) ---
        register_notes_routes(app, self.session, self._get_orchestrator)

        # --- Web Search & Fetch ---
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
            result = fetch_page(url)
            return result

        # --- Browser ---
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
            result = self._browser_manager.open_session(
                f"{self.session.session_id}:gui", url
            )
            if result.get("success"):
                result["session_id"] = "gui"
            return result

        @app.get("/api/browser/console")
        def browser_console():
            collector = ConsoleLogCollector(
                f"{self.session.session_id}:gui", self.session.gm_dir
            )
            return {"logs": collector.get_logs()}

        @app.get("/api/browser/network")
        def browser_network():
            collector = NetworkLogCollector(
                self.session.gm_dir, f"{self.session.session_id}:gui"
            )
            return {"logs": collector.get_logs()}

        @app.get("/api/browser/errors")
        def browser_errors():
            collector = PageErrorCollector(
                self.session.gm_dir, f"{self.session.session_id}:gui"
            )
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

        # --- GitHub ---
        @app.get("/api/github/scan")
        async def github_scan(url: str):
            token = os.environ.get("GITHUB_TOKEN", os.environ.get("GH_TOKEN", ""))
            scanner = GitHubScanner(token=token)
            result = await scanner.scan_repo(url)
            return result

        # --- Locations ---
        @app.get("/api/locations")
        def get_locations():
            return build_locations_payload(
                self.session.workroot, self.session.gm_dir, APP_INSTALL_DIR
            )

        # --- Memory ---
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

        # --- Skills ---
        @app.get("/api/skills")
        async def get_skills():
            from galaxy_merge.skills.registry import SkillRegistry

            registry = SkillRegistry(self.session.gm_dir)
            return {"skills": registry.list_all(), "count": registry.count()}

        # --- Safety ---
        @app.get("/api/safety")
        def get_safety():
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

        # --- Secret Scan ---
        @app.post("/api/secret-scan")
        async def secret_scan(data: dict[str, Any] | None = None):
            data = data or {}
            include_history = data.get("include_history", False)
            from galaxy_merge.tools.security_tools import make_security_tools

            schemas_and_handlers = make_security_tools(
                self.session.workroot, APP_INSTALL_DIR
            )
            for schema, handler in schemas_and_handlers:
                if schema.name == "secret.scan":
                    result = await handler(include_history=include_history)
                    return {
                        "success": result.success,
                        "data": result.data,
                        "error": result.error,
                    }
            return JSONResponse(
                content={"error": "secret scan tool not available"}, status_code=500
            )

        # --- Health ---
        @app.get("/api/health")
        def get_health():
            from galaxy_merge.core.session import validate_gm_structure

            gm_validation = validate_gm_structure(self.session.gm_dir)

            tools_count = 0
            providers_loaded = 0
            providers_available = 0
            if self._orchestrator is not None:
                try:
                    tools_count = len(self._orchestrator.tool_kernel.list_tools())
                except Exception:
                    tools_count = 0
                try:
                    providers = self._orchestrator.providers.available_providers()
                    providers_loaded = len(providers)
                    providers_available = sum(
                        1 for p in providers if p.get("available", True)
                    )
                except Exception:
                    providers_loaded = 0
                    providers_available = 0

            events_log = (
                self.session.gm_dir
                / "sessions"
                / self.session.session_id
                / "events.jsonl"
            )
            recent_events = 0
            try:
                if events_log.exists():
                    with events_log.open("r", encoding="utf-8") as fp:
                        for _ in fp:
                            recent_events += 1
            except OSError:
                pass

            ok = bool(gm_validation.get("ok")) and self.session is not None
            return {
                "ok": ok,
                "session_id": self.session.session_id,
                "workroot": str(self.session.workroot),
                "gm_dir": str(self.session.gm_dir),
                "gm_validation": gm_validation,
                "tools_count": tools_count,
                "providers_loaded": providers_loaded,
                "providers_available": providers_available,
                "session_status": self.session._state.get("status", "unknown"),
                "events_recorded": recent_events,
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }

        # --- WebSocket ---
        @app.websocket("/ws/session/{session_id}")
        async def websocket_endpoint(
            ws: WebSocket, session_id: str, since: int | None = 0
        ):
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
            # Keep startup lightweight and avoid blocking tests/environments where
            # provider discovery may stall. The orchestrator is initialized lazily
            # the first time goal execution is requested.
            return None

        if STATIC_DIR.exists():
            app.mount(
                "/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static"
            )

        return app

    async def _execute_goal_and_broadcast(self, goal: str) -> None:
        if self._orchestrator is None:
            self._orchestrator = Orchestrator(
                self.session, self.config_dir, APP_INSTALL_DIR
            )
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
        window = events[start : start + safe_limit]
        if redact:
            policy = CredentialPolicy(self.session.workroot)
            window = [_redact_nested(event, policy) for event in window]
        next_offset = start + len(window)
        return window, total, next_offset

    async def _send_with_timeout(
        self, ws: WebSocket, payload: dict[str, Any], timeout: float = 1.5
    ) -> bool:
        try:
            await asyncio.wait_for(ws.send_json(payload), timeout=timeout)
            return True
        except (asyncio.TimeoutError, Exception):
            return False

    async def _send_replay(
        self, ws: WebSocket, since: int = 0, limit: int = 200
    ) -> None:
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


def start_server(session: Session, port: int = 0) -> dict:
    server = SessionServer(session, port=port)
    return {"server": server, "port": server.port, "url": server.get_url()}
