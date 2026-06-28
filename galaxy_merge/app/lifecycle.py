import os
import sys
import platform
from pathlib import Path

from galaxy_merge.core.session import Session

PROVIDER_ENV_VARS = [
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GOOGLE_API_KEY",
    "DEEPSEEK_API_KEY",
    "MINIMAX_API_KEY",
    "STREAMLAKE_API_KEY",
    "STEPFUN_API_KEY",
    "OPENROUTER_API_KEY",
    "GITHUB_TOKEN",
    "GH_TOKEN",
]


REPOSITORY_URL = "https://github.com/yunusemrejr/GalaxyMerge"


def print_boot_log(
    version: str,
    workroot: Path,
    session_id: str,
    url: str,
    port: int,
    provider_stats: dict | None = None,
) -> None:
    print(f"Galaxy Merge Harness v{version}", file=sys.stderr)
    print(f"Repository: {REPOSITORY_URL}", file=sys.stderr)
    print(f"WorkRoot: {workroot}", file=sys.stderr)
    print(f"Session ID: {session_id}", file=sys.stderr)
    print(f"GUI: {url}", file=sys.stderr)
    print(f"Safety: enabled", file=sys.stderr)

    if provider_stats:
        loaded = provider_stats.get("loaded", 0)
        available = provider_stats.get("available", 0)
        unavailable = provider_stats.get("unavailable", 0)
    else:
        loaded = 0
        available = 0
        for var in PROVIDER_ENV_VARS:
            if var != "GH_TOKEN":
                loaded += 1
                if os.environ.get(var, ""):
                    available += 1
        unavailable = loaded - available
    print(f"Providers: {loaded} loaded, {available} available, {unavailable} unavailable", file=sys.stderr)
    print(f"Browser: isolated profile ready", file=sys.stderr)


def shutdown(session: Session) -> None:
    session.event_log.emit(
        "session_completed",
        session_id=session.session_id,
        workroot=str(session.workroot),
    )
    session.mark_completed()


def _check(label: str, ok: bool, detail: str = "", critical: bool = True) -> bool:
    status = "OK" if ok else ("MISSING" if critical else "WARN")
    msg = f"  [{status}] {label}"
    if detail:
        msg += f" — {detail}"
    print(msg)
    return ok


def run_doctor() -> int:
    print("Galaxy Merge Harness — Doctor")
    print("=" * 50)
    print()

    all_ok = True

    # --- Python ---
    print("--- Python ---")
    py_ver = sys.version.split()[0]
    major, minor = sys.version_info[:2]
    py_ok = major >= 3 and minor >= 12
    _check("Python >= 3.12", py_ok, py_ver)
    all_ok &= py_ok
    print(f"  Platform: {platform.platform()}")
    print()

    # --- Virtual environment ---
    print("--- Virtual Environment ---")
    in_venv = hasattr(sys, 'prefix') and sys.prefix != sys.base_prefix
    _check("Running in venv", in_venv, sys.prefix if in_venv else "system Python")
    print()

    # --- Required packages ---
    print("--- Required Packages ---")
    _IMPORT_NAMES = {
        "pyyaml": "yaml",
        "beautifulsoup4": "bs4",
    }
    required = ["fastapi", "uvicorn", "pydantic", "httpx", "websockets", "pyyaml", "requests"]
    for pkg in required:
        try:
            import_name = _IMPORT_NAMES.get(pkg, pkg)
            mod = __import__(import_name)
            ver = getattr(mod, '__version__', '?')
            _check(pkg, True, ver)
        except ImportError:
            _check(pkg, False, critical=(pkg in ("fastapi", "uvicorn", "pydantic")))
            if pkg in ("fastapi", "uvicorn", "pydantic"):
                all_ok = False
    print()

    # --- Optional packages ---
    print("--- Optional Packages ---")
    optional = ["beautifulsoup4", "lxml"]
    for pkg in optional:
        try:
            import_name = _IMPORT_NAMES.get(pkg, pkg)
            mod = __import__(import_name)
            ver = getattr(mod, '__version__', '?')
            _check(pkg, True, ver)
        except ImportError:
            _check(pkg, False, "optional")
    print()

    # --- Launcher ---
    print("--- Launcher ---")
    bin_dir = Path.home() / ".local" / "bin"
    launcher = bin_dir / "gm"
    launcher_exists = launcher.exists() and launcher.is_file()
    _check("~/.local/bin/gm exists", launcher_exists, str(launcher))

    path_dirs = os.environ.get("PATH", "").split(":")
    bin_in_path = str(bin_dir) in path_dirs
    _check("~/.local/bin in PATH", bin_in_path)
    if not bin_in_path and bin_dir.exists():
        print("    Add: export PATH=\"$HOME/.local/bin:$PATH\"")
    print()

    # --- Config files ---
    print("--- Config Files ---")
    try:
        import galaxy_merge
        install_dir = Path(galaxy_merge.__file__).resolve().parent.parent
    except Exception:
        install_dir = Path.cwd()

    config_dir = install_dir / "galaxy_merge" / "config_templates"
    for name in ("providers", "models", "fusion", "routing"):
        p = config_dir / f"{name}.json"
        _check(f"config_templates/{name}.json", p.exists(), critical=False)
    print()

    # --- Example configs ---
    print("--- Example Configs ---")
    example_dir = install_dir / "config"
    for name in ("providers", "models", "fusion", "routing"):
        p = example_dir / f"{name}.example.json"
        _check(f"config/{name}.example.json", p.exists())
    print()

    # --- Provider keys ---
    print("--- Provider Keys ---")
    available_count = 0
    for var in PROVIDER_ENV_VARS:
        val = os.environ.get(var, "")
        if val:
            available_count += 1
            _check(var, True, "set")
        else:
            _check(var, False, "not set")
    print(f"  Summary: {available_count}/{len(PROVIDER_ENV_VARS)} provider keys available")
    print()

    # --- Secret safety ---
    print("--- Secret Safety ---")
    gitignore = install_dir / ".gitignore"
    if gitignore.exists():
        content = gitignore.read_text()
        _check(".gm/ in .gitignore", ".gm/" in content)
        _check(".env in .gitignore", ".env" in content)
        _check("providers.json in .gitignore", "providers.json" in content or "**/providers.json" in content)
    else:
        _check(".gitignore exists", False)
    print()

    # --- .env.example ---
    env_example = install_dir / ".env.example"
    _check(".env.example exists", env_example.exists())
    print()

    # --- Summary ---
    print("=" * 50)
    if all_ok:
        print("Result: All critical checks passed.")
    else:
        print("Result: Some checks failed. See above for details.")
    print()
    return 0 if all_ok else 1
