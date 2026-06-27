import sys
import argparse

from galaxy_merge.app.launcher import Launcher

VERSION = "0.1.0"


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="gm",
        description="Galaxy Merge Harness — autonomous coding harness",
    )
    parser.add_argument(
        "--version", action="store_true", help="print version and exit"
    )
    parser.add_argument("--no-browser", action="store_true", help="do not open browser")
    parser.add_argument("--port", type=int, default=0, help="server port (0 = auto)")
    parser.add_argument(
        "--project",
        type=str,
        default=None,
        help="explicit project directory",
    )
    parser.add_argument(
        "--resume", type=str, default=None, help="session ID to resume"
    )
    parser.add_argument("--doctor", action="store_true", help="run diagnostics")

    args = parser.parse_args()

    if args.version:
        print(f"Galaxy Merge Harness v{VERSION}")
        return 0

    if args.doctor:
        from galaxy_merge.app.lifecycle import run_doctor

        return run_doctor()

    launcher = Launcher(
        project_dir=args.project,
        port=args.port,
        no_browser=args.no_browser,
        resume_session_id=args.resume,
    )
    return launcher.run()


if __name__ == "__main__":
    sys.exit(main())
