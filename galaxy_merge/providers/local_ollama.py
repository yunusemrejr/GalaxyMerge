from typing import Any

import httpx

from galaxy_merge.providers.base import ProviderBase


class OllamaProvider(ProviderBase):
    def __init__(self, provider_id: str, config: dict[str, Any]):
        super().__init__(provider_id, config)
        self.base_url = config.get("base_url", "http://127.0.0.1:11434").rstrip("/")
        self.timeout = config.get("timeout_seconds", 180)

    async def chat_completion(
        self,
        messages: list[dict[str, str]],
        model: str,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        stream: bool = False,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "stream": stream,
        }
        if max_tokens:
            body["options"] = {"num_predict": max_tokens}

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(
                    f"{self.base_url}/api/chat",
                    json=body,
                )
                response.raise_for_status()
                data = response.json()

                return {
                    "success": True,
                    "content": data.get("message", {}).get("content", ""),
                    "model": data.get("model", model),
                    "usage": {},
                    "provider": self.provider_id,
                }
            except httpx.TimeoutException:
                return {"success": False, "error": "request timed out"}
            except Exception as e:
                return {"success": False, "error": str(e)}

    async def check_health(self) -> bool:
        async with httpx.AsyncClient(timeout=5) as client:
            try:
                response = await client.get(f"{self.base_url}/api/tags")
                self._healthy = response.status_code < 500
                return self._healthy
            except Exception:
                self._healthy = False
                return False
