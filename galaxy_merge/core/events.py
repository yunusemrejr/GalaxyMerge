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
        records = []
        with open(self.path) as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
        return records
