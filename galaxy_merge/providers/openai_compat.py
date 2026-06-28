import os
from typing import Any

import httpx

from galaxy_merge.providers.base import ProviderBase
from galaxy_merge.safety.credential_policy import redact_text


class OpenAICompatibleProvider(ProviderBase):
    def __init__(self, provider_id: str, config: dict[str, Any]):
        super().__init__(provider_id, config)
        self.base_url = config.get("base_url", "").rstrip("/")
        auth_config = config.get("auth", {})
        self.api_key = self._resolve_api_key(auth_config)
        self.timeout = config.get("timeout_seconds", 90)
        if auth_config.get("type") == "env" and not self.api_key:
            env_var = auth_config.get("env_var", "")
            self._healthy = False
            self._available = False
            self._warning = f"missing env var: {env_var}"

    def _resolve_api_key(self, auth_config: dict[str, Any]) -> str:
        if auth_config.get("type") == "env":
            env_var = auth_config.get("env_var", "")
            return os.environ.get(env_var, "")
        return ""

    async def chat_completion(
        self,
        messages: list[dict[str, str]],
        model: str,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        stream: bool = False,
    ) -> dict[str, Any]:
        if not self.available:
            return {"success": False, "error": self.warning or "provider unavailable"}
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "stream": stream,
        }
        if max_tokens:
            body["max_tokens"] = max_tokens

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=body,
                )
                response.raise_for_status()
                data = response.json()

                content = ""
                if data.get("choices"):
                    content = data["choices"][0].get("message", {}).get("content", "")

                return {
                    "success": True,
                    "content": content,
                    "model": data.get("model", model),
                    "usage": data.get("usage", {}),
                    "provider": self.provider_id,
                }
            except httpx.TimeoutException:
                return {"success": False, "error": "request timed out"}
            except httpx.HTTPStatusError as e:
                return {"success": False, "error": redact_text(f"HTTP {e.response.status_code}: {e.response.text}")}
            except Exception as e:
                return {"success": False, "error": redact_text(str(e))}

    async def check_health(self) -> bool:
        if not self.available:
            return False
        async with httpx.AsyncClient(timeout=10) as client:
            try:
                response = await client.get(
                    f"{self.base_url}/models",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
                self._healthy = response.status_code < 500
                return self._healthy
            except Exception:
                self._healthy = False
                return False
