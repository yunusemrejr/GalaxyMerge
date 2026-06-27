import sys
from pathlib import Path

from galaxy_merge.core.session import Session


def print_boot_log(
    version: str,
    workroot: Path,
    session_id: str,
    url: str,
    port: int,
) -> None:
    print(f"Galaxy Merge Harness v{version}", file=sys.stderr)
    print(f"WorkRoot: {workroot}", file=sys.stderr)
    print(f"Session ID: {session_id}", file=sys.stderr)
    print(f"GUI: {url}", file=sys.stderr)
    print(f"Safety: enabled", file=sys.stderr)


def shutdown(session: Session) -> None:
    session.event_log.emit(
        "session_completed",
        session_id=session.session_id,
        workroot=str(session.workroot),
    )
    session.mark_completed()


def run_doctor() -> int:
    import platform

    print("Galaxy Merge Harness — Doctor")
    print(f"Python: {sys.version}")
    print(f"Platform: {platform.platform()}")
    print(f"CWD: {Path.cwd()}")

    try:
        import fastapi
        print(f"FastAPI: {fastapi.__version__}")
    except ImportError:
        print("FastAPI: NOT INSTALLED")

    try:
        import uvicorn
        print(f"Uvicorn: {uvicorn.__version__}")
    except ImportError:
        print("Uvicorn: NOT INSTALLED")

    return 0
