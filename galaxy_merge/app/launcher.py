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
from galaxy_merge.core.concurrency import (
    cleanup_stale_sessions,
    register_active_session,
    upgrade_concurrency,
    write_heartbeat,
)

VERSION = "0.1.0"


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
