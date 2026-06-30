import ipaddress
import re
import socket
from typing import Any, Final
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup


MAX_FETCH_BYTES: Final[int] = 10_000
HTML_CONTENT_TYPES: Final[tuple[str, ...]] = ("text/html", "application/xhtml")
BINARY_CONTENT_TYPES: Final[tuple[str, ...]] = (
    "application/octet-stream",
    "application/pdf",
    "application/zip",
    "application/x-7z-compressed",
    "application/x-rar-compressed",
    "application/x-tar",
)
BINARY_CONTENT_PREFIXES: Final[tuple[str, ...]] = ("image/", "audio/", "video/")

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


def _content_type(headers: dict[str, str]) -> str:
    return headers.get("content-type", "").split(";")[0].strip().lower()


def _is_binary_content_type(content_type: str) -> bool:
    if content_type in BINARY_CONTENT_TYPES:
        return True
    return any(content_type.startswith(prefix) for prefix in BINARY_CONTENT_PREFIXES)


def _is_private_ip(hostname: str) -> bool:
    try:
        resolved = socket.getaddrinfo(hostname, None)
        for family, _, _, _, sockaddr in resolved:
            ip = ipaddress.ip_address(sockaddr[0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                return True
        return False
    except (socket.gaierror, ValueError):
        return True


def _read_limited_text(response: requests.Response, max_bytes: int) -> tuple[str, bool]:
    chunks: list[bytes] = []
    total = 0
    truncated = False
    content_length = response.headers.get("content-length")
    if content_length and content_length.isdigit() and int(content_length) > max_bytes:
        truncated = True

    for chunk in response.iter_content(chunk_size=8192):
        if not chunk:
            continue
        remaining = max_bytes - total
        if len(chunk) > remaining:
            chunks.append(chunk[:remaining])
            truncated = True
            break
        chunks.append(chunk)
        total += len(chunk)
        if total >= max_bytes:
            break

    encoding = response.encoding or "utf-8"
    return b"".join(chunks).decode(encoding, errors="replace"), truncated


def fetch_page(
    url: str, timeout: int = 30, max_bytes: int = MAX_FETCH_BYTES
) -> dict[str, Any]:
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        return {
            "url": url,
            "error": f"unsupported URL scheme: {scheme or 'missing'}",
            "status": 0,
        }

    hostname = parsed.hostname or ""
    if _is_private_ip(hostname):
        return {
            "url": url,
            "error": "SSRF blocked: target is a private/internal IP address",
            "status": 0,
        }

    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) GalaxyMerge/0.1",
    }
    try:
        response = requests.get(url, headers=headers, timeout=timeout, stream=True)
        try:
            response.raise_for_status()
            content_type = _content_type(response.headers)

            if _is_binary_content_type(content_type):
                return {
                    "url": url,
                    "error": f"blocked binary content type: {content_type or 'unknown'}",
                    "content_type": content_type,
                    "status": response.status_code,
                }

            body, truncated = _read_limited_text(response, max_bytes)

            if content_type in HTML_CONTENT_TYPES:
                soup = BeautifulSoup(body, "lxml")
                for tag in soup(
                    [
                        "script",
                        "style",
                        "nav",
                        "footer",
                        "header",
                        "iframe",
                        "object",
                        "embed",
                    ]
                ):
                    tag.decompose()
                text = soup.get_text(separator="\n", strip=True)
                text = "\n".join(line for line in text.splitlines() if line.strip())
                title = (
                    soup.title.string.strip()
                    if soup.title and soup.title.string
                    else ""
                )
                result_content_type = "html"
            else:
                text = body
                title = ""
                result_content_type = content_type

            injections = _detect_prompt_injection(text)
            sanitized = _strip_prompt_injection(text)
            return {
                "url": url,
                "title": title,
                "content": sanitized,
                "content_type": result_content_type,
                "status": response.status_code,
                "injections_detected": len(injections),
                "injection_patterns": injections,
                "sanitized": len(injections) > 0,
                "truncated": truncated,
                "max_bytes": max_bytes,
            }
        finally:
            response.close()
    except requests.RequestException as e:
        return {"url": url, "error": str(e), "status": 0}
