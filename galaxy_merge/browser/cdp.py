import json
import threading
import time
import urllib.request
from typing import Any

from galaxy_merge.browser.console_logs import ConsoleLogCollector
from galaxy_merge.browser.network_logs import NetworkLogCollector


class CDPMonitor:
    def __init__(
        self,
        port: int,
        console: ConsoleLogCollector,
        network: NetworkLogCollector,
    ):
        self.port = port
        self.console = console
        self.network = network
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        try:
            ws_url = self._wait_for_page_ws_url()
            if not ws_url:
                self.console.add_warning("DevTools endpoint not available", "cdp")
                return
            self._listen(ws_url)
        except (OSError, TimeoutError, json.JSONDecodeError) as e:
            self.console.add_error(str(e), "cdp")

    def _wait_for_page_ws_url(self) -> str:
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline and not self._stop.is_set():
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/json/list", timeout=1) as response:
                    pages = json.loads(response.read().decode("utf-8"))
                for page in pages:
                    if page.get("type") == "page" and page.get("webSocketDebuggerUrl"):
                        return page["webSocketDebuggerUrl"]
            except (OSError, TimeoutError, json.JSONDecodeError):
                time.sleep(0.2)
        return ""

    def _listen(self, ws_url: str) -> None:
        from websockets.sync.client import connect

        with connect(ws_url, open_timeout=3) as websocket:
            for idx, method in enumerate(("Runtime.enable", "Log.enable", "Network.enable"), start=1):
                websocket.send(json.dumps({"id": idx, "method": method}))
            while not self._stop.is_set():
                try:
                    raw = websocket.recv(timeout=1)
                except TimeoutError:
                    continue
                if not raw:
                    continue
                self._handle_event(json.loads(raw))

    def _handle_event(self, event: dict[str, Any]) -> None:
        method = event.get("method", "")
        params = event.get("params", {})
        if method == "Runtime.consoleAPICalled":
            args = params.get("args", [])
            message = " ".join(str(arg.get("value", arg.get("description", ""))) for arg in args)
            self.console.add_log(params.get("type", "log"), message, "console")
        elif method == "Log.entryAdded":
            entry = params.get("entry", {})
            self.console.add_log(entry.get("level", "log"), entry.get("text", ""), entry.get("source", "log"))
        elif method == "Network.responseReceived":
            response = params.get("response", {})
            self.network.add_request(
                response.get("url", ""),
                params.get("type", "GET"),
                int(response.get("status", 0) or 0),
                "",
            )
