from typing import Any

import requests
from bs4 import BeautifulSoup


def search_duckduckgo(query: str, max_results: int = 10) -> list[dict[str, Any]]:
    url = "https://html.duckduckgo.com/html/"
    params = {"q": query}
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) GalaxyMerge/0.1",
    }

    try:
        response = requests.get(url, params=params, headers=headers, timeout=15)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "lxml")
        results = []
        for link in soup.select(".result__a")[:max_results]:
            title = link.get_text(strip=True)
            href = link.get("href", "")
            if "uddg=" in href:
                import urllib.parse

                parsed = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
                href = parsed.get("uddg", [href])[0]
            snippet_el = link.find_parent(".result") or link.find_next_sibling()
            snippet = ""
            if snippet_el:
                snip = snippet_el.select_one(".result__snippet")
                if snip:
                    snippet = snip.get_text(strip=True)
            results.append({"title": title, "url": href, "snippet": snippet})

        return results
    except requests.RequestException as e:
        return [{"error": str(e)}]
