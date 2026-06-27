import json
from pathlib import Path
from typing import Any

from galaxy_merge.core.locks import FileLock, LockTimeout, atomic_append, atomic_write


class MemoryStore:
    def __init__(self, gm_dir: Path):
        self.memory_dir = gm_dir / "memory"
        self.memory_dir.mkdir(parents=True, exist_ok=True)

    def append(self, kind: str, data: dict[str, Any]) -> None:
        path = self.memory_dir / f"{kind}.jsonl"
        atomic_append(path, json.dumps(data, default=str))

    def read_all(self, kind: str) -> list[dict[str, Any]]:
        path = self.memory_dir / f"{kind}.jsonl"
        if not path.exists():
            return []
        records = []
        lock_path = path.with_suffix(".lock")
        try:
            with FileLock(lock_path, timeout=5.0):
                lines = path.read_text().splitlines()
        except (OSError, LockTimeout):
            lines = path.read_text().splitlines()
        for line in lines:
            line = line.strip()
            if line:
                records.append(json.loads(line))
        return records

    def read_recent(self, kind: str, n: int = 20) -> list[dict[str, Any]]:
        all_records = self.read_all(kind)
        return all_records[-n:]

    def set_preference(self, key: str, value: Any) -> None:
        prefs_path = self.memory_dir / "preferences.json"
        with FileLock(prefs_path.with_suffix(".lock"), timeout=5.0):
            prefs: dict[str, Any] = {}
            if prefs_path.exists():
                prefs = json.loads(prefs_path.read_text())
            prefs[key] = value
            atomic_write(prefs_path, json.dumps(prefs, indent=2))

    def get_preference(self, key: str, default: Any = None) -> Any:
        prefs_path = self.memory_dir / "preferences.json"
        if prefs_path.exists():
            try:
                prefs = json.loads(prefs_path.read_text())
                return prefs.get(key, default)
            except json.JSONDecodeError:
                pass
        return default

    def clear(self, kind: str) -> None:
        path = self.memory_dir / f"{kind}.jsonl"
        if path.exists():
            with FileLock(path.with_suffix(".lock"), timeout=5.0):
                path.unlink()
