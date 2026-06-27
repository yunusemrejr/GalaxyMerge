from pathlib import Path
from typing import Any

from galaxy_merge.cache.store import CacheStore


class FusionCache:
    def __init__(self, cache_dir: Path):
        self.store = CacheStore(cache_dir / "fusion")

    def get(self, council_name: str, goal_hash: str) -> dict[str, Any] | None:
        key = f"fusion:{council_name}:{goal_hash}"
        return self.store.get(key)

    def set(self, council_name: str, goal_hash: str, result: dict[str, Any]) -> None:
        key = f"fusion:{council_name}:{goal_hash}"
        self.store.set(key, result, ttl_seconds=600)
