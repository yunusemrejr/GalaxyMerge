import pytest
from galaxy_merge.web.search import WebSearch
from galaxy_merge.web.fetch import fetch_page


class TestWebSearch:
    def test_search_duckduckgo(self):
        searcher = WebSearch()
        results = searcher.search("python programming", source="duckduckgo")
        assert len(results) > 0

    def test_search_wikipedia(self):
        searcher = WebSearch()
        results = searcher.search("Python", source="wikipedia")
        assert len(results) > 0

    def test_fetch_page_error(self):
        result = fetch_page("http://nonexistent.example.com")
        assert "error" in result


class TestDuckDuckGo:
    def test_search_returns_list(self):
        from galaxy_merge.web.duckduckgo import search_duckduckgo
        results = search_duckduckgo("test query")
        assert isinstance(results, list)


class TestWikipedia:
    def test_search_returns_list(self):
        from galaxy_merge.web.wikipedia import search_wikipedia, get_wikipedia_summary
        results = search_wikipedia("Python programming language")
        assert isinstance(results, list)

    def test_summary(self):
        from galaxy_merge.web.wikipedia import get_wikipedia_summary
        result = get_wikipedia_summary("Python (programming language)")
        assert "extract" in result or "error" in result
