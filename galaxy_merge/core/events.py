import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from galaxy_merge.core.locks import atomic_append


class EventLog:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.touch()

    def emit(self, event: str, session_id: str = "", **kwargs: Any) -> dict[str, Any]:
        record = {
            "time": datetime.now(timezone.utc).isoformat(),
            "session_id": session_id,
            "event": event,
            **kwargs,
        }
        line = json.dumps(record, default=str)
        atomic_append(self.path, line)
        return record

    def replay(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        lock_path = self.path.with_suffix(self.path.suffix + ".lock")
        import fcntl, os
        fd = None
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o644)
            fcntl.flock(fd, fcntl.LOCK_SH)
            records = []
            with open(self.path) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            records.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass
            return records
        finally:
            if fd is not None:
                try:
                    fcntl.flock(fd, fcntl.LOCK_UN)
                except OSError:
                    pass
                try:
                    os.close(fd)
                except OSError:
                    pass

    def replay_from(self, offset: int = 0, limit: int | None = None) -> list[dict[str, Any]]:
        records = self.replay()
        if offset <= 0:
            offset = 0
        if limit is None:
            return records[offset:]
        if limit <= 0:
            return []
        return records[offset:offset + limit]
