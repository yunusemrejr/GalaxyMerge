import os
import sys
import signal
from pathlib import Path

from galaxy_merge.app.server import start_server
from galaxy_merge.app.browser import open_browser
from galaxy_merge.app.lifecycle import print_boot_log, shutdown
from galaxy_merge.core.session import detect_workroot, init_gm_dir, Session
from galaxy_merge.core.config import load_app_config, save_app_config, AppConfig
from galaxy_merge.core.errors import GalaxyMergeError
from galaxy_merge.safety.self_protection import SelfProtectionPolicy
from galaxy_merge.core.concurrency import (
    cleanup_stale_sessions,
    register_active_session,
    upgrade_concurrency,
    write_heartbeat,
)

VERSION = "0.1.0"


def _detect_install_dir() -> Path | None:
    try:
        import galaxy_merge
        pkg_path = Path(galaxy_merge.__file__).resolve().parent
        install_dir = pkg_path.parent
        if (install_dir / "pyproject.toml").exists() or (install_dir / "gm").exists():
            return install_dir
    except Exception:
        pass
    return None


def _is_inside_galaxy_merge_codebase(workroot: Path) -> bool:
    install_dir = _detect_install_dir()
    if not install_dir:
        return False
    try:
        return workroot.resolve().is_relative_to(install_dir.resolve())
    except (ValueError, AttributeError):
        return False


def print_self_codebase_warning() -> None:
    print("", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    print("Galaxy Merge detected that it was launched", file=sys.stderr)
    print("inside its own source tree.", file=sys.stderr)
    print("", file=sys.stderr)
    print("Normal autonomous mode is disabled here.", file=sys.stderr)
    print("Read-only diagnostic mode is active.", file=sys.stderr)
    print("", file=sys.stderr)
    print("To use Galaxy Merge on a project:", file=sys.stderr)
    print("", file=sys.stderr)
    print("  cd /path/to/your/project", file=sys.stderr)
    print("  gm", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    print("", file=sys.stderr)


class Launcher:
    def __init__(
        self,
        project_dir: str | None = None,
        port: int = 0,
        no_browser: bool = False,
        resume_session_id: str | None = None,
    ):
        self.project_dir = project_dir
        self.port = port
        self.no_browser = no_browser
        self.resume_session_id = resume_session_id
        self.session: Session | None = None
        self.server_info: dict | None = None
        self._shutdown_flag = False

    def run(self) -> int:
        config = load_app_config()

        cwd = Path(self.project_dir).resolve() if self.project_dir else Path.cwd()
        workroot = detect_workroot(cwd)
        if workroot is None:
            print(
                "Error: Cannot determine safe WorkRoot. "
                "Run gm from a project directory.",
                file=sys.stderr,
            )
            return 1

        inside_own_codebase = _is_inside_galaxy_merge_codebase(workroot)
        if inside_own_codebase:
            print_self_codebase_warning()

        init_gm_dir(workroot)
        upgrade_concurrency(workroot / ".gm")
        cleanup_stale_sessions(workroot / ".gm")

        session_id = self.resume_session_id
        self.session = Session(workroot, session_id=session_id)
        self.session.save_state()
        register_active_session(self.session.gm_dir, self.session.session_id)
        write_heartbeat(self.session.gm_dir, self.session.session_id)

        self.server_info = start_server(self.session, port=self.port)

        print_boot_log(
            version=VERSION,
            workroot=workroot,
            session_id=self.session.session_id,
            url=self.server_info["url"],
            port=self.server_info["port"],
        )

        if not self.no_browser:
            open_browser(self.server_info["url"])

        self._setup_signal_handlers()

        try:
            self.server_info["server"].serve()
        except KeyboardInterrupt:
            pass
        finally:
            self._shutdown()

        return 0

    def _setup_signal_handlers(self) -> None:
        def handler(signum, frame):
            if not self._shutdown_flag:
                self._shutdown_flag = True
                print("\nShutting down...", file=sys.stderr)
                self._shutdown()
                sys.exit(0)

        signal.signal(signal.SIGINT, handler)
        signal.signal(signal.SIGTERM, handler)

    def _shutdown(self) -> None:
        if self.session:
            self.session.event_log.emit(
                "session_completed",
                session_id=self.session.session_id,
                workroot=str(self.session.workroot),
            )
            self.session.mark_completed()
