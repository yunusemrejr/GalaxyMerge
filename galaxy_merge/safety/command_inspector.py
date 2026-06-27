import os
import re
import shlex
from dataclasses import dataclass
from pathlib import Path


REMOTE_CLASSES = {
    "ssh": "ssh_remote",
    "scp": "ssh_remote",
    "rsync": "ssh_remote",
    "rclone": "ssh_remote",
    "kubectl": "ssh_remote",
    "docker": "ssh_remote",
    "ansible": "ssh_remote",
    "sftp": "sftp_remote",
    "ftp": "ftp_remote",
    "lftp": "ftp_remote",
    "terraform": "production_target",
    "pulumi": "production_target",
    "aws": "production_target",
    "gcloud": "production_target",
    "az": "production_target",
    "netlify": "production_target",
    "vercel": "production_target",
    "firebase": "production_target",
}

SHELL_WRAPPERS = {"sh", "bash", "zsh", "fish"}
OPERATORS = {";", "&&", "||", "|", "&"}
PROTECTED_REDIRECT_RE = re.compile(r"(?:^|\s)(?:>|>>)\s*(/|~|\$[A-Za-z_][A-Za-z0-9_]*)")


@dataclass(frozen=True, slots=True)
class CommandInspection:
    location_class: str
    reason: str
    risk: str
    host: str
    path: str
    repo: str


def split_tokens(command: str) -> list[str]:
    lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|<>")
    lexer.whitespace_split = True
    return list(lexer)


def first_remote_mutation(command: str) -> CommandInspection | None:
    try:
        tokens = split_tokens(command)
    except ValueError:
        return CommandInspection("unknown", "unparseable shell command", "high", "", "", "")
    return _inspect_tokens(tokens)


def has_protected_redirect(command: str) -> bool:
    return bool(PROTECTED_REDIRECT_RE.search(command))


def _inspect_tokens(tokens: list[str]) -> CommandInspection | None:
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token in OPERATORS or token in {">", ">>", "<", "<<"}:
            index += 1
            continue

        command = os.path.basename(token).lower()
        if command == "env":
            env_result = _inspect_env(tokens[index + 1 :])
            if env_result:
                return env_result
            index += 1
            continue

        if "=" in token and not token.startswith("-"):
            index += 1
            continue

        if command in SHELL_WRAPPERS:
            shell_result = _inspect_shell_wrapper(tokens[index + 1 :])
            if shell_result:
                return shell_result

        result = _inspect_command_at(tokens, index, command)
        if result:
            return result
        index += 1
    return None


def _inspect_env(tokens: list[str]) -> CommandInspection | None:
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token in OPERATORS:
            return _inspect_tokens(tokens[index + 1 :])
        if "=" in token and not token.startswith("-"):
            if token.upper().startswith(("GIT_DIR=", "GIT_WORK_TREE=", "SSH_AUTH_SOCK=")):
                return CommandInspection("git_remote", "environment can redirect git/ssh context", "high", "", "", "")
            index += 1
            continue
        return _inspect_tokens(tokens[index:])
    return None


def _inspect_shell_wrapper(tokens: list[str]) -> CommandInspection | None:
    for index, token in enumerate(tokens):
        if token == "-c" and index + 1 < len(tokens):
            return first_remote_mutation(tokens[index + 1])
        if token.startswith("-c") and len(token) > 2:
            return first_remote_mutation(token[2:])
    return None


def _inspect_command_at(tokens: list[str], index: int, command: str) -> CommandInspection | None:
    tail = tokens[index + 1 :]
    if command == "git" and "push" in tail:
        return CommandInspection("git_remote", "git push targets a remote repository", "high", "", "", _git_repo_hint(tail))
    if command in REMOTE_CLASSES:
        location_class = _remote_class_for(command, tail)
        return CommandInspection(location_class, f"{command} targets a remote or deployment surface", "high", _host_hint(tail), _path_hint(tail), "")
    return None


def _remote_class_for(command: str, tail: list[str]) -> str:
    joined = " ".join(tail).lower()
    if "production" in joined or "prod" in joined:
        return "production_target"
    if "staging" in joined or "stage" in joined:
        return "staging_target"
    return REMOTE_CLASSES[command]


def _host_hint(tokens: list[str]) -> str:
    for token in tokens:
        if "@" in token or "://" in token:
            return token.split(":", 1)[0]
    return ""


def _path_hint(tokens: list[str]) -> str:
    for token in reversed(tokens):
        expanded = token.replace("'", "").replace('"', "")
        if expanded.startswith("/") or ":/" in expanded or expanded.startswith("s3://"):
            return expanded
    return ""


def _git_repo_hint(tokens: list[str]) -> str:
    for token in tokens:
        if token.startswith(("http://", "https://", "git@", "ssh://")):
            return token
    return ""
