from pathlib import Path
from typing import Any

IGNORE_DIRS: set[str] = {
    ".git", ".gm/cache", "node_modules", "venv", ".venv",
    "dist", "build", "target", "__pycache__", ".cache",
    "coverage", ".mypy_cache", ".ruff_cache", ".pytest_cache",
}

IGNORE_EXTENSIONS: set[str] = {".pyc", ".pyo", ".so", ".o", ".class"}

IGNORE_FILES: set[str] = {"*.log", "*.pid"}


class FileTree:
    def __init__(self, workroot: Path):
        self.workroot = workroot.resolve()

    def build(self) -> dict[str, Any]:
        return self._build_node(self.workroot)

    def _build_node(self, path: Path) -> dict[str, Any]:
        name = path.name
        if path.is_file():
            size = path.stat().st_size
            return {"name": name, "type": "file", "size": size}
        children = []
        try:
            for child in sorted(path.iterdir()):
                if self._should_ignore(child):
                    continue
                children.append(self._build_node(child))
        except PermissionError:
            pass
        return {"name": name, "type": "directory", "children": children}

    def _should_ignore(self, path: Path) -> bool:
        name = path.name
        if path.is_dir():
            if name in IGNORE_DIRS:
                return True
            if name.startswith(".") and name not in (".gm",):
                return True
        else:
            if path.suffix in IGNORE_EXTENSIONS:
                return True
            if name.startswith("."):
                return True
        return False
