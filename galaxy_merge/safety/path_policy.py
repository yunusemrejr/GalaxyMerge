from pathlib import Path
from typing import Any

from galaxy_merge.safety.path_utils import is_relative_to

BLOCKED_WRITE_PATHS: list[Path] = [
    Path("/bin"),
    Path("/sbin"),
    Path("/usr"),
    Path("/etc"),
    Path("/var"),
    Path("/boot"),
    Path("/dev"),
    Path("/proc"),
    Path("/sys"),
    Path("/run"),
    Path("/root"),
    Path("/opt"),
    Path("/lib"),
    Path("/lib64"),
]

BLOCKED_USER_PATTERNS: list[str] = [
    ".ssh",
    ".gnupg",
    ".aws",
    ".config",
    ".local/bin",
    ".bashrc",
    ".profile",
    ".zshrc",
    ".npmrc",
    ".pypirc",
    ".docker",
    ".gitconfig",
    ".netrc",
    ".env",
    ".env.local",
    ".env.production",
    ".env.development",
]

GIT_HOOK_PATTERNS: list[str] = [
    ".git/hooks/",
    ".git/config",
]

CREDENTIAL_CHECK_PATTERNS: list[str] = [
    ".env",
    ".env.local",
    ".env.production",
    ".env.development",
    ".env.staging",
    "credentials.json",
    "credentials.yaml",
    "credentials.yml",
    "token.json",
    "tokens.json",
    ".ssh/",
    ".aws/",
    ".gnupg/",
    ".docker/",
    "id_rsa",
    "id_ed25519",
    "id_ecdsa",
    ".pem",
    ".key",
    ".npmrc",
    ".pypirc",
    ".netrc",
    ".gitconfig",
    "service-account-key",
]

UNSAFE_SYMLINK_WARNING = "write path resolves via symlink to a different location"


class PathPolicy:
    def __init__(self, workroot: Path):
        self.workroot = workroot.resolve()
        self.home = Path.home().resolve()
        self._symlink_cache: dict[Path, Path] = {}

    def _check_git_hooks(self, resolved_str: str) -> dict[str, Any] | None:
        for pattern in GIT_HOOK_PATTERNS:
            if pattern in resolved_str:
                return {
                    "decision": "block",
                    "reason": f"write to git hooks/config blocked: {pattern}",
                }
        return None

    def _check_credential_path(self, resolved_str: str) -> dict[str, Any] | None:
        path_lower = resolved_str.lower()
        for part in CREDENTIAL_CHECK_PATTERNS:
            if part in path_lower:
                return {
                    "decision": "block",
                    "reason": f"credential file path blocked: {part}",
                }
        return None

    def check_write(self, path: Path) -> dict[str, Any]:
        resolved = path.resolve()
        resolved_str = str(resolved)

        if resolved != path:
            real_path_str = str(resolved)
            for blocked in BLOCKED_WRITE_PATHS:
                if is_relative_to(resolved, blocked):
                    return {
                        "decision": "block",
                        "reason": f"symlink escape blocked: {path} resolves to {real_path_str}",
                    }

        for blocked in BLOCKED_WRITE_PATHS:
            if is_relative_to(resolved, blocked):
                return {
                    "decision": "block",
                    "reason": f"write to system path blocked: {blocked}",
                }

        if is_relative_to(resolved, self.home):
            relative = str(resolved.relative_to(self.home))
            for pattern in BLOCKED_USER_PATTERNS:
                if (
                    relative == pattern
                    or relative.startswith(pattern + "/")
                    or f"/{pattern}" in relative
                ):
                    return {
                        "decision": "block",
                        "reason": f"write to protected user path blocked: {pattern}",
                    }

        git_result = self._check_git_hooks(resolved_str)
        if git_result:
            return git_result

        if not is_relative_to(resolved, self.workroot):
            return {
                "decision": "block",
                "reason": f"write outside WorkRoot blocked: {path}",
            }

        if resolved != path:
            return {
                "decision": "allow_with_audit",
                "reason": "write via symlink, real path verified safe",
            }

        return {"decision": "allow", "reason": "path inside WorkRoot"}

    def check_read(self, path: Path) -> dict[str, Any]:
        resolved = path.resolve()
        resolved_str = str(resolved)
        cred_result = self._check_credential_path(resolved_str)
        if cred_result:
            return cred_result
        return {"decision": "allow", "reason": "read permitted"}
