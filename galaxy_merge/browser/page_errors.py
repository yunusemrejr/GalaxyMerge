import json
from datetime import datetime, timezone
from pathlib import Path

from galaxy_merge.core.locks import atomic_append


class PageErrorCollector:
    def __init__(self, cache_dir: Path, session_id: str):
        self.session_id = session_id
        self.log_path = cache_dir / "browser" / "page_errors.jsonl"
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def add_error(self, error_type: str, message: str, source: str = "") -> None:
        record = {
            "time": datetime.now(timezone.utc).isoformat(),
            "session_id": self.session_id,
            "type": error_type,
            "message": message,
            "source": source,
        }
        atomic_append(self.log_path, json.dumps(record))

    def get_errors(self, max_count: int = 100) -> list[dict[str, str]]:
        if not self.log_path.exists():
            return []
        errors = []
        with open(self.log_path) as f:
            for line in f:
                line = line.strip()
                if line:
                    record = json.loads(line)
                    if record.get("session_id") == self.session_id:
                        errors.append(record)
        return errors[-max_count:]
