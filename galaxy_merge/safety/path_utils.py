from pathlib import Path


def is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def resolve_inside(root: Path, path: str | Path) -> Path | None:
    target = (root / path).resolve()
    if not is_relative_to(target, root):
        return None
    return target
