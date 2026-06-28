import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from galaxy_merge.core.locks import atomic_append


class NetworkLogCollector:
    def __init__(self, cache_dir: Path, session_id: str = ""):
        self.session_id = session_id
        self.log_path = cache_dir / "browser" / "network_logs.jsonl"
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def add_request(
        self, url: str, method: str, status: int = 0, error: str = ""
    ) -> None:
        record = {
            "time": datetime.now(timezone.utc).isoformat(),
            "type": "request",
            "session_id": self.session_id,
            "url": url,
            "method": method,
            "status": status,
            "error": error,
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
                    if (
                        not self.session_id
                        or record.get("session_id") == self.session_id
                    ):
                        logs.append(record)
        return logs[-max_count:]
