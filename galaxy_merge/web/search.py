import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from galaxy_merge.core.locks import atomic_append
from galaxy_merge.web.duckduckgo import search_duckduckgo
from galaxy_merge.web.wikipedia import search_wikipedia, get_wikipedia_summary
from galaxy_merge.web.fetch import MAX_FETCH_BYTES, fetch_page


class WebSearch:
    def __init__(self, cache_dir: Path | None = None):
        self.cache_dir = cache_dir
        self._init_cache()

    def _init_cache(self) -> None:
        if not self.cache_dir:
            return
        for name in ("searches", "fetched_pages", "wikipedia", "duckduckgo", "curl_fetches"):
            p = self.cache_dir / "web" / f"{name}.jsonl"
            p.parent.mkdir(parents=True, exist_ok=True)

    def _log_cache(self, source: str, data: dict[str, Any]) -> None:
        if not self.cache_dir:
            return
        name_map = {
            "duckduckgo": "duckduckgo",
            "wikipedia": "wikipedia",
            "fetch": "fetched_pages",
            "curl_fetch": "curl_fetches",
        }
        filename = name_map.get(source, "searches")
        path = self.cache_dir / "web" / f"{filename}.jsonl"
        record = {
            "time": datetime.now(timezone.utc).isoformat(),
            "source": source,
            "data": data,
        }
        atomic_append(path, json.dumps(record))

    def search(self, query: str, source: str = "duckduckgo") -> list[dict[str, Any]]:
        if source == "duckduckgo":
            results = search_duckduckgo(query)
        elif source == "wikipedia":
            results = search_wikipedia(query)
        else:
            return [{"error": f"unknown source: {source}"}]
        self._log_cache(source, {"query": query, "results": results})
        return results

    def fetch(self, url: str, max_bytes: int = MAX_FETCH_BYTES) -> dict[str, Any]:
        result = fetch_page(url, max_bytes=max_bytes)
        self._log_cache("fetch", {"url": url, "result": result})
        return result

    def wikipedia_summary(self, title: str) -> dict[str, Any]:
        result = get_wikipedia_summary(title)
        self._log_cache("wikipedia_summary", {"title": title, "result": result})
        return result
