from pathlib import Path
from typing import Any


class TaskScope:
    def __init__(self, workroot: Path):
        self.workroot = workroot.resolve()
        self._scope_paths: list[Path] = []
        self._scope_files: list[Path] = []

    def set_from_plan(self, files: list[str]) -> None:
        self._scope_files = [(self.workroot / f).resolve() for f in files]
        dirs = set()
        for f in self._scope_files:
            if f.exists():
                dirs.add(f.parent)
        self._scope_paths = list(dirs)

    def contains(self, path: Path) -> bool:
        resolved = path.resolve()
        if not self._scope_files:
            return str(resolved).startswith(str(self.workroot))
        for sp in self._scope_files:
            if str(resolved) == str(sp):
                return True
        for dp in self._scope_paths:
            if str(resolved).startswith(str(dp)):
                return True
        return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "scope_paths": [str(p) for p in self._scope_paths],
            "scope_files": [str(p) for p in self._scope_files],
        }
