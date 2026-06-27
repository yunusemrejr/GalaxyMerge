#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if command -v gitleaks >/dev/null 2>&1; then
    exec gitleaks detect --no-banner --redact --source "$ROOT_DIR"
fi

if command -v trufflehog >/dev/null 2>&1; then
    exec trufflehog filesystem --no-update --fail "$ROOT_DIR"
fi

SECRET_RE='(-----BEGIN (RSA |OPENSSH |EC |DSA )?PRIVATE KEY-----|sk-(proj-)?[A-Za-z0-9_-]{40,}|ghp_[A-Za-z0-9_]{36,}|github_pat_[A-Za-z0-9_]{40,}|xox[baprs]-[A-Za-z0-9-]{40,}|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{30,}|npm_[A-Za-z0-9]{30,}|Bearer[[:space:]][A-Za-z0-9._-]{40,}|(api[_-]?key|secret|token|password)[[:space:]]*[:=][[:space:]]*["'\''][^"'\'']{20,}["'\''])'
PLACEHOLDER_RE='(EXAMPLE|example|test|fake|placeholder|1234567890abcdef|abc123|def456|hunter2|my_super_secret|sk-xxxx|MIIEpQIBAAKCAQEA|ABCDEFG|b3BlbnNzaC1rZXktdjE|GM_EXAMPLE_PROVIDER_API_KEY|self\.api_key|\{self\.api_key\}|os\.environ\.get)'
FORBIDDEN_PATH_RE='(^|/)(\.env($|\.)|providers\.json$|models\.json$|routing\.json$|fusion\.json$|remote-targets\.json$|.*secret.*\.json$|.*credential.*\.json$|.*endpoint.*\.json$)'

failed=0

while IFS= read -r path; do
    [ -n "$path" ] || continue
    [ -f "$path" ] || continue
    if [[ "$path" != ".env.example" && "$path" =~ $FORBIDDEN_PATH_RE ]]; then
        echo "forbidden public candidate path: $path" >&2
        failed=1
        continue
    fi
    if grep -Iq . "$path" && grep -Ei "$SECRET_RE" "$path" | grep -Eiv "$PLACEHOLDER_RE" >/dev/null; then
        echo "secret-like value in public candidate path: $path" >&2
        failed=1
    fi
done < <(git ls-files --cached --others --exclude-standard)

if [ "${1:-}" = "--history" ] && git rev-parse --verify HEAD >/dev/null 2>&1; then
    mapfile -t commits < <(git rev-list --all)
    if [ "${#commits[@]}" -gt 0 ]; then
        if git grep -IE "$SECRET_RE" "${commits[@]}" -- ':!uv.lock' \
            | grep -Eiv "$PLACEHOLDER_RE" \
            | cut -d: -f1-2 \
            | sort -u >/tmp/gm-secret-history-findings.txt 2>/dev/null; then
            echo "secret-like value found in git history:" >&2
            sed -n '1,80p' /tmp/gm-secret-history-findings.txt >&2
            failed=1
        fi
    fi
fi

if [ "$failed" -ne 0 ]; then
    exit 1
fi

echo "Secret scan passed with fallback scanner."
