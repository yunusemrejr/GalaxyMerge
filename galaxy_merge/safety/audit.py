import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from galaxy_merge.core.locks import atomic_append


class SafetyAudit:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, check_type: str, target: str, result: dict[str, Any]) -> None:
        record = {
            "time": datetime.now(timezone.utc).isoformat(),
            "type": check_type,
            "target": target,
            "decision": result["decision"],
            "reason": result.get("reason", ""),
        }
        atomic_append(self.path, json.dumps(record))

    def recent(self, n: int = 50) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        records = []
        with open(self.path) as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
        return records[-n:]
