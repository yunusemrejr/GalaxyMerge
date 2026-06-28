import asyncio
import json
from typing import Any

from galaxy_merge.fusion.roles import ROLE_DEFINITIONS
from galaxy_merge.providers.base import ProviderBase
from galaxy_merge.safety.credential_policy import redact_text


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
        self.call_history.append({"role": role, "model": model, "provider": self.provider_id})

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
        content = json.dumps(response_data) if response_data else json.dumps({"raw": "mock response"})
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
