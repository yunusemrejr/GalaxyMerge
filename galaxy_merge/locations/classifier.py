from pathlib import Path
from typing import Any

from galaxy_merge.safety.command_inspector import first_remote_mutation
from galaxy_merge.safety.path_utils import is_relative_to

LOCATION_CLASSES = [
    "local_workroot",
    "local_taskscope",
    "local_gm_project_state",
    "local_temp",
    "local_user_home",
    "local_system",
    "galaxy_merge_app_codebase",
    "galaxy_merge_app_config",
    "galaxy_merge_runtime",
    "git_local",
    "git_remote",
    "ssh_remote",
    "ftp_remote",
    "sftp_remote",
    "http_external",
    "browser_profile_temp",
    "staging_target",
    "production_target",
    "unknown",
]

REMOTE_COMMAND_PATTERNS = [
    "git push",
    "ssh ",
    "scp ",
    "sftp ",
    "ftp ",
    "lftp ",
    "rsync ",
    "rclone ",
    "kubectl ",
    "docker context",
    "docker compose --context",
    "ssh-copy-id ",
    "ansible",
    "terraform apply",
    "pulumi up",
    "aws ",
    "gcloud ",
    "az ",
    "netlify deploy",
    "vercel deploy",
    "firebase deploy",
]


class LocationClassifier:
    def __init__(self, workroot: Path, gm_dir: Path, install_dir: Path | None = None):
        self.workroot = workroot.resolve()
        self.gm_dir = gm_dir.resolve()
        self.install_dir = install_dir.resolve() if install_dir else None
        self.home = Path.home().resolve()

    def classify_path(self, path: str | Path) -> str:
        resolved = Path(path).resolve()
        resolved_str = str(resolved)

        if self.install_dir and is_relative_to(resolved, self.install_dir):
            return "galaxy_merge_app_codebase"

        if is_relative_to(resolved, self.gm_dir):
            return "local_gm_project_state"

        if is_relative_to(resolved, self.workroot):
            return "local_workroot"

        home_str = str(self.home)
        if resolved_str.startswith(home_str):
            if resolved_str == home_str or resolved_str.count("/") <= home_str.count("/") + 1:
                return "local_user_home"
            rest = resolved_str[len(home_str):].strip("/")
            if rest.startswith(".config/galaxy-merge"):
                return "galaxy_merge_app_config"
            return "local_user_home"

        if resolved_str.startswith("/tmp"):
            return "local_temp"

        system_prefixes = ["/bin", "/sbin", "/usr", "/etc", "/var", "/boot", "/dev", "/proc", "/sys", "/run", "/root"]
        for p in system_prefixes:
            if resolved_str.startswith(p):
                return "local_system"

        return "unknown"

    def _classify_remote_type(self, cmd_lower: str, pattern: str) -> str:
        """Map matched patterns to their location class."""
        if "production" in cmd_lower or "prod" in cmd_lower:
            return "production_target"
        if pattern.startswith("git"):
            return "git_remote"
        if pattern.startswith("ssh"):
            return "ssh_remote"
        if pattern.startswith("sftp"):
            return "sftp_remote"
        if pattern.startswith("ftp") or pattern.startswith("lftp"):
            return "ftp_remote"
        if pattern.startswith("scp"):
            return "ssh_remote"
        if pattern.startswith("rsync") or pattern.startswith("rclone"):
            return "ssh_remote"
        if pattern.startswith("kubectl"):
            return "ssh_remote"
        if pattern.startswith("docker"):
            return "ssh_remote"
        if pattern.startswith("ansible"):
            return "ssh_remote"
        if pattern.startswith("terraform") or pattern.startswith("pulumi"):
            return "production_target"
        if pattern.startswith("aws") or pattern.startswith("gcloud") or pattern.startswith("az"):
            return "production_target"
        if "deploy" in pattern:
            return "production_target"
        return "ssh_remote"

    def classify_command(self, command: str) -> str:
        cmd_lower = command.strip().lower()
        inspected = first_remote_mutation(command)
        if inspected:
            return inspected.location_class
        for pattern in REMOTE_COMMAND_PATTERNS:
            if cmd_lower.startswith(pattern.lower()):
                return self._classify_remote_type(cmd_lower, pattern)
        return "local_workroot"

    def is_remote_mutation(self, command: str) -> bool:
        cls = self.classify_command(command)
        return cls in ("git_remote", "ssh_remote", "ftp_remote", "sftp_remote", "production_target", "staging_target")

    def is_production(self, command: str) -> bool:
        cls = self.classify_command(command)
        return cls == "production_target"

    def classify(self, target: str, target_type: str = "path") -> dict[str, Any]:
        if target_type == "path":
            cls = self.classify_path(target)
        else:
            cls = self.classify_command(target)

        inspected = first_remote_mutation(target) if target_type != "path" else None
        return {
            "target": target,
            "classification": cls,
            "is_remote": cls in ("git_remote", "ssh_remote", "ftp_remote", "sftp_remote", "production_target", "staging_target"),
            "is_production": cls == "production_target",
            "is_local": cls.startswith("local_"),
            "host": inspected.host if inspected else "",
            "path": inspected.path if inspected else (target if target_type == "path" else ""),
            "repo": inspected.repo if inspected else "",
            "risk": inspected.risk if inspected else ("high" if cls in ("local_system", "production_target") else "low"),
            "policy_decision": "blocked_by_default" if cls in ("git_remote", "ssh_remote", "ftp_remote", "sftp_remote", "production_target", "staging_target") else "allowed_by_default",
        }
