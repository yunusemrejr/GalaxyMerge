import os
import sys
import signal
import threading
from pathlib import Path

from galaxy_merge.app.server import start_server
from galaxy_merge.app.browser import open_browser
from galaxy_merge.app.lifecycle import print_boot_log
from galaxy_merge.core.session import (
    detect_workroot,
    init_gm_dir,
    Session,
    validate_gm_structure,
)
from galaxy_merge.core.config import load_app_config
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
        self._heartbeat_thread: threading.Thread | None = None
        self._heartbeat_stop = threading.Event()
        self._shutdown_reason: str | None = None
        self._shutdown_done = False

    def run(self) -> int:
        load_app_config()

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

        gm_validation = validate_gm_structure(workroot / ".gm")
        if not gm_validation["ok"]:
            print("", file=sys.stderr)
            print(
                f"WARNING: .gm/ structure validation found {len(gm_validation['warnings'])} issue(s):",
                file=sys.stderr,
            )
            for w in gm_validation["warnings"][:8]:
                print(f"  - {w}", file=sys.stderr)
            if len(gm_validation["warnings"]) > 8:
                print(
                    f"  ... and {len(gm_validation['warnings']) - 8} more (see .gm/ logs)",
                    file=sys.stderr,
                )
            print("", file=sys.stderr)

        session_id = self.resume_session_id
        self.session = Session(workroot, session_id=session_id)
        if session_id and not self.session.resume():
            print(
                f"Cannot resume session {self.session.session_id}: already complete or running",
                file=sys.stderr,
            )
            return 1
        self.session.save_state()
        self.session.mark_running()

        write_heartbeat(self.session.gm_dir, self.session.session_id)

        self.server_info = start_server(self.session, port=self.port)
        mapped_port = self.server_info["port"]

        from galaxy_merge.providers.registry import ProviderRegistry

        provider_registry = ProviderRegistry(
            self.server_info["server"].config_dir, session_id=self.session.session_id
        )
        provider_registry.load()
        all_providers = provider_registry.available_providers()
        loaded = len(all_providers)
        available = sum(1 for p in all_providers if p.get("available", True))
        unavailable = loaded - available
        provider_stats = {
            "loaded": loaded,
            "available": available,
            "unavailable": unavailable,
        }
        register_active_session(
            self.session.gm_dir,
            self.session.session_id,
            port=mapped_port,
            pid=os.getpid(),
        )

        print_boot_log(
            version=VERSION,
            workroot=workroot,
            session_id=self.session.session_id,
            url=self.server_info["url"],
            port=mapped_port,
            provider_stats=provider_stats,
        )

        if not self.no_browser:
            open_browser(self.server_info["url"])

        self._setup_signal_handlers()
        self._start_heartbeat()

        try:
            self.server_info["server"].serve()
        except KeyboardInterrupt:
            self._shutdown_reason = None
        except Exception as exc:
            self._shutdown_reason = str(exc)
        finally:
            self._shutdown()

        return 0

    def _setup_signal_handlers(self) -> None:
        def handler(signum, frame):
            if self._shutdown_flag:
                return
            self._shutdown_flag = True
            self._shutdown_reason = "received_signal"
            print("\nShutting down...", file=sys.stderr)
            server = self.server_info["server"] if self.server_info else None
            if server and server._server:
                server._server.should_exit = True

        signal.signal(signal.SIGINT, handler)
        signal.signal(signal.SIGTERM, handler)

    def _start_heartbeat(self, interval: float = 3.0) -> None:
        self._heartbeat_stop.clear()

        def _loop() -> None:
            session = self.session
            if not session:
                return
            while not self._heartbeat_stop.wait(interval):
                try:
                    write_heartbeat(session.gm_dir, session.session_id)
                except Exception:
                    pass

        self._heartbeat_thread = threading.Thread(target=_loop, daemon=True)
        self._heartbeat_thread.start()

    def _stop_heartbeat(self) -> None:
        self._heartbeat_stop.set()
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            self._heartbeat_thread.join(timeout=1.0)

    def _shutdown(self) -> None:
        if self._shutdown_done:
            return
        self._shutdown_done = True
        self._stop_heartbeat()
        if self.session:
            if self._shutdown_reason == "received_signal":
                if self.session._state.get("status") not in {"complete", "stopped"}:
                    self.session.mark_stopped("stopped_by_signal")
                    self.session.event_log.emit(
                        "session_stopped",
                        session_id=self.session.session_id,
                        workroot=str(self.session.workroot),
                    )
            elif self._shutdown_reason:
                self.session.mark_crashed(self._shutdown_reason)
                self.session.event_log.emit(
                    "session_crashed",
                    session_id=self.session.session_id,
                    error=self._shutdown_reason,
                    workroot=str(self.session.workroot),
                )
            else:
                if self.session._state.get("status") not in {"complete", "stopped"}:
                    self.session.mark_completed()
                self.session.event_log.emit(
                    "session_completed",
                    session_id=self.session.session_id,
                    workroot=str(self.session.workroot),
                )
        self._shutdown_flag = True
        if self.server_info:
            server = self.server_info["server"]
            if server._socket is not None:
                try:
                    server._socket.close()
                except OSError:
                    pass
                server._socket = None
