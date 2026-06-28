import hashlib
import json
from pathlib import Path
from typing import Any

from galaxy_merge.core.locks import FileLock, atomic_write
from galaxy_merge.workspace.tree import FileTree


class WorkspaceIndexer:
    def __init__(self, workroot: Path):
        self.workroot = workroot.resolve()
        self.index_dir = self.workroot / ".gm" / "indexes"
        self.index_dir.mkdir(parents=True, exist_ok=True)
        self._file_hashes: dict[str, str] = self._load_hashes()

    def _load_hashes(self) -> dict[str, str]:
        path = self.index_dir / "file_hashes.json"
        if path.exists():
            with FileLock(path.with_suffix(".lock"), timeout=10.0):
                return json.loads(path.read_text())
        return {}

    def _save_hashes(self) -> None:
        path = self.index_dir / "file_hashes.json"
        with FileLock(path.with_suffix(".lock"), timeout=10.0):
            atomic_write(
                path, json.dumps(self._file_hashes, indent=2), _nested_lock=True
            )

    def _hash_file(self, path: Path) -> str:
        h = hashlib.sha256()
        h.update(path.read_bytes())
        return h.hexdigest()[:16]

    def refresh(self) -> dict[str, Any]:
        changed: list[str] = []
        removed: list[str] = []
        current_hashes: dict[str, str] = {}
        file_count = 0

        for path in self.workroot.rglob("*"):
            if path.is_file() and not path.name.startswith("."):
                relative = str(path.relative_to(self.workroot))
                try:
                    file_hash = self._hash_file(path)
                    current_hashes[relative] = file_hash
                    file_count += 1
                    if relative in self._file_hashes:
                        if self._file_hashes[relative] != file_hash:
                            changed.append(relative)
                    else:
                        changed.append(relative)
                except (OSError, PermissionError):
                    pass

        for rel in self._file_hashes:
            if rel not in current_hashes:
                removed.append(rel)

        hashes_path = self.index_dir / "file_hashes.json"
        with FileLock(hashes_path.with_suffix(".lock"), timeout=10.0):
            self._file_hashes = current_hashes
            atomic_write(
                hashes_path, json.dumps(self._file_hashes, indent=2), _nested_lock=True
            )

        tree = FileTree(self.workroot).build()

        summary = {
            "total_files": file_count,
            "changed": changed,
            "removed": removed,
            "tree": tree,
        }
        atomic_write(
            self.index_dir / "index.meta.json",
            json.dumps({"changed": changed, "removed": removed, "total": file_count}),
        )

        return summary

    def incremental_update(self, files: list[str]) -> dict[str, Any]:
        changed = []
        hashes_path = self.index_dir / "file_hashes.json"
        with FileLock(hashes_path.with_suffix(".lock"), timeout=10.0):
            if hashes_path.exists():
                self._file_hashes = json.loads(hashes_path.read_text())
            for f in files:
                path = (self.workroot / f).resolve()
                if path.exists() and path.is_file():
                    try:
                        file_hash = self._hash_file(path)
                        relative = str(path.relative_to(self.workroot))
                        old_hash = self._file_hashes.get(relative)
                        self._file_hashes[relative] = file_hash
                        if old_hash != file_hash:
                            changed.append(relative)
                    except (OSError, ValueError):
                        pass
            atomic_write(
                hashes_path, json.dumps(self._file_hashes, indent=2), _nested_lock=True
            )
            total = len(self._file_hashes)
        return {"changed": changed, "total": total}
