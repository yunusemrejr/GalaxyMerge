from typing import Any


class DOMInspector:
    def inspect(self, html: str, selector: str = "body") -> dict[str, Any]:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "lxml")
        elements = soup.select(selector)
        return {
            "selector": selector,
            "count": len(elements),
            "elements": [
                {
                    "tag": el.name,
                    "text": el.get_text(strip=True)[:200],
                    "attributes": dict(el.attrs),
                }
                for el in elements[:20]
            ],
        }

    def get_page_structure(self, html: str) -> list[dict[str, Any]]:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "lxml")

        def extract_structure(tag, depth=0):
            if depth > 5:
                return []
            result = []
            for child in tag.find_all(recursive=False):
                entry = {
                    "tag": child.name,
                    "id": child.get("id", ""),
                    "classes": child.get("class", []),
                    "children_count": len(child.find_all(recursive=False)),
                    "text_preview": child.get_text(strip=True)[:80],
                }
                result.append(entry)
                result.extend(extract_structure(child, depth + 1))
            return result

        body = soup.find("body")
        if not body:
            return []
        return extract_structure(body)[:50]

    def inspect_page_structure(
        self, session: dict[str, Any], selector: str = "body"
    ) -> dict[str, Any]:
        data_dir = session.get("data_dir", "")
        url = session.get("url", "")
        return {
            "session_url": url,
            "data_dir": data_dir,
            "note": "DOM inspection requires Playwright for live page access",
            "selector": selector,
        }
