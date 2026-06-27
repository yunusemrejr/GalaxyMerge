from pathlib import Path
from typing import Any

from galaxy_merge.core.locks import atomic_append


class SessionMemory:
    def __init__(self, session_dir: Path):
        self.session_dir = session_dir
        self.transcript_path = session_dir / "transcript.jsonl"
        self._entries: list[dict[str, Any]] = []

    def add_entry(self, entry_type: str, content: Any) -> None:
        entry = {
            "type": entry_type,
            "content": content,
        }
        self._entries.append(entry)
        import json
        atomic_append(self.transcript_path, json.dumps(entry, default=str))

    def get_history(self) -> list[dict[str, Any]]:
        return self._entries

    def get_recent(self, n: int = 10) -> list[dict[str, Any]]:
        return self._entries[-n:]

    def clear(self) -> None:
        self._entries = []
        if self.transcript_path.exists():
            self.transcript_path.unlink()
