import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from galaxy_merge.core.locks import atomic_append


class Checkpoints:
    def __init__(self, gm_dir: Path):
        self.patchsets_dir = gm_dir / "git" / "patchsets"
        self.patchsets_dir.mkdir(parents=True, exist_ok=True)
        self._index_path = gm_dir / "git" / "checkpoints.jsonl"

    def save(
        self, checkpoint_id: str, session_id: str, files_changed: list[str], reason: str
    ) -> dict[str, Any]:
        record = {
            "checkpoint_id": checkpoint_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "session_id": session_id,
            "files_changed": files_changed,
            "reason": reason,
            "verified": False,
        }
        atomic_append(self._index_path, json.dumps(record))
        return record

    def list_all(self) -> list[dict[str, Any]]:
        if not self._index_path.exists():
            return []
        records = []
        with open(self._index_path) as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
        return records
