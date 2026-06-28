

import pytest

pytestmark = [pytest.mark.integration]
from galaxy_merge.web.search import WebSearch
from galaxy_merge.web.fetch import fetch_page
from galaxy_merge.tools.web_tools import make_web_tools


class TestWebSearch:
    @pytest.mark.network
    def test_search_duckduckgo(self):
        searcher = WebSearch()
        results = searcher.search("python programming", source="duckduckgo")
        assert len(results) > 0

    @pytest.mark.network
    def test_search_wikipedia(self):
        searcher = WebSearch()
        results = searcher.search("Python", source="wikipedia")
        assert len(results) > 0

    def test_fetch_page_error(self):
        result = fetch_page("http://nonexistent.example.com")
        assert "error" in result

    def test_fetch_page_rejects_unsupported_scheme_without_network(self, monkeypatch):
        # Given: a local file URL and a network call that must not be reached.
        def fail_get(*args, **kwargs):
            raise AssertionError("network should not be called for unsupported schemes")

        monkeypatch.setattr("galaxy_merge.web.fetch.requests.get", fail_get)

        # When: the page is fetched.
        result = fetch_page("file:///etc/passwd")

        # Then: the request is rejected locally.
        assert "error" in result
        assert "unsupported URL scheme" in result["error"]

    def test_fetch_page_blocks_binary_response_without_body_read(self, monkeypatch):
        # Given: a binary response whose body reader must not be consumed.
        class BinaryResponse:
            headers = {"content-type": "application/octet-stream", "content-length": "4"}
            status_code = 200
            encoding = "utf-8"

            def raise_for_status(self):
                return None

            def iter_content(self, chunk_size=8192):
                raise AssertionError("binary body should not be read")

            def close(self):
                return None

        def fake_get(*args, **kwargs):
            return BinaryResponse()

        monkeypatch.setattr("galaxy_merge.web.fetch.requests.get", fake_get)

        # When: the page is fetched.
        result = fetch_page("https://example.com/archive.bin")

        # Then: Galaxy Merge blocks the binary response before reading the body.
        assert "error" in result
        assert "blocked binary content type" in result["error"]

    def test_fetch_page_streams_text_under_byte_cap(self, monkeypatch):
        # Given: a text response larger than the configured fetch cap.
        class TextResponse:
            headers = {"content-type": "text/plain"}
            status_code = 200
            encoding = "utf-8"

            def raise_for_status(self):
                return None

            def iter_content(self, chunk_size=8192):
                yield b"a" * 8192
                yield b"b" * 8192

            def close(self):
                return None

        seen_kwargs = {}

        def fake_get(*args, **kwargs):
            seen_kwargs.update(kwargs)
            return TextResponse()

        monkeypatch.setattr("galaxy_merge.web.fetch.requests.get", fake_get)

        # When: the page is fetched with a small cap.
        result = fetch_page("https://example.com/large.txt", max_bytes=10_000)

        # Then: the body is streamed and capped instead of fully downloaded.
        assert seen_kwargs["stream"] is True
        assert len(result["content"]) == 10_000
        assert result["truncated"] is True
        assert result["max_bytes"] == 10_000

    def test_web_fetch_tools_expose_max_bytes_parameter(self):
        # Given: the native web tools are registered.
        tools = make_web_tools()

        # When: fetch tool schemas are inspected.
        schemas = {schema.name: schema for schema, _handler in tools}

        # Then: both fetch surfaces expose the same byte cap control.
        assert "max_bytes" in schemas["web.fetch"].parameters
        assert "max_bytes" in schemas["web.curl.fetch"].parameters

    @pytest.mark.asyncio
    async def test_web_fetch_tool_passes_max_bytes_to_fetch_layer(self, monkeypatch, tmp_path):
        # Given: a fetch layer that records the byte cap.
        seen = {}

        def fake_fetch_page(url, max_bytes=0):
            seen["url"] = url
            seen["max_bytes"] = max_bytes
            return {"url": url, "content": "ok", "status": 200}

        monkeypatch.setattr("galaxy_merge.web.search.fetch_page", fake_fetch_page)
        tools = make_web_tools(tmp_path)
        handlers = {schema.name: handler for schema, handler in tools}

        # When: the native fetch tool is called with a custom cap.
        result = await handlers["web.fetch"]("https://example.com", max_bytes=1234)

        # Then: the cap reaches the fetch layer.
        assert result.success is True
        assert seen == {"url": "https://example.com", "max_bytes": 1234}


class TestDuckDuckGo:
    @pytest.mark.network
    def test_search_returns_list(self):
        from galaxy_merge.web.duckduckgo import search_duckduckgo
        results = search_duckduckgo("test query")
        assert isinstance(results, list)


class TestWikipedia:
    @pytest.mark.network
    def test_search_returns_list(self):
        from galaxy_merge.web.wikipedia import search_wikipedia, get_wikipedia_summary
        results = search_wikipedia("Python programming language")
        assert isinstance(results, list)

    @pytest.mark.network
    def test_summary(self):
        from galaxy_merge.web.wikipedia import get_wikipedia_summary
        result = get_wikipedia_summary("Python (programming language)")
        assert "extract" in result or "error" in result
