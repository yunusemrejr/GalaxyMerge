import re
from pathlib import Path
from typing import Any

from galaxy_merge.safety.path_utils import is_relative_to


GALAXY_MERGE_SOURCE_PATTERNS = [
    re.compile(r'(?:^|[\s"/])galaxy_merge/'),
    re.compile(r'(?:^|[\s"/])pyproject\.toml(?:$|\s)'),
    re.compile(r'(?:^|[\s"/])\.gm/'),
    re.compile(r'(?:^|[\s"])gm(?:\s|$)'),
]


GALAXY_MERGE_SOURCE_FILES = [
    "galaxy_merge/",
    "pyproject.toml",
    "gm ",
    ".gm/",
]

ALLOWED_READ_ONLY_COMMANDS = {
    "ls",
    "cat",
    "head",
    "tail",
    "rg",
    "grep",
    "find",
    "read",
    "diff",
    "echo",
    "printf",
    "which",
    "file",
    "stat",
    "pwd",
}


class SelfProtectionPolicy:
    def __init__(self, workroot: Path, gm_dir: Path):
        self.workroot = workroot.resolve()
        self.gm_dir = gm_dir.resolve()

    def check_path(self, path: Path) -> dict[str, Any]:
        resolved = path.resolve()
        install_dir = self._find_install_dir()
        if install_dir and is_relative_to(resolved, install_dir):
            return {
                "decision": "block",
                "reason": "self-modification blocked: install directory",
            }
        return {"decision": "allow", "reason": "not a self path"}

    def check_command(self, command: str) -> dict[str, Any]:
        stripped = command.strip()
        first_word = stripped.split()[0] if stripped.split() else ""

        if first_word not in ALLOWED_READ_ONLY_COMMANDS:
            for gp in GALAXY_MERGE_SOURCE_FILES:
                if gp in stripped:
                    return {
                        "decision": "block",
                        "reason": f"self-modification blocked: command targets {gp}",
                    }

            for pattern in GALAXY_MERGE_SOURCE_PATTERNS:
                if pattern.search(stripped):
                    return {
                        "decision": "block",
                        "reason": "self-modification blocked: regex match",
                    }

        return {"decision": "allow", "reason": "not a self command"}

    def is_inside_galaxy_merge_codebase(self) -> bool:
        install_dir = self._find_install_dir()
        if not install_dir:
            return False
        try:
            wrs = str(self.workroot)
            return is_relative_to(Path(wrs), install_dir)
        except Exception:
            return False

    def _find_install_dir(self) -> Path | None:
        try:
            import galaxy_merge

            pkg_path = Path(galaxy_merge.__file__).resolve().parent
            install_dir = pkg_path.parent
            if (install_dir / "pyproject.toml").exists() or (
                install_dir / "gm"
            ).exists():
                return install_dir
            return None
        except Exception:
            return None
