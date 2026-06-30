import json
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from galaxy_merge.core.events import EventLog
from galaxy_merge.core.locks import atomic_write
from galaxy_merge.core.runtime_models import SessionState


def _generate_id(prefix: str) -> str:
    suffix = secrets.token_hex(4)
    now = datetime.now(timezone.utc)
    return f"{prefix}_{now.strftime('%Y%m%d_%H%M%S')}_{suffix}"


class Session:
    def __init__(self, workroot: Path, session_id: str | None = None):
        self.workroot = workroot.resolve()
        self.gm_dir = self.workroot / ".gm"
        self.session_id = session_id or _generate_id("gmsess")
        self.session_dir = self.gm_dir / "sessions" / self.session_id
        self.created_at = datetime.now(timezone.utc)

        self.state_path = self.session_dir / "state.json"
        self.goal_path = self.session_dir / "goal.json"
        self.events_path = self.session_dir / "events.jsonl"

        self.event_log = EventLog(self.events_path)
        self._state: dict[str, Any] = self._load_state()
        if self._state.get("created_at"):
            try:
                self.created_at = datetime.fromisoformat(self._state["created_at"])
            except (TypeError, ValueError):
                pass

    def _load_state(self) -> dict[str, Any]:
        if self.state_path.exists():
            try:
                return json.loads(self.state_path.read_text())
            except (json.JSONDecodeError, OSError):
                return {
                    "status": "recovering",
                    "active": True,
                    "goal": "",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "error": "state_file_corrupted",
                }
        return {
            "status": "running",
            "active": True,
            "goal": "",
            "error": None,
        }

    def save_state(self) -> None:
        self.session_dir.mkdir(parents=True, exist_ok=True)
        for sub in ["diffs", "artifacts"]:
            (self.session_dir / sub).mkdir(parents=True, exist_ok=True)
        for fname in [
            "transcript.jsonl",
            "council.jsonl",
            "tool_calls.jsonl",
            "safety.jsonl",
            "provider_events.jsonl",
            "compaction.jsonl",
        ]:
            p = self.session_dir / fname
            if not p.exists():
                p.touch()

        state = SessionState(
            session_id=self.session_id,
            workroot=str(self.workroot),
            created_at=self.created_at,
            updated_at=datetime.now(timezone.utc),
            status=self._state.get("status", "running"),
            goal=self._state.get("goal", ""),
            active=self._state.get("active", True),
            error=self._state.get("error"),
            crash_count=self._state.get("crash_count", 0),
        )
        atomic_write(
            self.state_path,
            json.dumps(state.model_dump(mode="json"), indent=2, default=str),
        )

    def set_goal(self, goal: str) -> None:
        self._state["goal"] = goal
        self._state["status"] = "understanding"
        self.save_state()
        goal_data = {
            "goal": goal,
            "parsed": {},
            "status": "understanding",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self.goal_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(self.goal_path, json.dumps(goal_data, indent=2))

    def mark_running(self) -> None:
        self._state["status"] = "running"
        self._state["active"] = True
        self._state["error"] = None
        self.save_state()

    def mark_stopped(self, reason: str = "stopped") -> None:
        self._state["status"] = reason
        self._state["active"] = False
        self.save_state()

    def mark_completed(self) -> None:
        self._state["status"] = "complete"
        self._state["active"] = False
        self._state["error"] = None
        self._write_final_md("completed")
        self.save_state()

    def mark_crashed(self, reason: str | None = None) -> None:
        self._state["status"] = "crashed"
        self._state["active"] = False
        self._state["error"] = reason
        self._state["crash_count"] = self._state.get("crash_count", 0) + 1
        self.save_state()

    def _write_final_md(self, reason: str) -> None:
        """Write a final.md summary for the completed session."""
        goal_text = self._state.get("goal", "")
        lines = [
            f"# Session {self.session_id}",
            "",
            f"**Status:** {reason}",
            f"**Goal:** {goal_text}",
            f"**WorkRoot:** {self.workroot}",
            f"**Started:** {self.created_at.isoformat()}",
            f"**Reason:** {reason}",
            "",
        ]
        events_path = self.session_dir / "events.jsonl"
        if events_path.exists():
            try:
                events = [
                    json.loads(line)
                    for line in events_path.read_text().splitlines()
                    if line.strip()
                ]
            except (json.JSONDecodeError, OSError):
                events = []
            lines.append(f"**Events:** {len(events)} total")
            for e in events:
                lines.append(
                    f"- {e.get('event', '?')}: {e.get('goal', e.get('tool', e.get('task_type', '')))}"
                )
        atomic_write(self.session_dir / "final.md", "\n".join(lines))

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "workroot": str(self.workroot),
            "created_at": self.created_at.isoformat(),
            "status": self._state.get("status", "running"),
            "goal": self._state.get("goal", ""),
            "active": self._state.get("active", True),
            "error": self._state.get("error"),
        }

    def resume(self) -> bool:
        if self._state.get("status") in {"complete", "running"}:
            return False
        self._state["status"] = self._state.get("status", "recovering")
        self._state["active"] = True
        self._state["error"] = None
        self.save_state()
        return True

    def can_resume(self) -> bool:
        return self._state.get("status") in {
            "stopped",
            "crashed",
            "failed_safe",
            "recovering",
        }


def detect_workroot(path: Path) -> Path | None:
    path = path.resolve()
    signals = [
        ".git",
        "package.json",
        "pyproject.toml",
        "go.mod",
        "Cargo.toml",
        "composer.json",
        "pom.xml",
        "Makefile",
        ".project",
    ]
    forbidden_prefixes = [
        Path("/"),
        Path("/home").resolve(),
        Path.home(),
        Path.home() / "Desktop",
        Path.home() / "Downloads",
        Path("/usr"),
        Path("/bin"),
        Path("/etc"),
        Path("/var"),
        Path("/opt"),
        Path("/root"),
    ]
    blocked_tree_prefixes = [
        "/usr",
        "/bin",
        "/sbin",
        "/etc",
        "/var",
        "/opt",
        "/boot",
        "/dev",
        "/proc",
        "/sys",
        "/run",
        "/root",
    ]

    def _is_forbidden_root(candidate: Path) -> bool:
        for forbidden in forbidden_prefixes:
            if candidate == forbidden:
                return True
        candidate_str = str(candidate)
        for prefix in blocked_tree_prefixes:
            if candidate_str == prefix or candidate_str.startswith(prefix + "/"):
                return True
        return False

    current = path
    for _ in range(20):
        if _is_forbidden_root(current):
            # Hit a forbidden ancestor while walking up; stop traversing but
            # let the final check decide based on the original path.
            break
        for signal in signals:
            if (current / signal).exists():
                if _is_forbidden_root(current):
                    return None
                return current
        parent = current.parent
        if parent == current:
            break
        current = parent

    if _is_forbidden_root(path):
        return None
    return path


def init_gm_dir(workroot: Path) -> None:
    gm = workroot / ".gm"

    dirs = [
        "notes/history",
        "notes/.trash",
        "memory",
        "sessions",
        "skill_matches",
        "indexes/embeddings",
        "cache/provider",
        "cache/file_summaries",
        "cache/skill_matches",
        "cache/fusion",
        "cache/command_results",
        "cache/web_search",
        "cache/browser_pages",
        "cache/github_scans",
        "web",
        "browser/profiles",
        "browser/sessions",
        "browser/screenshots",
        "locations",
        "github/scans",
        "github/issues",
        "github/pull_requests",
        "logs",
        "safety",
        "git/patchsets",
    ]
    for d in dirs:
        (gm / d).mkdir(parents=True, exist_ok=True)

    _init_readme(gm)
    _init_project_json(gm, workroot)
    _init_notes_index(gm)
    _init_safety_files(gm)
    _init_git_files(gm)
    _init_web_files(gm)
    _init_browser_files(gm)
    _init_github_files(gm)
    _validate_gm_structure(gm)


def _init_readme(gm: Path) -> None:
    path = gm / "README.md"
    if not path.exists():
        atomic_write(
            path,
            "\n".join(
                [
                    "# Galaxy Merge Runtime State",
                    "",
                    "This directory is generated by Galaxy Merge for this project.",
                    "It stores sessions, notes, memory, indexes, caches, browser evidence, safety logs, and git patchsets.",
                    "Do not commit this directory to a public repository.",
                    "",
                ]
            ),
        )


def _init_project_json(gm: Path, workroot: Path) -> None:
    path = gm / "project.json"
    if path.exists():
        _validate_project_json(path)
        return
    data = {
        "schema_version": 1,
        "project_id": "gmproj_" + secrets.token_hex(4),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "workroot": str(workroot),
        "name": workroot.name,
        "language_hints": [],
        "framework_hints": [],
        "git_detected": (workroot / ".git").exists(),
        "default_branch": _detect_default_branch(workroot),
        "notes_enabled": True,
        "memory_enabled": True,
        "index_enabled": True,
        "safety_policy": "default",
    }
    atomic_write(path, json.dumps(data, indent=2))


def _validate_project_json(path: Path) -> list[str]:
    errors = []
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        return [f"invalid JSON: {e}"]
    if data.get("schema_version") != 1:
        errors.append(f"expected schema_version=1, got {data.get('schema_version')}")
    if not data.get("project_id", "").startswith("gmproj_"):
        errors.append("project_id must start with 'gmproj_'")
    if not data.get("workroot"):
        errors.append("workroot is required")
    if not data.get("created_at"):
        errors.append("created_at is required")
    if errors:
        import logging

        for e in errors:
            logging.warning(f"project.json validation: {e}")
    return errors


def _detect_default_branch(workroot: Path) -> str:
    git_dir = workroot / ".git"
    if git_dir.exists():
        try:
            import subprocess

            r = subprocess.run(
                ["git", "symbolic-ref", "--short", "HEAD"],
                cwd=str(workroot),
                capture_output=True,
                text=True,
                timeout=5,
            )
            if r.returncode == 0:
                return r.stdout.strip()
        except Exception:
            pass
    return "main"


def _init_notes_index(gm: Path) -> None:
    index_path = gm / "notes" / "index.json"
    if not index_path.exists():
        atomic_write(
            index_path,
            json.dumps(
                {
                    "schema_version": 1,
                    "notes": [],
                },
                indent=2,
            ),
        )


def _init_safety_files(gm: Path) -> None:
    policy_path = gm / "safety" / "policy.snapshot.json"
    if not policy_path.exists():
        atomic_write(
            policy_path,
            json.dumps(
                {
                    "schema_version": 1,
                    "policy": "default",
                    "active": True,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                },
                indent=2,
            ),
        )
    blocked_path = gm / "safety" / "blocked_actions.jsonl"
    if not blocked_path.exists():
        blocked_path.touch()
    allowed_path = gm / "safety" / "allowed_commands.json"
    if not allowed_path.exists():
        atomic_write(allowed_path, json.dumps({"allowed_commands": []}, indent=2))
    protected_path = gm / "safety" / "protected_paths.json"
    if not protected_path.exists():
        atomic_write(
            protected_path,
            json.dumps(
                {
                    "protected_paths": [
                        str(gm / "safety"),
                        str(gm / "project.json"),
                    ]
                },
                indent=2,
            ),
        )


def _init_git_files(gm: Path) -> None:
    checkpoints_path = gm / "git" / "checkpoints.jsonl"
    if not checkpoints_path.exists():
        checkpoints_path.touch()


def _init_web_files(gm: Path) -> None:
    for name in (
        "searches",
        "fetched_pages",
        "wikipedia",
        "duckduckgo",
        "curl_fetches",
    ):
        p = gm / "web" / f"{name}.jsonl"
        if not p.exists():
            p.touch()


def _init_browser_files(gm: Path) -> None:
    for name in ("console_logs", "network_logs", "page_errors"):
        p = gm / "browser" / f"{name}.jsonl"
        if not p.exists():
            p.touch()


def _init_github_files(gm: Path) -> None:
    p = gm / "github" / "repos.jsonl"
    if not p.exists():
        p.touch()


REQUIRED_GM_SUBDIRS: list[str] = [
    "notes",
    "notes/history",
    "notes/.trash",
    "memory",
    "sessions",
    "indexes",
    "indexes/embeddings",
    "cache/provider",
    "cache/file_summaries",
    "cache/skill_matches",
    "cache/fusion",
    "cache/command_results",
    "cache/web_search",
    "cache/browser_pages",
    "cache/github_scans",
    "web",
    "browser/profiles",
    "browser/sessions",
    "browser/screenshots",
    "locations",
    "github/scans",
    "github/issues",
    "github/pull_requests",
    "logs",
    "safety",
    "git/patchsets",
]

REQUIRED_GM_FILES: list[str] = [
    "project.json",
    "README.md",
    "notes/index.json",
    "safety/policy.snapshot.json",
    "safety/allowed_commands.json",
    "safety/protected_paths.json",
    "web/searches.jsonl",
    "web/fetched_pages.jsonl",
    "web/wikipedia.jsonl",
    "web/duckduckgo.jsonl",
    "web/curl_fetches.jsonl",
    "browser/console_logs.jsonl",
    "browser/network_logs.jsonl",
    "browser/page_errors.jsonl",
    "github/repos.jsonl",
    "git/checkpoints.jsonl",
]


def _validate_gm_structure(gm: Path) -> list[str]:
    """Check that all required .gm/ subdirs and files exist. Return warning list."""
    import logging

    warnings: list[str] = []

    for sub in REQUIRED_GM_SUBDIRS:
        p = gm / sub
        if not p.is_dir():
            warnings.append(f"missing .gm/ subdirectory: {sub}")

    for fname in REQUIRED_GM_FILES:
        p = gm / fname
        if not p.exists():
            warnings.append(f"missing .gm/ file: {fname}")
        elif fname == "project.json":
            _validate_project_json(p)

    if warnings:
        for w in warnings:
            logging.warning(f"gm structure: {w}")

    return warnings


def validate_gm_structure(gm: Path) -> dict[str, Any]:
    """Public .gm/ structure validation.

    Returns a dict with ``ok`` (bool) and ``warnings`` (list[str]).
    Safe to call on a partially-created or empty ``.gm`` directory; never
    raises. Use this from boot, the health endpoint, or tests.
    """
    result: dict[str, Any] = {"ok": True, "warnings": [], "checked_at": None}
    if not gm.exists():
        result["ok"] = False
        result["warnings"].append(f".gm directory missing: {gm}")
        return result
    warnings = _validate_gm_structure(gm)
    if warnings:
        result["ok"] = False
        result["warnings"].extend(warnings)
    from datetime import datetime, timezone

    result["checked_at"] = datetime.now(timezone.utc).isoformat()
    return result
