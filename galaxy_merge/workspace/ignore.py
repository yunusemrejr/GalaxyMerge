from pathlib import Path

GITIGNORE_PATTERNS: set[str] = {
    "__pycache__/", "*.py[cod]", "*$py.class",
    "*.so", ".Python", "env/", "venv/", ".venv/",
    "dist/", "build/", "*.egg-info/",
    ".git/", ".gm/cache/",
    "node_modules/", ".npm/",
    "target/", "Cargo.lock",
    ".DS_Store", "*.log", ".coverage",
    ".mypy_cache/", ".ruff_cache/", ".pytest_cache/",
}


def should_ignore(path: Path, workroot: Path) -> bool:
    name = path.name
    if path.is_dir() and name.startswith(".") and name != ".gm":
        return True
    if name in GITIGNORE_PATTERNS:
        return True
    for pattern in GITIGNORE_PATTERNS:
        if pattern.endswith("/") and path.is_dir() and name == pattern.rstrip("/"):
            return True
        if pattern.startswith("*.") and path.suffix == pattern[1:]:
            return True
    return False
