"""Fake adapters and factories for deterministic, isolated testing."""

from __future__ import annotations

import asyncio
import json
import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Fake Provider Adapter
# ---------------------------------------------------------------------------


class FakeProvider:
    """Minimal provider that returns canned responses without network."""

    def __init__(
        self, provider_id: str = "fake", responses: dict[str, Any] | None = None
    ):
        self.provider_id = provider_id
        self.config: dict[str, Any] = {"type": "mock", "enabled": True}
        self.available = True
        self.warning: str | None = None
        self.healthy = True
        self._responses = responses or {}
        self._default_response = {
            "success": True,
            "content": '{"steps": [], "completion_criteria": []}',
        }
        self.call_log: list[dict[str, Any]] = []

    def set_response(self, role: str, response: dict[str, Any]) -> None:
        self._responses[role] = response

    def set_healthy(self, healthy: bool) -> None:
        self.healthy = healthy

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.provider_id, "type": "mock", "available": self.available}

    async def chat_completion(
        self,
        messages: list[dict[str, str]],
        model: str,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        stream: bool = False,
        **kwargs: Any,
    ) -> dict[str, Any]:
        role = self._extract_role(messages)
        self.call_log.append(
            {"role": role, "model": model, "provider": self.provider_id}
        )
        return dict(self._responses.get(role, self._default_response))

    @staticmethod
    def _extract_role(messages: list[dict[str, str]]) -> str:
        for msg in messages:
            if msg.get("role") == "system":
                content = msg.get("content", "")
                for r in (
                    "planner",
                    "scout",
                    "implementer",
                    "reviewer",
                    "skeptic",
                    "cheap_verifier",
                    "synthesizer",
                ):
                    if r in content:
                        return r
        return ""


class FakeProviderRegistry:
    """In-memory provider registry for tests that don't need real config files."""

    def __init__(self) -> None:
        self._providers: dict[str, FakeProvider] = {}
        self._models: dict[str, dict[str, Any]] = {}
        self._event_log: Any | None = None

    def add(self, provider: FakeProvider) -> None:
        self._providers[provider.provider_id] = provider

    def add_model(self, key: str, config: dict[str, Any]) -> None:
        self._models[key] = config

    def get(self, provider_id: str) -> FakeProvider | None:
        return self._providers.get(provider_id)

    def get_model(self, model_key: str) -> dict[str, Any] | None:
        return self._models.get(model_key)

    def get_models_for_role(self, role: str) -> list[tuple[str, str, dict[str, Any]]]:
        results = []
        for mid, cfg in self._models.items():
            if role in cfg.get("roles", []) and cfg.get("enabled", True):
                pid = cfg.get("provider", "")
                model = cfg.get("model", mid)
                results.append((pid, model, cfg))
        return results

    def mark_unhealthy(self, provider_id: str, **kwargs: Any) -> None:
        p = self._providers.get(provider_id)
        if p:
            p.healthy = False

    def load(self) -> None:
        pass

    @property
    def providers(self) -> dict[str, FakeProvider]:
        return self._providers


# ---------------------------------------------------------------------------
# Fake Browser Manager
# ---------------------------------------------------------------------------


class FakeBrowserManager:
    """Browser manager that never launches a real browser."""

    def __init__(self, profile_dir: Path | None = None):
        self.profile_dir = profile_dir
        self._launched = False
        self._closed = False
        self.commands: list[str] = []

    def launch(self, **kwargs: Any) -> None:
        self._launched = True

    def close(self) -> None:
        self._closed = True

    def navigate(self, url: str) -> None:
        self.commands.append(f"navigate:{url}")

    def screenshot(self, path: str) -> None:
        self.commands.append(f"screenshot:{path}")

    @property
    def is_running(self) -> bool:
        return self._launched and not self._closed


# ---------------------------------------------------------------------------
# Fake Event Bus / Event Log
# ---------------------------------------------------------------------------


class FakeEventBus:
    """In-memory event bus for testing event-driven code."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []
        self._subscribers: dict[str, list[Any]] = {}

    def emit(self, event_type: str, **kwargs: Any) -> None:
        event = {"type": event_type, "timestamp": time.time(), **kwargs}
        self.events.append(event)
        for handler in self._subscribers.get(event_type, []):
            handler(event)

    def subscribe(self, event_type: str, handler: Any) -> None:
        self._subscribers.setdefault(event_type, []).append(handler)

    def clear(self) -> None:
        self.events.clear()

    def find(self, event_type: str) -> list[dict[str, Any]]:
        return [e for e in self.events if e.get("type") == event_type]

    def count(self, event_type: str) -> int:
        return len(self.find(event_type))


# ---------------------------------------------------------------------------
# Fake Clock
# ---------------------------------------------------------------------------


class FakeClock:
    """Deterministic clock for testing time-dependent logic."""

    def __init__(self, start: float = 1000.0) -> None:
        self._now = start

    def time(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds

    def set(self, t: float) -> None:
        self._now = t


# ---------------------------------------------------------------------------
# Project / .gm / Config Factories
# ---------------------------------------------------------------------------


def make_fake_project(tmp_path: Path, name: str = "fake_project") -> Path:
    """Create a minimal fake project directory with a few files."""
    project_dir = tmp_path / name
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "main.py").write_text("print('hello')\n")
    (project_dir / "README.md").write_text(f"# {name}\n")
    (project_dir / "src").mkdir(exist_ok=True)
    (project_dir / "src" / "__init__.py").write_text("")
    (project_dir / "src" / "utils.py").write_text("def helper(): pass\n")
    return project_dir


def make_fake_gm_dir(tmp_path: Path) -> Path:
    """Create a minimal .gm directory structure."""
    gm_dir = tmp_path / ".gm"
    gm_dir.mkdir(parents=True, exist_ok=True)
    (gm_dir / "locks").mkdir(exist_ok=True)
    (gm_dir / "notes").mkdir(exist_ok=True)
    (gm_dir / "sessions").mkdir(exist_ok=True)
    (gm_dir / "memory").mkdir(exist_ok=True)
    (gm_dir / "project.json").write_text(
        json.dumps(
            {
                "name": "test_project",
                "created": "2025-01-01T00:00:00Z",
            }
        )
    )
    return gm_dir


def make_fake_config(
    tmp_path: Path,
    providers: dict[str, Any] | None = None,
    models: dict[str, Any] | None = None,
    fusion: dict[str, Any] | None = None,
) -> Path:
    """Create a minimal config directory with providers.json, models.json, fusion.json."""
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)

    if providers is None:
        providers = {
            "providers": {
                "fake": {
                    "enabled": True,
                    "type": "mock",
                    "base_url": "http://fake",
                    "auth": {"type": "none"},
                    "timeout_seconds": 5,
                }
            }
        }
    (config_dir / "providers.json").write_text(json.dumps(providers))

    if models is None:
        models = {
            "models": {
                "fake:all": {
                    "provider": "fake",
                    "model": "fake-v1",
                    "enabled": True,
                    "context_window": 32000,
                    "strengths": [
                        "planning",
                        "implementation",
                        "synthesis",
                        "review",
                        "fast_scan",
                    ],
                    "roles": [
                        "planner",
                        "scout",
                        "implementer",
                        "reviewer",
                        "skeptic",
                        "cheap_verifier",
                        "synthesizer",
                    ],
                }
            }
        }
    (config_dir / "models.json").write_text(json.dumps(models))

    if fusion is None:
        fusion = {
            "max_parallel_calls": 4,
            "timeout_seconds": 5,
            "retry_count": 1,
            "retry_backoff": 0,
            "roles": {
                "planner": {
                    "required": True,
                    "model_selector": {"role": "planner", "cost_policy": "balanced"},
                },
                "scout": {
                    "required": True,
                    "model_selector": {"role": "scout", "cost_policy": "cheap"},
                },
                "implementer": {
                    "required": True,
                    "model_selector": {"role": "implementer", "cost_policy": "quality"},
                },
                "reviewer": {
                    "required": True,
                    "model_selector": {"role": "reviewer", "cost_policy": "balanced"},
                },
                "skeptic": {
                    "required": True,
                    "model_selector": {"role": "skeptic", "cost_policy": "balanced"},
                },
                "cheap_verifier": {
                    "required": True,
                    "count": 1,
                    "model_selector": {
                        "role": "cheap_verifier",
                        "cost_policy": "cheap",
                    },
                },
                "synthesizer": {
                    "required": True,
                    "model_selector": {"role": "synthesizer", "cost_policy": "quality"},
                },
            },
        }
    (config_dir / "fusion.json").write_text(json.dumps(fusion))

    return config_dir


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@contextmanager
def temp_env(**env: str):
    """Temporarily set environment variables, restoring originals on exit."""
    old = {}
    for k, v in env.items():
        old[k] = os.environ.get(k)
        os.environ[k] = v
    try:
        yield
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


async def bounded_receive(coro: Any, timeout: float = 2.0) -> Any:
    """Await a coroutine with a bounded timeout."""
    return await asyncio.wait_for(coro, timeout=timeout)


def assert_no_secrets(text: str, secrets: list[str] | None = None) -> None:
    """Assert that no secret values appear in text."""
    if secrets is None:
        secrets = []
    for secret in secrets:
        assert secret not in text, f"Secret leaked in output: {secret[:8]}..."


def make_tmp_gm_factory(tmp_path: Path):
    """Return a factory that creates fresh .gm dirs under tmp_path."""
    counter = [0]

    def factory() -> Path:
        counter[0] += 1
        return make_fake_gm_dir(tmp_path / f"gm_instance_{counter[0]}")

    return factory
