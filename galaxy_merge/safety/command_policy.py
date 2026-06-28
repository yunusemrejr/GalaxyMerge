import os
import re
from pathlib import Path
from typing import Any

from galaxy_merge.safety.command_inspector import (
    first_remote_mutation,
    has_protected_redirect,
)

BLOCKED_COMMANDS: list[str] = [
    "sudo rm",
    "sudo mv",
    "sudo cp",
    "sudo chmod",
    "sudo chown",
    "chmod -R 777",
    "chown -R",
    "mkfs",
    "mount",
    "umount",
    "mkswap",
    "swapon",
    "swapoff",
    "fdisk",
    "parted",
]

SYSTEM_PATHS = [
    "/",
    "/bin",
    "/sbin",
    "/usr",
    "/etc",
    "/var",
    "/boot",
    "/dev",
    "/proc",
    "/sys",
    "/run",
    "/root",
    "/opt",
    "/lib",
]

REMOTE_MUTATION_PATTERNS: list[str] = [
    "git push",
    "ssh ",
    "ssh-copy-id",
    "scp ",
    "sftp ",
    "ftp ",
    "lftp ",
    "rsync ",
    "rclone ",
    "kubectl ",
    "docker context",
    "docker compose --context",
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

BLOCKED_BINARY_PATHS: list[str] = ["/sbin/", "/usr/sbin/", "/usr/local/sbin/"]

SHELL_METACHARACTERS = re.compile(r"[;|&$`(){}<>]")

ENV_INJECTION_PATTERNS: list[str] = [
    r"^LD_PRELOAD=",
    r"^LD_LIBRARY_PATH=",
    r"^LD_AUDIT=",
    r"^LD_DEBUG=",
    r"^LD_ORIGIN_PATH=",
    r"^LIBRARY_PATH=",
    r"^PYTHONPATH=",
    r"^NODE_PATH=",
    r"^BASH_ENV=",
    r"^ENV=",
    r"^BASH_FUNC_",
    r"^IFS=",
    r"^GIT_DIR=",
    r"^SSH_ORIGINAL_COMMAND=",
    r"^PERL5LIB=",
    r"^RUBYLIB=",
    r"^RUBYOPT=",
    r"^PYTHONSTARTUP=",
    r"^PYTHONWARNINGS=",
    r"^TMPDIR=",
    r"^TEMPDIR=",
]

NUKE_PIPE_PATTERNS: list[str] = [
    "curl",
    "wget",
    "fetch",
    "httpie",
]

DIRECT_DOWNLOAD_KILL_SWITCHES: list[str] = [
    "| sh",
    "| bash",
    "| zsh",
    "| fish",
    "| python",
    "| python3",
    "| node",
    "| perl",
    "| ruby",
]

DANGEROUS_CODE_PATTERNS = [
    r"python[\d.]*\s+-c\s+['\"].*os\.system\s*\(",
    r"python[\d.]*\s+-c\s+['\"].*subprocess\..*run\s*\(",
    r"python[\d.]*\s+-c\s+['\"].*subprocess\..*check_call\s*\(",
    r"python[\d.]*\s+-c\s+['\"].*subprocess\..*call\s*\(",
    r"python[\d.]*\s+-c\s+['\"].*subprocess\..*Popen\s*\(",
    r"python[\d.]*\s+-c\s+['\"].*exec\s*\(",
    r"node\s+-e\s+['\"].*child_process",
    r"node\s+-e\s+['\"].*exec(?:Sync)?\s*\(",
    r"node\s+-e\s+['\"].*spawn\s*\(",
]


def _first_word_basename(command: str) -> str:
    """Extract the basename of the first word (handles /usr/bin/git -> git)."""
    words = command.strip().split()
    if not words:
        return ""
    return os.path.basename(words[0])


def _normalize_first_word(command: str) -> str:
    """Replace first word with its basename, preserving rest of command."""
    words = command.strip().split()
    if not words:
        return ""
    basename = os.path.basename(words[0])
    rest = " ".join(words[1:])
    return (basename + " " + rest).strip()


def _find_rm_target(command: str) -> str | None:
    """Extract the target path from an rm command, skipping flags."""
    parts = command.split()
    for i, part in enumerate(parts):
        if os.path.basename(part) == "rm":
            for j in range(i + 1, len(parts)):
                if parts[j] == "--":
                    continue
                if not parts[j].startswith("-"):
                    return parts[j]
    return None


def _has_recursive_flag(parts: list[str], start: int) -> bool:
    """Check if there's a recursive flag (-r, -R) in parts starting at start."""
    for j in range(start, len(parts)):
        p = parts[j]
        if not p.startswith("-"):
            return False
        if p == "--":
            continue
        if p.startswith("--"):
            if p in ("--recursive",):
                return True
            continue
        if "r" in p or "R" in p:
            return True
    return False


def _contains_rm_rf_system_path(command: str) -> bool:
    parts = command.split()
    for i, part in enumerate(parts):
        if os.path.basename(part) == "rm":
            has_recursive = _has_recursive_flag(parts, i + 1)
            target = _find_rm_target(command)
            if has_recursive and target:
                for sp in SYSTEM_PATHS:
                    if target == sp or target.startswith(sp + "/"):
                        return True
    return False


def _dd_target_targets_system(value: str) -> bool:
    target = value
    for sp in SYSTEM_PATHS:
        if target == sp or target.startswith(sp + "/"):
            return True
    return False


def _contains_destructive_dd(command: str) -> bool:
    """Block ``dd`` whenever either ``of=`` or ``if=`` targets a system path.

    Reading raw system devices is at minimum data exfiltration and at worst
    destructive (writing the read data back over a system device), so the
    check fires regardless of which side of the pipeline is the system path.
    """
    parts = command.split()
    if not parts:
        return False
    if os.path.basename(parts[0]) not in ("dd",):
        return False
    for part in parts[1:]:
        if part.startswith("of=") and _dd_target_targets_system(part[3:]):
            return True
        if part.startswith("if=") and _dd_target_targets_system(part[3:]):
            return True
    return False


def _contains_any_sudo(command: str) -> bool:
    return bool(re.search(r"(^|[;&|`$()\s])sudo\s", command, re.IGNORECASE))


def _contains_destructive_chmod(command: str) -> bool:
    if re.search(r"chmod\s+(-R\s+)?\d{3,4}\s+/", command):
        return True
    return False


def _contains_destructive_chown(command: str) -> bool:
    if re.search(r"chown\s+(-R\s+)?\w+:\w+\s+/", command):
        return True
    return False


def _contains_nuke_pipe(command: str) -> bool:
    """Detect curl|sh, wget|bash etc. — pipe from download to shell."""
    command_lower = command.lower()
    has_downloader = any(dp in command_lower for dp in NUKE_PIPE_PATTERNS)
    if not has_downloader:
        return False
    for switch in DIRECT_DOWNLOAD_KILL_SWITCHES:
        if switch in command_lower:
            return True
    return False


def _contains_dangerous_code(command: str) -> bool:
    for pat in DANGEROUS_CODE_PATTERNS:
        if re.search(pat, command):
            return True
    return False


def _command_targets_system_via_trash(command: str) -> bool:
    parts = command.split()
    if not parts:
        return False
    if os.path.basename(parts[0]) not in ("trash",):
        return False
    for part in parts[1:]:
        if part.startswith("-"):
            continue
        resolved = Path(part).expanduser().resolve()
        resolved_str = str(resolved)
        for sp in SYSTEM_PATHS:
            if resolved_str == sp or resolved_str.startswith(sp + "/"):
                return True
        home = Path.home().resolve()
        home_str = str(home)
        if resolved_str.startswith(home_str):
            relative = resolved_str[len(home_str) :].strip("/")
            blocked_patterns = [
                ".ssh",
                ".gnupg",
                ".aws",
                ".config",
                ".local/bin",
                ".docker",
                ".gitconfig",
                ".netrc",
                ".env",
                ".npmrc",
                ".pypirc",
            ]
            for pattern in blocked_patterns:
                if (
                    relative == pattern
                    or relative.startswith(pattern + "/")
                    or "/" + pattern in relative
                ):
                    return True
    return False


RM_RF_CRITICAL_PATTERNS = [
    "rm -rf /",
    "rm -rf ~",
    "rm -rf /home",
    "rm -rf /usr",
    "rm -rf /etc",
    "rm -rf /var",
    "rm -rf /boot",
    "rm -rf /opt",
    "rm -rf /root",
    "rm -rf /lib",
    "rm -rf /bin",
    "rm -rf /sbin",
]


def _contains_rm_rf_substring(command: str) -> bool:
    for pat in RM_RF_CRITICAL_PATTERNS:
        if pat in command:
            return True
    return False


class CommandPolicy:
    def __init__(self, workroot: Path):
        self.workroot = workroot.resolve()

    def check(self, command: str) -> dict[str, Any]:
        stripped = command.strip()
        if not stripped:
            return {"decision": "block", "reason": "empty command"}

        if _contains_rm_rf_substring(stripped):
            return {
                "decision": "block",
                "reason": "rm -rf targeting critical path detected",
            }

        if _contains_rm_rf_system_path(stripped):
            return {
                "decision": "block",
                "reason": "rm targeting system path with recursive flag detected",
            }

        if _contains_destructive_dd(stripped):
            return {"decision": "block", "reason": "dd targeting system path"}

        if _contains_any_sudo(stripped):
            return {"decision": "block", "reason": "sudo detected in command"}

        remote_result = first_remote_mutation(stripped)
        if remote_result:
            return {
                "decision": "allow_with_audit",
                "reason": f"remote mutation pattern: {remote_result.reason} — requires deployment policy",
            }

        if _contains_nuke_pipe(stripped):
            return {
                "decision": "block",
                "reason": "download-to-shell pipe blocked (curl|sh etc.)",
            }

        if _contains_dangerous_code(stripped):
            return {
                "decision": "block",
                "reason": "dangerous code execution pattern detected",
            }

        for env_pat in ENV_INJECTION_PATTERNS:
            if re.search(env_pat, stripped):
                return {
                    "decision": "block",
                    "reason": f"environment variable injection blocked: {env_pat}",
                }

        if _command_targets_system_via_trash(stripped):
            return {"decision": "block", "reason": "trash targeting system path"}

        if _contains_destructive_chmod(stripped):
            return {"decision": "block", "reason": "destructive chmod on system path"}

        if _contains_destructive_chown(stripped):
            return {"decision": "block", "reason": "destructive chown on system path"}

        if has_protected_redirect(stripped):
            return {
                "decision": "block",
                "reason": "redirect to protected path or shell-expanded path blocked",
            }

        for blocked in BLOCKED_COMMANDS:
            if stripped.startswith(blocked):
                return {
                    "decision": "block",
                    "reason": f"blocked command pattern: {blocked}",
                }

        for bp in BLOCKED_BINARY_PATHS:
            if stripped.startswith(bp):
                return {"decision": "block", "reason": f"blocked binary path: {bp}"}

        if SHELL_METACHARACTERS.search(stripped):
            known_safe_with_meta = {
                "echo",
                "printf",
                "test",
                "[",
                "rg",
                "grep",
                "sed",
                "awk",
                "diff",
                "cat",
                "head",
                "tail",
                "sort",
                "uniq",
                "wc",
                "cut",
                "tr",
                "find",
                "xargs",
                "git log",
                "git diff",
                "git show",
                "python3",
                "python",
                "node",
                "tsc",
                "eslint",
                "ruff",
                "pytest",
                "cargo",
                "go",
            }
            is_known_safe = any(stripped.startswith(s) for s in known_safe_with_meta)

            if not is_known_safe:
                return {
                    "decision": "block",
                    "reason": f"shell metacharacters detected and command is not in safe-list: {stripped[:80]}",
                }

        normalized = _normalize_first_word(stripped)
        for remote in REMOTE_MUTATION_PATTERNS:
            if normalized.startswith(remote):
                return {
                    "decision": "allow_with_audit",
                    "reason": f"remote mutation pattern: {remote} — requires deployment policy",
                }

        return {"decision": "allow", "reason": "command permitted"}
