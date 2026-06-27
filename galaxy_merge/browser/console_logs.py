import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from galaxy_merge.core.locks import atomic_append


class ConsoleLogCollector:
    def __init__(self, session_id: str, cache_dir: Path):
        self.session_id = session_id
        self.log_path = cache_dir / "browser" / "console_logs.jsonl"
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def add_log(self, level: str, message: str, source: str = "") -> None:
        record = {
            "time": datetime.now(timezone.utc).isoformat(),
            "session_id": self.session_id,
            "level": level,
            "message": message,
            "source": source,
        }
        atomic_append(self.log_path, json.dumps(record))

    def get_logs(self, max_count: int = 100) -> list[dict[str, Any]]:
        if not self.log_path.exists():
            return []
        logs = []
        with open(self.log_path) as f:
            for line in f:
                line = line.strip()
                if line:
                    record = json.loads(line)
                    if record.get("session_id") == self.session_id:
                        logs.append(record)
        return logs[-max_count:]

    def add_error(self, message: str, source: str = "") -> None:
        self.add_log("error", message, source)

    def add_warning(self, message: str, source: str = "") -> None:
        self.add_log("warning", message, source)

    def add_info(self, message: str, source: str = "") -> None:
        self.add_log("info", message, source)
