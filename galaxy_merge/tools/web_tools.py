from pathlib import Path
from typing import Any

from galaxy_merge.tools.schemas import ToolSchema, ToolResult
from galaxy_merge.web.search import WebSearch
from galaxy_merge.web.fetch import MAX_FETCH_BYTES


def make_web_tools(cache_dir: Path | None = None) -> list[tuple[ToolSchema, Any]]:
    searcher = WebSearch(cache_dir)

    async def web_search(query: str, source: str = "duckduckgo") -> ToolResult:
        results = searcher.search(query, source)
        return ToolResult(success=True, data={"query": query, "source": source, "results": results, "count": len(results)})

    async def web_fetch(url: str, max_bytes: int = MAX_FETCH_BYTES) -> ToolResult:
        result = searcher.fetch(url, max_bytes=max_bytes)
        if "error" in result:
            return ToolResult(success=False, error=result["error"])
        return ToolResult(success=True, data=result)

    async def web_duckduckgo(query: str) -> ToolResult:
        results = searcher.search(query, "duckduckgo")
        return ToolResult(success=True, data={"query": query, "results": results, "count": len(results)})

    async def web_wikipedia(query: str) -> ToolResult:
        results = searcher.search(query, "wikipedia")
        return ToolResult(success=True, data={"query": query, "results": results, "count": len(results)})

    async def web_wikipedia_summary(title: str) -> ToolResult:
        result = searcher.wikipedia_summary(title)
        if "error" in result:
            return ToolResult(success=False, error=result["error"])
        return ToolResult(success=True, data=result)

    async def web_curl_fetch(url: str, max_bytes: int = MAX_FETCH_BYTES) -> ToolResult:
        return await web_fetch(url, max_bytes=max_bytes)

    return [
        (ToolSchema("web.search", "Search the web via DuckDuckGo or Wikipedia", parameters={
            "query": {"type": "string", "required": True},
            "source": {"type": "string", "default": "duckduckgo"},
        }), web_search),
        (ToolSchema("web.fetch", "Fetch a URL and return its content", parameters={
            "url": {"type": "string", "required": True},
            "max_bytes": {"type": "integer", "default": MAX_FETCH_BYTES},
        }), web_fetch),
        (ToolSchema("web.duckduckgo.search", "Search DuckDuckGo", parameters={
            "query": {"type": "string", "required": True},
        }), web_duckduckgo),
        (ToolSchema("web.wikipedia.search", "Search Wikipedia", parameters={
            "query": {"type": "string", "required": True},
        }), web_wikipedia),
        (ToolSchema("web.wikipedia.summary", "Get Wikipedia article summary", parameters={
            "title": {"type": "string", "required": True},
        }), web_wikipedia_summary),
        (ToolSchema("web.curl.fetch", "Fetch a URL via curl/httpx", parameters={
            "url": {"type": "string", "required": True},
            "max_bytes": {"type": "integer", "default": MAX_FETCH_BYTES},
        }), web_curl_fetch),
    ]
