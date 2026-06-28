import os
import socket
import time
from pathlib import Path
from typing import Any

from galaxy_merge.browser.cdp import CDPCommandError, CDPMonitor, send_page_command
from galaxy_merge.browser.console_logs import ConsoleLogCollector
from galaxy_merge.browser.page_errors import PageErrorCollector
from galaxy_merge.browser.network_logs import NetworkLogCollector
from galaxy_merge.browser.screenshots import ScreenshotManager
from galaxy_merge.browser.dom import DOMInspector


class BrowserManager:
    def __init__(self, cache_dir: Path):
        self.gm_dir = cache_dir
        self.cache_dir = cache_dir / "browser"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._sessions: dict[str, dict[str, Any]] = {}
        self._console_collectors: dict[str, ConsoleLogCollector] = {}
        self._network_collectors: dict[str, NetworkLogCollector] = {}
        self._page_error_collectors: dict[str, PageErrorCollector] = {}
        self._cdp_monitors: dict[str, CDPMonitor] = {}
        self._screenshot_mgr = ScreenshotManager(cache_dir)
        self._dom_inspector = DOMInspector()

    def profile_path(self, session_id: str) -> Path:
        return self.cache_dir / "profiles" / session_id

    def open_session(self, session_id: str, url: str = "about:blank") -> dict[str, Any]:
        import subprocess
        data_dir = self.profile_path(session_id)
        data_dir.mkdir(parents=True, exist_ok=True)
        debug_port = _find_free_port()

        chrome_paths = [
            "/usr/bin/google-chrome",
            "/usr/bin/chromium-browser",
            "/usr/bin/chromium",
        ]
        chrome_path = None
        for p in chrome_paths:
            if os.path.exists(p):
                chrome_path = p
                break

        if not chrome_path:
            return {"success": False, "error": "Chrome/Chromium not found"}

        args = [
            chrome_path,
            f"--user-data-dir={data_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-extensions",
            "--disable-sync",
            "--disable-translate",
            f"--remote-debugging-port={debug_port}" if debug_port else "--remote-debugging-port=0",
            "--window-size=1280,800",
            url,
        ]

        try:
            process = subprocess.Popen(
                args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
            )
            self._sessions[session_id] = {
                "process": process,
                "profile_dir": str(data_dir),
                "data_dir": str(data_dir),
                "url": url,
                "started_at": time.time(),
            }
            console = ConsoleLogCollector(session_id, self.gm_dir)
            network = NetworkLogCollector(self.gm_dir, session_id)
            page_errors = PageErrorCollector(self.gm_dir, session_id)
            self._console_collectors[session_id] = console
            self._network_collectors[session_id] = network
            self._page_error_collectors[session_id] = page_errors
            if debug_port:
                monitor = CDPMonitor(debug_port, console, network, page_errors)
                self._cdp_monitors[session_id] = monitor
                monitor.start()
            else:
                console.add_warning("DevTools capture disabled: no local debug port available", "cdp")

            return {
                "success": True,
                "session_id": session_id,
                "url": url,
                "pid": process.pid,
                "profile_dir": str(data_dir),
                "debug_port": debug_port,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def close_session(self, session_id: str) -> bool:
        session = self._sessions.pop(session_id, None)
        if session:
            monitor = self._cdp_monitors.pop(session_id, None)
            if monitor:
                monitor.stop()
            self._console_collectors.pop(session_id, None)
            self._network_collectors.pop(session_id, None)
            self._page_error_collectors.pop(session_id, None)
            proc = session.get("process")
            if proc and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except Exception:
                    proc.kill()
            import shutil
            profile = session.get("profile_dir", "")
            if profile and Path(profile).exists():
                shutil.rmtree(profile, ignore_errors=True)
            return True
        return False

    def list_sessions(self) -> list[dict[str, Any]]:
        return [
            {
                "session_id": sid,
                "url": s.get("url", ""),
                "started_at": s.get("started_at", 0),
                "running": s.get("process") and s["process"].poll() is None,
            }
            for sid, s in self._sessions.items()
        ]

    def network_read(self, session_id: str) -> list[dict[str, Any]]:
        collector = self._network_collectors.get(session_id)
        if not collector:
            return []
        return collector.get_logs()

    def page_errors_read(self, session_id: str) -> list[dict[str, Any]]:
        collector = self._page_error_collectors.get(session_id)
        if not collector:
            return []
        return collector.get_errors()

    def inspect_page(self, session_id: str, selector: str = "body") -> dict[str, Any]:
        session = self._sessions.get(session_id)
        if not session:
            return {"error": "session not found"}
        live = self.dom_snapshot(session_id, selector)
        if live.get("success"):
            return live
        return self._dom_inspector.inspect_page_structure(session, selector)

    def _debug_port(self, session_id: str) -> int:
        session = self._sessions.get(session_id)
        if not session:
            return 0
        return int(session.get("debug_port", 0) or 0)

    def _run_page_command(self, session_id: str, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        port = self._debug_port(session_id)
        if not port:
            return {"success": False, "error": "DevTools capture not available"}
        try:
            response = send_page_command(port, method, params)
            return {"success": True, "response": response}
        except CDPCommandError as e:
            return {"success": False, "error": str(e)}

    def navigate(self, session_id: str, url: str) -> dict[str, Any]:
        if session_id not in self._sessions:
            return {"success": False, "error": "session not found"}
        result = self._run_page_command(session_id, "Page.navigate", {"url": url})
        if result.get("success"):
            self._sessions[session_id]["url"] = url
            result["url"] = url
        return result

    def reload(self, session_id: str) -> dict[str, Any]:
        if session_id not in self._sessions:
            return {"success": False, "error": "session not found"}
        return self._run_page_command(session_id, "Page.reload")

    def dom_snapshot(self, session_id: str, selector: str = "body") -> dict[str, Any]:
        if session_id not in self._sessions:
            return {"success": False, "error": "session not found"}
        result = self._run_page_command(session_id, "Runtime.evaluate", {
            "expression": "document.documentElement.outerHTML",
            "returnByValue": True,
        })
        if not result.get("success"):
            return result
        response = result.get("response", {})
        html = response.get("result", {}).get("result", {}).get("value", "")
        if not html:
            return {"success": False, "error": "DOM snapshot unavailable"}
        return {
            "success": True,
            "session_id": session_id,
            "selector": selector,
            "snapshot": self._dom_inspector.inspect(html, selector),
            "html_preview": html[:1000],
        }

    def screenshot(self, session_id: str) -> dict[str, Any]:
        session = self._sessions.get(session_id)
        if not session:
            return {"success": False, "error": "session not found"}
        try:
            import subprocess
            proc = session.get("process")
            if not proc or proc.poll() is not None:
                return {"success": False, "error": "browser process not running"}
            ss_path = self._screenshot_mgr.get_screenshot_path(session_id)
            ss_path.parent.mkdir(parents=True, exist_ok=True)
            import shutil
            if shutil.which("import"):
                import subprocess as sp
                result = sp.run(
                    ["import", "-window", "root", str(ss_path)],
                    capture_output=True, text=True, timeout=15,
                )
                if result.returncode == 0:
                    return {"success": True, "screenshot_path": str(ss_path)}
            if shutil.which("gnome-screenshot"):
                import subprocess as sp
                result = sp.run(
                    ["gnome-screenshot", "-f", str(ss_path)],
                    capture_output=True, text=True, timeout=15,
                )
                if result.returncode == 0:
                    return {"success": True, "screenshot_path": str(ss_path)}
            return {"success": False, "error": "no screenshot tool available (try: import, gnome-screenshot, or Playwright)"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def cleanup_all(self) -> None:
        for sid in list(self._sessions.keys()):
            self.close_session(sid)


def _find_free_port() -> int:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])
    except OSError:
        return 0
