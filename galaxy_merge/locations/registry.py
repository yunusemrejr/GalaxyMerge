import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from galaxy_merge.core.locks import atomic_write


class LocationRegistry:
    def __init__(self, gm_dir: Path):
        self.path = gm_dir / "locations" / "registry.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._registry: dict[str, Any] = self._load()

    def _load(self) -> dict[str, Any]:
        if self.path.exists():
            return json.loads(self.path.read_text())
        return {
            "schema_version": 1,
            "workroot": "",
            "remote_targets": [],
            "protected_locations": [],
        }

    def _save(self) -> None:
        atomic_write(self.path, json.dumps(self._registry, indent=2, default=str))

    def init_from_project(self, workroot: Path, gm_dir: Path) -> None:
        self._registry["workroot"] = str(workroot)
        self._registry["taskscope"] = [str(workroot)]
        self._registry["protected_locations"] = []

        git_dir = workroot / ".git"
        if git_dir.exists():
            import subprocess

            try:
                result = subprocess.run(
                    ["git", "remote", "-v"],
                    cwd=str(workroot),
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                remotes = {}
                for line in result.stdout.splitlines():
                    parts = line.split()
                    if len(parts) >= 3:
                        name, url = parts[0], parts[1]
                        remotes[name] = url
                self._registry["git"] = {"repo_root": str(workroot), "remotes": remotes}
                branch = subprocess.run(
                    ["git", "branch", "--show-current"],
                    cwd=str(workroot),
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                self._registry["git"]["current_branch"] = branch.stdout.strip()
            except Exception:
                pass

        self._save()

    def register_remote(
        self,
        remote_id: str,
        target_type: str,
        host: str,
        path: str,
        classification: str,
    ) -> None:
        entry = {
            "id": remote_id,
            "type": target_type,
            "host": host,
            "path": path,
            "classification": classification,
            "write_policy": "blocked_by_default",
            "registered_at": datetime.now(timezone.utc).isoformat(),
        }
        existing = [
            r
            for r in self._registry.get("remote_targets", [])
            if r.get("id") == remote_id
        ]
        if existing:
            existing[0].update(entry)
        else:
            self._registry.setdefault("remote_targets", []).append(entry)
        self._save()

    def to_dict(self) -> dict[str, Any]:
        return dict(self._registry)

    def get_location_events_path(self) -> Path:
        path = self.path.parent / "location_events.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path
