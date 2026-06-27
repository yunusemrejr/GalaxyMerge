import pytest
from pathlib import Path
import tempfile

from galaxy_merge.browser.console_logs import ConsoleLogCollector
from galaxy_merge.browser.network_logs import NetworkLogCollector
from galaxy_merge.browser.screenshots import ScreenshotManager
from galaxy_merge.browser.dom import DOMInspector


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
