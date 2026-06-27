import re
from typing import Any

import requests
from bs4 import BeautifulSoup


PROMPT_INJECTION_PATTERNS: list[str] = [
    r"(?i)ignore\s+(all\s+)?previous\s+instructions",
    r"(?i)forget\s+(all\s+)?previous\s+instructions",
    r"(?i)ignore\s+your\s+(system\s+)?prompt",
    r"(?i)you\s+are\s+(now\s+)?a\s+different\s+(AI|assistant|model)",
    r"(?i)override\s+(your\s+)?(system\s+)?instructions",
    r"(?i)disregard\s+(all\s+)?(prior\s+)?(instructions|directives)",
    r"(?i)new\s+instructions?\s*:",
    r"(?i)act\s+as\s+if",
    r"(?i)you\s+must\s+obey",
    r"(?i)you\s+will\s+now",
    r"(?i)from\s+now\s+on\s+you\s+are",
    r"(?i)system\s+(override|breach|bypass)",
    r"(?i)![iI][mM][pP][oO][rR][tT](ant)?",
]


def _detect_prompt_injection(text: str) -> list[str]:
    matches = []
    for pattern in PROMPT_INJECTION_PATTERNS:
        found = re.findall(pattern, text)
        if found:
            matches.append(pattern)
    return matches


def _strip_prompt_injection(text: str) -> str:
    for pattern in PROMPT_INJECTION_PATTERNS:
        text = re.sub(pattern, "[REDACTED: potential prompt injection]", text)
    return text


def fetch_page(url: str, timeout: int = 30) -> dict[str, Any]:
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) GalaxyMerge/0.1",
    }
    try:
        response = requests.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()

        content_type = response.headers.get("content-type", "")
        if "text/html" in content_type or "application/xhtml" in content_type:
            soup = BeautifulSoup(response.text, "lxml")
            for tag in soup(["script", "style", "nav", "footer", "header", "iframe", "object", "embed"]):
                tag.decompose()
            text = soup.get_text(separator="\n", strip=True)
            text = "\n".join(line for line in text.splitlines() if line.strip())
            text = text[:10000]
            title = soup.title.string.strip() if soup.title and soup.title.string else ""

            injections = _detect_prompt_injection(text)
            sanitized = _strip_prompt_injection(text)

            return {
                "url": url,
                "title": title,
                "content": sanitized,
                "content_type": "html",
                "status": response.status_code,
                "injections_detected": len(injections),
                "injection_patterns": injections,
                "sanitized": len(injections) > 0,
            }
        else:
            content = response.text[:10000]
            injections = _detect_prompt_injection(content)
            sanitized = _strip_prompt_injection(content)
            return {
                "url": url,
                "title": "",
                "content": sanitized,
                "content_type": content_type.split(";")[0],
                "status": response.status_code,
                "injections_detected": len(injections),
                "injection_patterns": injections,
                "sanitized": len(injections) > 0,
            }
    except requests.RequestException as e:
        return {"url": url, "error": str(e), "status": 0}