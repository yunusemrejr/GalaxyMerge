import asyncio
import json
from typing import Any

from galaxy_merge.fusion.roles import ROLE_DEFINITIONS
from galaxy_merge.providers.base import ProviderBase
from galaxy_merge.safety.credential_policy import redact_text

OFFLINE_MOCK_RESPONSES: dict[str, dict[str, Any]] = {
    "planner": {
        "goal_understanding": "offline mock: goal acknowledged",
        "relevant_files": ["src/main.py"],
        "steps": ["analyze goal", "determine approach", "apply changes"],
        "completion_criteria": ["changes applied", "no syntax errors"],
        "risks": ["offline mode: review depth limited"],
    },
    "scout": {
        "files_found": ["src/main.py"],
        "architecture_summary": "offline mock: no workspace scan performed",
        "uncertainties": ["offline mode: limited context"],
    },
    "implementer": {
        "changes": [
            {
                "file": "src/main.py",
                "action": "edit",
                "diff": "# offline mock: no changes applied",
                "rationale": "offline mode — no real implementation",
            }
        ],
    },
    "reviewer": {
        "findings": [
            {
                "type": "info",
                "file": "src/main.py",
                "evidence": "offline mode: no real review performed",
                "severity": "low",
                "recommendation": "provide API keys for real review",
            }
        ],
        "approved": True,
    },
    "cheap_verifier": {
        "findings": [
            {
                "type": "info",
                "file": "src/main.py",
                "evidence": "offline mode: no real verification",
                "severity": "low",
            }
        ],
        "syntax_ok": True,
        "summary": "offline mock verification: no syntax errors detected",
    },
    "skeptic": {
        "blockers": [],
        "missing_evidence": ["offline mode: cannot fully verify"],
        "completion_claim_valid": True,
    },
    "synthesizer": {
        "plan": [
            {
                "tool": "offline_mock",
                "params": {},
                "rationale": "offline mode — no real synthesis",
            }
        ],
        "summary": "offline mock: no changes needed (provide API keys for real work)",
        "contradictions_resolved": [],
    },
}


class OfflineMockProvider(ProviderBase):
    """Deterministic offline provider that produces valid schema-conformant
    responses for every council role without any network calls.

    Automatically injected by ProviderRegistry when zero real providers are
    available, so the harness always produces a usable plan even with no API
    keys or all providers down.
    """

    def __init__(self, provider_id: str = "offline_mock", config: dict[str, Any] | None = None):
        super().__init__(provider_id, config or {"type": "mock"})
        self._healthy = True
        self._available = True

    async def chat_completion(
        self,
        messages: list[dict[str, str]],
        model: str,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        stream: bool = False,
        extra_body: dict[str, Any] | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        role = _extract_role(messages)
        response_data = OFFLINE_MOCK_RESPONSES.get(role, {"raw": "offline mock response"})
        content = json.dumps(response_data)
        return {
            "success": True,
            "content": content,
            "model": model,
            "usage": {},
            "provider": self.provider_id,
        }

    async def check_health(self) -> bool:
        return True


def _extract_role(messages: list[dict[str, str]]) -> str:
    """Extract the council role from the system message content."""
    for msg in messages:
        if msg.get("role") != "system":
            continue
        content = msg.get("content", "")
        for role in ROLE_DEFINITIONS:
            if role in content and role != "synthesizer":
                return role
        if "synthesizer" in content:
            return "synthesizer"
    return ""


class MockProvider(ProviderBase):
    """Explicitly configured provider for deterministic local tests."""

    def __init__(self, provider_id: str, config: dict[str, Any]):
        super().__init__(provider_id, config)
        self._mock_responses: dict[str, dict[str, Any]] = config.get("responses", {})
        self._mock_failures: dict[str, Any] = config.get("failures", {})
        self._delay = float(config.get("delay_seconds", 0.0) or 0.0)
        self.call_history: list[dict[str, Any]] = []

    def set_mock_responses(self, responses: dict[str, dict[str, Any]]) -> None:
        self._mock_responses = responses

    def set_role_response(self, role: str, response_data: dict[str, Any]) -> None:
        self._mock_responses[role] = response_data

    def set_role_failure(self, role: str, failure: Any) -> None:
        self._mock_failures[role] = failure

    def set_delay(self, seconds: float) -> None:
        self._delay = seconds

    async def chat_completion(
        self,
        messages: list[dict[str, str]],
        model: str,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        stream: bool = False,
        **kwargs,
    ) -> dict[str, Any]:
        if self._delay > 0:
            await asyncio.sleep(self._delay)

        role = self._extract_role(messages)
        self.call_history.append(
            {"role": role, "model": model, "provider": self.provider_id}
        )

        failure = self._mock_failures.get(role)
        if failure:
            if isinstance(failure, dict):
                error = failure.get("error", "mock provider failure")
                return {
                    "success": bool(failure.get("success", False)),
                    "error": redact_text(str(error)),
                    "content": failure.get("content", ""),
                    "model": model,
                    "provider": self.provider_id,
                }
            return {
                "success": False,
                "error": redact_text(str(failure)),
                "model": model,
                "provider": self.provider_id,
            }

        response_data = self._mock_responses.get(role, {})
        content = (
            json.dumps(response_data)
            if response_data
            else json.dumps({"raw": "mock response"})
        )
        return {
            "success": True,
            "content": content,
            "model": model,
            "usage": {},
            "provider": self.provider_id,
        }

    async def check_health(self) -> bool:
        return self._healthy

    def _extract_role(self, messages: list[dict[str, str]]) -> str:
        for msg in messages:
            if msg.get("role") != "system":
                continue
            content = msg.get("content", "")
            for role in ROLE_DEFINITIONS:
                if role in content and role != "synthesizer":
                    return role
            if "synthesizer" in content:
                return "synthesizer"
        return ""
