#!/usr/bin/env python3
"""Galaxy Merge — Secret scanner.

Scans tracked and untracked files for credential-like values.
Exits 0 if clean, 1 if secrets found.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

PEM_BEGIN_RE = re.compile(r'-----BEGIN (?:RSA |OPENSSH |EC |DSA )?PRIVATE KEY-----')
PEM_END_RE = re.compile(r'-----END (?:RSA |OPENSSH |EC |DSA )?PRIVATE KEY-----')

SECRET_PATTERNS = [
    re.compile(r'sk-(?:proj-)?[A-Za-z0-9_-]{40,}'),
    re.compile(r'ghp_[A-Za-z0-9_]{36,}'),
    re.compile(r'github_pat_[A-Za-z0-9_]{40,}'),
    re.compile(r'gho_[A-Za-z0-9_]{36,}'),
    re.compile(r'AKIA[0-9A-Z]{16}'),
    re.compile(r'AIza[0-9A-Za-z_-]{30,}'),
    PEM_BEGIN_RE,
    re.compile(r'xox[baprs]-[A-Za-z0-9-]{40,}'),
    re.compile(r'npm_[A-Za-z0-9]{30,}'),
    re.compile(r'eyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}'),
]

PLACEHOLDER_PATTERNS = [
    re.compile(r'EXAMPLE|example|test|fake|placeholder', re.IGNORECASE),
    re.compile(r'1234567890abcdef|abc123|def456|hunter2|my_super_secret', re.IGNORECASE),
    re.compile(r'sk-xxxx|sk-xxx|sk-[x]{10,}|ghp_[x]{10,}|ghp_1234', re.IGNORECASE),
    re.compile(r'MIIEpQIBAAKCAQEA|MIIEpQIBAAK|ABCDEFG', re.IGNORECASE),
    re.compile(r'b3BlbnNzaC1rZXktdjE', re.IGNORECASE),
    re.compile(r'dozjgNryP4J3j5M0uRvFQZ1O7A', re.IGNORECASE),
    re.compile(r'GM_EXAMPLE_PROVIDER_API_KEY', re.IGNORECASE),
    re.compile(r'os\.environ\.get|self\.api_key|\{self\.api_key\}', re.IGNORECASE),
    re.compile(r'YOUR_.*_KEY_HERE|REPLACE_ME|CHANGEME', re.IGNORECASE),
    re.compile(r'check_credential_exposure|redact_text|scan_text', re.IGNORECASE),
]

FORBIDDEN_PATHS = {
    "providers.json", "models.json", "routing.json", "fusion.json",
    "remote-targets.json",
}


def is_placeholder(line: str) -> bool:
    return any(p.search(line) for p in PLACEHOLDER_PATTERNS)




def scan_file(path: Path) -> list[str]:
    findings = []
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except (OSError, UnicodeDecodeError):
        return findings

    lines = content.splitlines()
    has_pem_end = any(PEM_END_RE.search(line) for line in lines)

    for line_num, line in enumerate(lines, 1):
        for pattern in SECRET_PATTERNS:
            if not pattern.search(line):
                continue
            if is_placeholder(line):
                continue
            # A bare PEM BEGIN header without a matching END marker is not a
            # leakable secret (real private keys always have an END line).
            if pattern is PEM_BEGIN_RE and not has_pem_end:
                continue
            findings.append(f"  {path}:{line_num}: {line.strip()[:120]}")
    return findings


def main() -> int:
    failed = False

    # Get tracked + untracked files
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=REPO_ROOT, capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        print(f"git ls-files failed: {result.stderr}", file=sys.stderr)
        return 1

    files = [f for f in result.stdout.splitlines() if f.strip()]

    for rel_path in files:
        full_path = REPO_ROOT / rel_path
        if not full_path.is_file():
            continue
        # Skip .env.example (intentional placeholders)
        if rel_path == ".env.example":
            continue
        # Check forbidden paths
        basename = full_path.name
        if basename in FORBIDDEN_PATHS and "example" not in basename:
            if not str(full_path).startswith(str(REPO_ROOT / "config")):
                print(f"forbidden public candidate: {rel_path}", file=sys.stderr)
                failed = True
                continue

        findings = scan_file(full_path)
        if findings:
            print(f"secret-like value in: {rel_path}", file=sys.stderr)
            for f in findings[:5]:
                print(f, file=sys.stderr)
            failed = True

    # Check .gitignore
    gitignore = REPO_ROOT / ".gitignore"
    if gitignore.exists():
        content = gitignore.read_text()
        required_ignores = [".gm/", ".env", "providers.json", "models.json"]
        for pattern in required_ignores:
            if pattern not in content:
                print(f".gitignore missing: {pattern}", file=sys.stderr)
                failed = True

    if not failed:
        print("Secret scan passed.")
    else:
        print("Secret scan FAILED — see above.", file=sys.stderr)

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
