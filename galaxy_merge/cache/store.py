import hashlib
import json
import time
from pathlib import Path
from typing import Any

from galaxy_merge.core.locks import FileLock, LockTimeout, atomic_write


class CacheStore:
    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _key_path(self, key: str) -> Path:
        h = hashlib.sha256(key.encode()).hexdigest()[:32]
        return self.cache_dir / f"{h}.json"

    def get(self, key: str) -> Any | None:
        path = self._key_path(key)
        if not path.exists():
            return None
        lock_path = path.with_suffix(".lock")
        try:
            with FileLock(lock_path, timeout=5.0):
                data = json.loads(path.read_text())
                expires = data.get("_expires", 0)
                if expires and time.time() > expires:
                    path.unlink(missing_ok=True)
                    return None
                return data.get("value")
        except (json.JSONDecodeError, OSError, LockTimeout):
            return None

    def set(self, key: str, value: Any, ttl_seconds: int = 300) -> None:
        expires = time.time() + ttl_seconds if ttl_seconds else 0
        data = {"value": value, "_expires": expires, "_created": time.time()}
        path = self._key_path(key)
        with FileLock(path.with_suffix(".lock"), timeout=5.0):
            atomic_write(path, json.dumps(data, default=str), _nested_lock=True)

    def invalidate(self, key: str) -> None:
        path = self._key_path(key)
        with FileLock(path.with_suffix(".lock"), timeout=5.0):
            path.unlink(missing_ok=True)

    def clear(self) -> None:
        for f in self.cache_dir.iterdir():
            if f.suffix == ".json":
                f.unlink(missing_ok=True)
