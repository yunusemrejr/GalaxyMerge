from pathlib import Path

from galaxy_merge.cache.store import CacheStore


class FileCache:
    def __init__(self, cache_dir: Path):
        self.store = CacheStore(cache_dir / "file_summaries")

    def get_summary(self, file_path: str, file_hash: str) -> str | None:
        key = f"summary:{file_path}:{file_hash}"
        return self.store.get(key)

    def set_summary(self, file_path: str, file_hash: str, summary: str) -> None:
        key = f"summary:{file_path}:{file_hash}"
        self.store.set(key, summary, ttl_seconds=3600)
