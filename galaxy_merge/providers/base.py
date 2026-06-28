from abc import ABC, abstractmethod
from typing import Any


class ProviderBase(ABC):
    def __init__(self, provider_id: str, config: dict[str, Any]):
        self.provider_id = provider_id
        self.config = config
        self._healthy = True
        self._available = True
        self._warning = ""

    @abstractmethod
    async def chat_completion(
        self,
        messages: list[dict[str, str]],
        model: str,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        stream: bool = False,
    ) -> dict[str, Any]: ...

    @abstractmethod
    async def check_health(self) -> bool: ...

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
        auth_type = self.config.get("auth", {}).get("type", "unknown")
        return {
            "provider_id": self.provider_id,
            "type": self.config.get("type", "unknown"),
            "base_url": self.config.get("base_url", ""),
            "auth_type": auth_type,
            "healthy": self._healthy,
            "available": self.available,
            "warning": self._warning,
        }
