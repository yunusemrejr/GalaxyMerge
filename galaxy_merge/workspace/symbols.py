from pathlib import Path
from typing import Any


def extract_symbols(file_path: Path) -> list[dict[str, Any]]:
    symbols = []
    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return symbols

    for i, line in enumerate(content.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith(("def ", "class ", "async def ")):
            kind = "class" if stripped.startswith("class ") else "function"
            name = stripped.split("(")[0].split(" ")[-1] if kind == "function" else stripped.split("(")[0].split(" ")[-1]
            if kind == "function":
                name = stripped.replace("async ", "").split("(")[0].split(" ")[-1]
            elif kind == "class":
                name = stripped.split("(")[0].split(" ")[-1].rstrip(":")
            symbols.append({
                "name": name,
                "kind": kind,
                "line": i,
                "file": str(file_path),
            })
    return symbols


def index_project_symbols(workroot: Path) -> list[dict[str, Any]]:
    all_symbols = []
    for path in workroot.rglob("*.py"):
        if ".gm" in str(path) or "node_modules" in str(path):
            continue
        all_symbols.extend(extract_symbols(path))
    return all_symbols
