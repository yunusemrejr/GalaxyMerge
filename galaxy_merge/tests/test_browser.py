import base64

import pytest

from galaxy_merge.browser.console_logs import ConsoleLogCollector
from galaxy_merge.browser.dom import DOMInspector
from galaxy_merge.browser.manager import BrowserManager
from galaxy_merge.browser.network_logs import NetworkLogCollector

pytestmark = [pytest.mark.unit]


class TestConsoleLogCollector:
    def test_add_and_get_logs(self, tmp_path):
        collector = ConsoleLogCollector("test", tmp_path)
        collector.add_log("info", "hello world")
        collector.add_error("something broke")
        logs = collector.get_logs()
        assert len(logs) == 2
        assert logs[0]["level"] == "info"
        assert logs[1]["level"] == "error"

    def test_get_empty(self, tmp_path):
        collector = ConsoleLogCollector("test", tmp_path / "other")
        assert collector.get_logs() == []


class TestNetworkLogCollector:
    def test_add_request(self, tmp_path):
        collector = NetworkLogCollector(tmp_path)
        collector.add_request("https://example.com", "GET", 200)
        logs = collector.get_logs()
        assert len(logs) == 1
        assert logs[0]["method"] == "GET"
        assert logs[0]["status"] == 200


class TestPageErrorCollector:
    def test_add_and_get_page_errors(self, tmp_path):
        from galaxy_merge.browser.page_errors import PageErrorCollector

        collector = PageErrorCollector(tmp_path, "sess_a")
        collector.add_error("Runtime.exceptionThrown", "boom", "app.js")
        other = PageErrorCollector(tmp_path, "sess_b")

        errors = collector.get_errors()
        assert len(errors) == 1
        assert errors[0]["message"] == "boom"
        assert other.get_errors() == []


class TestDOMInspector:
    def test_inspect(self):
        inspector = DOMInspector()
        html = "<html><body><h1>Title</h1><p>Text</p></body></html>"
        result = inspector.inspect(html, "h1")
        assert result["count"] == 1
        assert result["elements"][0]["tag"] == "h1"

    def test_page_structure(self):
        inspector = DOMInspector()
        html = "<html><body><div><h1>A</h1><p>B</p></div></body></html>"
        structure = inspector.get_page_structure(html)
        assert len(structure) > 0


class TestBrowserManagerCommands:
    def test_open_session_records_debug_port_and_headless_flags(
        self, monkeypatch, tmp_path
    ):
        # Given: Chrome exists and the harness is running without a display.
        manager = BrowserManager(tmp_path)
        started = {}

        class FakeProcess:
            pid = 1234

            def poll(self):
                return None

        def fake_popen(args, **kwargs):
            started["args"] = args
            started["kwargs"] = kwargs
            return FakeProcess()

        monkeypatch.setattr(
            "galaxy_merge.browser.manager.os.path.exists",
            lambda path: path == "/usr/bin/google-chrome",
        )
        monkeypatch.setattr("galaxy_merge.browser.manager.subprocess.Popen", fake_popen)
        monkeypatch.delenv("DISPLAY", raising=False)

        # When: a browser session is opened.
        opened = manager.open_session("sess_a", "http://127.0.0.1:8000")

        # Then: DevTools state is persisted for later browser commands.
        assert opened["success"] is True
        assert manager._debug_port("sess_a") == opened["debug_port"]
        assert "--headless=new" in started["args"]

    def test_navigate_reload_dom_snapshot_and_close_use_scoped_cdp(
        self, monkeypatch, tmp_path
    ):
        # Given: an existing browser session with a DevTools port.
        manager = BrowserManager(tmp_path)
        manager._sessions["sess_a"] = {
            "process": None,
            "profile_dir": str(manager.profile_path("sess_a")),
            "data_dir": str(manager.profile_path("sess_a")),
            "url": "about:blank",
            "started_at": 1.0,
            "debug_port": 9333,
        }
        commands = []

        def fake_send(port, method, params=None):
            commands.append((port, method, params or {}))
            if method == "Runtime.evaluate":
                return {
                    "result": {
                        "result": {"value": "<html><body><main>OK</main></body></html>"}
                    }
                }
            return {"result": {}}

        monkeypatch.setattr("galaxy_merge.browser.manager.send_page_command", fake_send)

        # When: browser command helpers are used.
        navigated = manager.navigate("sess_a", "https://example.test")
        reloaded = manager.reload("sess_a")
        snapshot = manager.dom_snapshot("sess_a", "main")
        closed = manager.close_session("sess_a")

        # Then: the correct CDP commands are dispatched and session state is updated.
        assert navigated["success"] is True
        assert reloaded["success"] is True
        assert snapshot["success"] is True
        assert snapshot["snapshot"]["count"] == 1
        assert closed is True
        assert commands[0] == (9333, "Page.navigate", {"url": "https://example.test"})
        assert commands[1] == (9333, "Page.reload", {})
        assert commands[2][1] == "Runtime.evaluate"

    def test_screenshot_uses_cdp_capture_when_available(self, monkeypatch, tmp_path):
        # Given: an existing browser session with a DevTools port and a running process.
        manager = BrowserManager(tmp_path)

        class FakeProcess:
            def poll(self):
                return None

        manager._sessions["sess_a"] = {
            "process": FakeProcess(),
            "profile_dir": str(manager.profile_path("sess_a")),
            "data_dir": str(manager.profile_path("sess_a")),
            "url": "about:blank",
            "started_at": 1.0,
            "debug_port": 9333,
        }
        png_bytes = b"\x89PNG\r\n\x1a\n"

        def fake_send(port, method, params=None):
            assert port == 9333
            assert method == "Page.captureScreenshot"
            return {"result": {"data": base64.b64encode(png_bytes).decode("ascii")}}

        monkeypatch.setattr("galaxy_merge.browser.manager.send_page_command", fake_send)

        # When: a screenshot is captured.
        result = manager.screenshot("sess_a")

        # Then: the PNG is written from CDP output.
        assert result["success"] is True
        assert result["source"] == "cdp"
        screenshot_path = result["screenshot_path"]
        assert (
            tmp_path.joinpath("browser", "screenshots", "sess_a_page.png").read_bytes()
            == png_bytes
        )
        assert screenshot_path.endswith("sess_a_page.png")


class TestBrowserTools:
    def test_required_browser_tool_surface_is_registered(self, tmp_path):
        from galaxy_merge.tools.browser_tools import make_browser_tools

        schemas = {
            schema.name: schema
            for schema, _handler in make_browser_tools(tmp_path, "owner")
        }

        assert "browser.reload" in schemas
        assert "browser.navigate" in schemas
        assert "browser.page_errors.read" in schemas
        assert "browser.dom.snapshot" in schemas
        assert "browser.close" in schemas


class TestCDPPageErrors:
    def test_runtime_and_network_failures_are_recorded_as_page_errors(self, tmp_path):
        from galaxy_merge.browser.cdp import CDPMonitor
        from galaxy_merge.browser.page_errors import PageErrorCollector

        console = ConsoleLogCollector("sess_a", tmp_path)
        network = NetworkLogCollector(tmp_path, "sess_a")
        page_errors = PageErrorCollector(tmp_path, "sess_a")
        monitor = CDPMonitor(0, console, network, page_errors)

        monitor._handle_event(
            {
                "method": "Runtime.exceptionThrown",
                "params": {
                    "exceptionDetails": {
                        "url": "app.js",
                        "exception": {
                            "description": "ReferenceError: missingThing is not defined"
                        },
                    },
                },
            }
        )
        monitor._handle_event(
            {
                "method": "Network.loadingFailed",
                "params": {
                    "requestId": "asset.js",
                    "type": "Script",
                    "errorText": "net::ERR_FAILED",
                },
            }
        )

        errors = page_errors.get_errors()
        assert len(errors) == 2
        assert errors[0]["type"] == "Runtime.exceptionThrown"
        assert "ReferenceError" in errors[0]["message"]
        assert errors[1]["type"] == "Network.loadingFailed"
        assert network.get_logs()[0]["error"] == "net::ERR_FAILED"
