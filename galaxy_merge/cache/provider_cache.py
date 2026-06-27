from pathlib import Path
from typing import Any

from galaxy_merge.cache.store import CacheStore
from galaxy_merge.cache.keys import provider_cache_key, hash_messages


class ProviderCache:
    def __init__(self, cache_dir: Path):
        self.store = CacheStore(cache_dir / "provider")
        self.cache_dir = cache_dir

    def get(self, provider_id: str, model: str, role: str, messages: list[dict[str, str]]) -> dict[str, Any] | None:
        key = provider_cache_key(provider_id, model, role, hash_messages(messages))
        return self.store.get(key)

    def set(self, provider_id: str, model: str, role: str, messages: list[dict[str, str]], result: dict[str, Any], ttl: int = 300) -> None:
        key = provider_cache_key(provider_id, model, role, hash_messages(messages))
        self.store.set(key, result, ttl_seconds=ttl)

    def invalidate_provider(self, provider_id: str) -> None:
        self.store.clear()
