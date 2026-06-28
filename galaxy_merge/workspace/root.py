from pathlib import Path
from typing import Any


def detect_language(workroot: Path) -> list[str]:
    languages = []
    if (workroot / "pyproject.toml").exists() or list(workroot.glob("*.py")):
        languages.append("python")
    if (workroot / "package.json").exists():
        languages.append("javascript")
        if (workroot / "tsconfig.json").exists():
            languages.append("typescript")
    if (workroot / "Cargo.toml").exists():
        languages.append("rust")
    if (workroot / "go.mod").exists():
        languages.append("go")
    if (workroot / "composer.json").exists():
        languages.append("php")
    if (workroot / "pom.xml").exists():
        languages.append("java")
    return languages


def detect_framework(workroot: Path) -> list[str]:
    frameworks = []
    if (workroot / "pyproject.toml").exists():
        content = (workroot / "pyproject.toml").read_text()
        for fw in ("fastapi", "django", "flask", "litestar"):
            if fw in content:
                frameworks.append(fw)
    if (workroot / "package.json").exists():
        import json

        try:
            pkg = json.loads((workroot / "package.json").read_text())
            deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
            for fw in ("next", "react", "vue", "svelte", "angular", "express"):
                if fw in str(deps):
                    frameworks.append(fw)
        except (json.JSONDecodeError, Exception):
            pass
    return frameworks


def detect_package_manager(workroot: Path) -> str | None:
    if (workroot / "uv.lock").exists() or (workroot / "pyproject.toml").exists():
        return "uv"
    if (workroot / "pnpm-lock.yaml").exists():
        return "pnpm"
    if (workroot / "yarn.lock").exists():
        return "yarn"
    if (workroot / "package-lock.json").exists():
        return "npm"
    if (workroot / "Cargo.lock").exists():
        return "cargo"
    if (workroot / "go.sum").exists():
        return "go"
    return None


def detect_test_command(workroot: Path) -> str | None:
    if (
        (workroot / "pyproject.toml").exists()
        or list(workroot.glob("test_*.py"))
        or list(workroot.glob("*_test.py"))
    ):
        return "pytest"
    if (workroot / "package.json").exists():
        return "npm test"
    if (workroot / "Cargo.toml").exists():
        return "cargo test"
    if (workroot / "go.mod").exists():
        return "go test ./..."
    return None


def analyze_workroot(workroot: Path) -> dict[str, Any]:
    return {
        "language": detect_language(workroot),
        "framework": detect_framework(workroot),
        "package_manager": detect_package_manager(workroot),
        "test_command": detect_test_command(workroot),
        "has_git": (workroot / ".git").exists(),
        "name": workroot.name,
    }
