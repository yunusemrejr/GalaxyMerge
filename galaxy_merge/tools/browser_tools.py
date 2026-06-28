from pathlib import Path
from typing import Any

from galaxy_merge.tools.schemas import ToolSchema, ToolResult
from galaxy_merge.browser.manager import BrowserManager


_browser_managers: dict[str, BrowserManager] = {}


def _get_manager(cache_dir: Path) -> BrowserManager:
    key = str(cache_dir.resolve())
    if key not in _browser_managers:
        _browser_managers[key] = BrowserManager(cache_dir)
    return _browser_managers[key]


def make_browser_tools(
    cache_dir: Path,
    owner_session_id: str | None = None,
) -> list[tuple[ToolSchema, Any]]:
    mgr = _get_manager(cache_dir)

    def scoped(session_id: str | None = None) -> str:
        base_sid = session_id or "default"
        return f"{owner_session_id}:{base_sid}" if owner_session_id else base_sid

    async def browser_open(url: str, session_id: str | None = None) -> ToolResult:
        base_sid = session_id or "default"
        result = mgr.open_session(scoped(base_sid), url)
        if result.get("success"):
            result["session_id"] = base_sid
        return ToolResult(success=result.get("success", False), data=result)

    async def browser_navigate(url: str, session_id: str = "default") -> ToolResult:
        result = mgr.navigate(scoped(session_id), url)
        if result.get("success"):
            result["session_id"] = session_id
        return ToolResult(
            success=result.get("success", False), data=result, error=result.get("error")
        )

    async def browser_reload(session_id: str = "default") -> ToolResult:
        result = mgr.reload(scoped(session_id))
        if result.get("success"):
            result["session_id"] = session_id
        return ToolResult(
            success=result.get("success", False), data=result, error=result.get("error")
        )

    async def browser_close(session_id: str = "default") -> ToolResult:
        closed = mgr.close_session(scoped(session_id))
        return ToolResult(
            success=closed, data={"session_id": session_id, "closed": closed}
        )

    async def browser_sessions() -> ToolResult:
        sessions = mgr.list_sessions()
        if owner_session_id:
            prefix = f"{owner_session_id}:"
            sessions = [
                {**session, "session_id": session["session_id"][len(prefix) :]}
                for session in sessions
                if session.get("session_id", "").startswith(prefix)
            ]
        return ToolResult(
            success=True, data={"sessions": sessions, "count": len(sessions)}
        )

    async def browser_console_read(session_id: str = "default") -> ToolResult:
        collector = mgr._console_collectors.get(scoped(session_id))
        if not collector:
            return ToolResult(success=False, error="no browser session found")
        logs = collector.get_logs()
        return ToolResult(
            success=True,
            data={"session_id": session_id, "logs": logs, "count": len(logs)},
        )

    async def browser_page_errors_read(session_id: str = "default") -> ToolResult:
        errors = mgr.page_errors_read(scoped(session_id))
        return ToolResult(
            success=True,
            data={
                "session_id": session_id,
                "page_errors": errors,
                "count": len(errors),
            },
        )

    async def browser_network_read(session_id: str = "default") -> ToolResult:
        collector = mgr._network_collectors.get(scoped(session_id))
        if not collector:
            return ToolResult(success=False, error="no browser session found")
        logs = collector.get_logs()
        return ToolResult(
            success=True,
            data={"session_id": session_id, "network_logs": logs, "count": len(logs)},
        )

    async def browser_screenshot(session_id: str = "default") -> ToolResult:
        result = mgr.screenshot(scoped(session_id))
        return ToolResult(success=result.get("success", False), data=result)

    async def browser_inspect(
        session_id: str = "default", selector: str = "body"
    ) -> ToolResult:
        result = mgr.inspect_page(scoped(session_id), selector)
        if "error" in result:
            return ToolResult(success=False, error=result["error"])
        return ToolResult(success=True, data=result)

    async def browser_dom_snapshot(
        session_id: str = "default", selector: str = "body"
    ) -> ToolResult:
        result = mgr.dom_snapshot(scoped(session_id), selector)
        if "error" in result:
            return ToolResult(success=False, error=result["error"], data=result)
        result["session_id"] = session_id
        return ToolResult(success=True, data=result)

    return [
        (
            ToolSchema(
                "browser.open",
                "Open a URL in an isolated browser session",
                parameters={
                    "url": {"type": "string", "required": True},
                    "session_id": {"type": "string", "default": "default"},
                },
            ),
            browser_open,
        ),
        (
            ToolSchema(
                "browser.navigate",
                "Navigate an existing browser session",
                parameters={
                    "url": {"type": "string", "required": True},
                    "session_id": {"type": "string", "default": "default"},
                },
            ),
            browser_navigate,
        ),
        (
            ToolSchema(
                "browser.reload",
                "Reload an existing browser session",
                parameters={
                    "session_id": {"type": "string", "default": "default"},
                },
            ),
            browser_reload,
        ),
        (
            ToolSchema(
                "browser.close",
                "Close an isolated browser session",
                parameters={
                    "session_id": {"type": "string", "default": "default"},
                },
            ),
            browser_close,
        ),
        (
            ToolSchema("browser.sessions", "List active browser sessions"),
            browser_sessions,
        ),
        (
            ToolSchema(
                "browser.console.read",
                "Read browser console logs",
                parameters={
                    "session_id": {"type": "string", "default": "default"},
                },
            ),
            browser_console_read,
        ),
        (
            ToolSchema(
                "browser.page_errors.read",
                "Read uncaught browser page errors",
                parameters={
                    "session_id": {"type": "string", "default": "default"},
                },
            ),
            browser_page_errors_read,
        ),
        (
            ToolSchema(
                "browser.network.read",
                "Read browser network request logs",
                parameters={
                    "session_id": {"type": "string", "default": "default"},
                },
            ),
            browser_network_read,
        ),
        (
            ToolSchema(
                "browser.screenshot",
                "Take browser screenshot",
                parameters={
                    "session_id": {"type": "string", "default": "default"},
                },
            ),
            browser_screenshot,
        ),
        (
            ToolSchema(
                "browser.inspect",
                "Inspect page DOM structure",
                parameters={
                    "session_id": {"type": "string", "default": "default"},
                    "selector": {"type": "string", "default": "body"},
                },
            ),
            browser_inspect,
        ),
        (
            ToolSchema(
                "browser.dom.snapshot",
                "Capture a DOM snapshot from the active browser page",
                parameters={
                    "session_id": {"type": "string", "default": "default"},
                    "selector": {"type": "string", "default": "body"},
                },
            ),
            browser_dom_snapshot,
        ),
    ]
