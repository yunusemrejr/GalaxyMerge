from pathlib import Path
from typing import Any


class FileSummarizer:
    def __init__(self, workroot: Path):
        self.workroot = workroot

    def summarize(self, path: Path) -> dict[str, Any]:
        relative = str(path.relative_to(self.workroot))
        ext = path.suffix.lower()

        summary: dict[str, Any] = {
            "path": relative,
            "size": path.stat().st_size if path.exists() else 0,
            "extension": ext,
        }

        if ext == ".py":
            summary["type"] = "python"
            summary["imports"] = self._count_imports(path)
        elif ext == ".ts" or ext == ".tsx":
            summary["type"] = "typescript"
            summary["imports"] = self._count_imports(path)
        elif ext == ".js" or ext == ".jsx":
            summary["type"] = "javascript"
            summary["imports"] = self._count_imports(path)
        elif ext == ".md":
            summary["type"] = "markdown"
        elif ext == ".json":
            summary["type"] = "json"
        elif ext in (".yml", ".yaml"):
            summary["type"] = "yaml"
        elif ext == ".html":
            summary["type"] = "html"
        elif ext == ".css":
            summary["type"] = "css"
        else:
            summary["type"] = "other"

        return summary

    def _count_imports(self, path: Path) -> int:
        count = 0
        try:
            for line in path.read_text().splitlines():
                if line.strip().startswith(("import ", "from ", "require(")):
                    count += 1
        except Exception:
            pass
        return count
