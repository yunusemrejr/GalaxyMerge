"""Fake adapters for deterministic, fast test isolation.

Every adapter in this module replaces a real external dependency
(network, browser, clock, provider API) with a configurable in-memory
implementation.  No real I/O, no real network, no real subprocesses.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ── FakeClock ─────────────────────────────────────────────────────────


class FakeClock:
    """Deterministic clock for TTL/timeout tests.

    Usage::

        clock = FakeClock()
        store = CacheStore(cache_dir, clock=clock.now)
        clock.advance(10)  # pretend 10 seconds passed
    """

    def __init__(self, start: float = 1000.0):
        self._now = start

    def now(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds

    def __call__(self) -> float:
        return self._now


# ── FakeProvider ──────────────────────────────────────────────────────


@dataclass
class FakeProvider:
    """In-memory provider that returns configurable responses instantly.

    No real network, no asyncio.sleep, no real API keys.
    """

    provider_id: str = "fake_provider"
    base_url: str = "http://fake.local/v1"
    auth_type: str = "none"
    _healthy: bool = True
    _available: bool = True
    _warning: str = ""
    _responses: dict[str, dict[str, Any]] = field(default_factory=dict)
    _call_history: list[dict[str, Any]] = field(default_factory=list)
    _fail_mode: str | None = None  # None, "timeout", "error", "malformed"

    # ── Configuration ────────────────────────────────────────────────

    def set_response(self, role: str, data: dict[str, Any]) -> None:
        self._responses[role] = data

    def set_fail_mode(self, mode: str | None) -> None:
        self._fail_mode = mode

    def set_healthy(self, healthy: bool) -> None:
        self._healthy = healthy
        self._available = healthy

    # ── Interface ────────────────────────────────────────────────────

    async def chat_completion(
        self,
        messages: list[dict[str, str]],
        model: str,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        stream: bool = False,
    ) -> dict[str, Any]:
        role = self._extract_role(messages)
        self._call_history.append(
            {
                "role": role,
                "model": model,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
        )

        if self._fail_mode == "error":
            return {"success": False, "error": "simulated failure"}
        if self._fail_mode == "malformed":
            return {"success": True, "content": "{bad json"}
        if self._fail_mode == "empty":
            return {"success": True, "content": ""}

        response = self._responses.get(role, {})
        return {
            "success": True,
            "content": json.dumps(response),
            "model": model,
            "provider": self.provider_id,
        }

    async def check_health(self) -> bool:
        return self._healthy

    @property
    def healthy(self) -> bool:
        return self._healthy

    @property
    def available(self) -> bool:
        return self._available and self._healthy

    @property
    def warning(self) -> str:
        return self._warning

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "type": "fake",
            "base_url": self.base_url,
            "auth_type": self.auth_type,
            "healthy": self._healthy,
            "available": self.available,
            "warning": self._warning,
        }

    # ── Internal ─────────────────────────────────────────────────────

    @staticmethod
    def _extract_role(messages: list[dict[str, str]]) -> str:
        """Extract the council role from system prompt, if any."""
        for msg in messages:
            content = msg.get("content", "")
            if "You are the" in content:
                for word in content.split():
                    if word in (
                        "planner",
                        "scout",
                        "implementer",
                        "reviewer",
                        "cheap_verifier",
                        "skeptic",
                        "synthesizer",
                    ):
                        return word
        return "unknown"

    @classmethod
    def from_config(cls, provider_id: str, config: dict[str, Any]) -> FakeProvider:
        auth = config.get("auth", {})
        return cls(
            provider_id=provider_id,
            base_url=config.get("base_url", ""),
            auth_type=auth.get("type", "unknown"),
        )


# ── FakeBrowserManager ───────────────────────────────────────────────


@dataclass
class FakeBrowserSession:
    session_id: str
    url: str = "about:blank"
    running: bool = True
    _console_logs: list[dict[str, Any]] = field(default_factory=list)
    _network_logs: list[dict[str, Any]] = field(default_factory=list)


class FakeBrowserManager:
    """In-memory browser manager. No real Chrome/Playwright/Selenium.

    Usage::

        mgr = FakeBrowserManager(tmp_path / ".gm")
        mgr.open_session("test", "http://localhost:3000")
        mgr.add_console_log("test", {"level": "error", "message": "x is undefined"})
        logs = mgr.get_console_logs("test")
    """

    def __init__(self, gm_dir: Path):
        self._sessions: dict[str, FakeBrowserSession] = {}

    def open_session(self, session_id: str, url: str = "about:blank") -> dict[str, Any]:
        sess = FakeBrowserSession(session_id=session_id, url=url)
        self._sessions[session_id] = sess
        return {"session_id": session_id, "url": url, "running": True}

    def close_session(self, session_id: str) -> dict[str, Any]:
        sess = self._sessions.pop(session_id, None)
        if sess:
            sess.running = False
        return {"session_id": session_id, "closed": True}

    def list_sessions(self) -> list[dict[str, Any]]:
        return [
            {"session_id": s.session_id, "url": s.url, "running": s.running}
            for s in self._sessions.values()
        ]

    def add_console_log(self, session_id: str, entry: dict[str, Any]) -> None:
        sess = self._sessions.get(session_id)
        if sess:
            sess._console_logs.append(entry)

    def add_network_log(self, session_id: str, entry: dict[str, Any]) -> None:
        sess = self._sessions.get(session_id)
        if sess:
            sess._network_logs.append(entry)

    def get_console_logs(self, session_id: str) -> list[dict[str, Any]]:
        sess = self._sessions.get(session_id)
        return list(sess._console_logs) if sess else []

    def get_network_logs(self, session_id: str) -> list[dict[str, Any]]:
        sess = self._sessions.get(session_id)
        return list(sess._network_logs) if sess else []

    def screenshot(self, session_id: str) -> dict[str, Any]:
        return {"session_id": session_id, "screenshot": "fake-base64-data"}


# ── FakeEventBus ──────────────────────────────────────────────────────


class FakeEventBus:
    """In-memory event bus that records emitted events for assertions.

    Usage::

        bus = FakeEventBus()
        bus.emit("tool_call", tool="file.read")
        assert len(bus.events) == 1
        assert bus.events[0]["event"] == "tool_call"
    """

    def __init__(self):
        self.events: list[dict[str, Any]] = []

    def emit(self, event: str, **kwargs: Any) -> None:
        self.events.append({"event": event, **kwargs})

    def clear(self) -> None:
        self.events.clear()

    def filter(self, event: str) -> list[dict[str, Any]]:
        return [e for e in self.events if e.get("event") == event]

    @property
    def count(self) -> int:
        return len(self.events)


# ── Session-scoped helpers ────────────────────────────────────────────


class FakeProjectFactory:
    """Create minimal, deterministic test projects."""

    @staticmethod
    def python_project(root: Path, name: str = "test-project") -> Path:
        p = root / name
        p.mkdir(parents=True, exist_ok=True)
        (p / "README.md").write_text(f"# {name}")
        (p / "src").mkdir()
        (p / "src" / "main.py").write_text("def main():\n    print('hello')\n")
        (p / "tests").mkdir()
        (p / "tests" / "test_main.py").write_text(
            "def test_main():\n    assert 1 + 1 == 2\n"
        )
        return p

    @staticmethod
    def js_project(root: Path, name: str = "test-webapp") -> Path:
        p = root / name
        p.mkdir(parents=True, exist_ok=True)
        (p / "README.md").write_text(f"# {name}")
        (p / "package.json").write_text(
            json.dumps({"name": name, "scripts": {"test": "jest"}})
        )
        (p / "src").mkdir()
        (p / "src" / "index.html").write_text("<html><body><p>Hi</p></body></html>")
        (p / "src" / "app.js").write_text("console.log('hello');")
        return p


# ── Assertion helpers ────────────────────────────────────────────────


def assert_no_secrets_in_text(
    text: str, secret_patterns: list[str] | None = None
) -> None:
    """Fail if *text* contains any known secret pattern.

    Default patterns include common API key prefixes.
    """
    patterns = secret_patterns or [
        "sk-",
        "pk-",
        "sv-",
        "ghp_",
        "gho_",
        "ghu_",
        "ghs_",
        "ghr_",
        "nvapi-",
        "xai-",
        "fad8b",
        "AKIA",
        "eyJ",
        "-----BEGIN",
    ]
    for pat in patterns:
        if pat in text:
            raise AssertionError(f"Secret pattern found in text: {pat!r}")


def assert_safety_blocked(result: dict[str, Any]) -> None:
    """Assert a Safety Governor result is a block decision."""
    assert result.get("decision") == "block", f"Expected block, got {result}"


def assert_safety_allowed(result: dict[str, Any]) -> None:
    """Assert a Safety Governor result is an allow decision."""
    assert result.get("decision") in ("allow", "allow_with_audit"), (
        f"Expected allow, got {result}"
    )
