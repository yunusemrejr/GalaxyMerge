from typing import Any

import requests


def search_wikipedia(
    query: str, lang: str = "en", max_results: int = 5
) -> list[dict[str, Any]]:
    url = f"https://{lang}.wikipedia.org/w/api.php"
    params = {
        "action": "query",
        "list": "search",
        "srsearch": query,
        "format": "json",
        "srlimit": max_results,
    }
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        results = []
        for hit in data.get("query", {}).get("search", []):
            results.append(
                {
                    "title": hit.get("title", ""),
                    "snippet": hit.get("snippet", "")
                    .replace('<span class="searchmatch">', "")
                    .replace("</span>", ""),
                    "page_id": hit.get("pageid"),
                }
            )
        return results
    except requests.RequestException as e:
        return [{"error": str(e)}]


def get_wikipedia_summary(
    title: str, lang: str = "en", sentences: int = 3
) -> dict[str, Any]:
    url = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{title.replace(' ', '_')}"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        return {
            "title": data.get("title", title),
            "extract": data.get("extract", ""),
            "url": data.get("content_urls", {}).get("desktop", {}).get("page", ""),
            "thumbnail": data.get("thumbnail", {}).get("source", ""),
        }
    except requests.RequestException as e:
        return {"error": str(e)}
