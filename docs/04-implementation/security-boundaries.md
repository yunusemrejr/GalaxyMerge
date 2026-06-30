# Security Boundaries

## Trust Boundaries

### 1. WorkRoot Boundary
All file operations are confined to the resolved WorkRoot. `PathPolicy.check_write()` rejects any write outside WorkRoot. Symlink escapes are detected.

### 2. System Path Boundary
Writes to `/bin`, `/usr`, `/etc`, `/var`, `/boot`, `/dev`, `/proc`, `/sys`, `/run`, `/root`, `/opt`, `/lib` are always blocked.

### 3. User Credential Boundary
Writes to `.ssh`, `.gnupg`, `.aws`, `.config`, `.env`, `.npmrc`, `.pypirc`, `.docker`, `.gitconfig`, `.netrc` are blocked.

### 4. Self-Protection Boundary
When WorkRoot is inside the Galaxy Merge source tree, all mutations are blocked. Read-only diagnostic mode.

### 5. Network Boundary
Server binds to `127.0.0.1` only. No external network exposure. All provider calls are outbound-only.

### 6. Git History Boundary
Git hooks and config (`.git/hooks/`, `.git/config`) are protected from writes.

## Secrets Handling

### Environment Variables
Provider API keys are read from environment variables only. Never from config files. Never committed.

### Redaction
`CredentialPolicy.redact(text)` scans and replaces:
- API key patterns (sk-*, sk-ant-*, ghp_*, etc.)
- Bearer tokens
- Base64-encoded credentials
- Known env var values

Redaction is applied at:
- Event log emission
- API response serialization
- Provider error messages
- Tool result data

### Public Repository Hygiene
- `.gm/` in `.gitignore` — never committed
- `.env` in `.gitignore` — never committed
- `providers.json` in `.gitignore` — never committed
- Config examples use placeholders only
- Secret scan scripts (`scripts/secret_scan.sh`, `scripts/secret_scan.py`)
- CI runs secret scan on every push

## Command Injection Prevention

- Shell metacharacters detected and blocked (unless in safe-list)
- `curl|sh`, `wget|bash` patterns blocked
- Environment variable injection patterns blocked (`LD_PRELOAD`, `PYTHONPATH`, etc.)
- Dangerous code execution patterns blocked (`python -c os.system`, `node -e child_process`)
- `sudo` always blocked
- Remote mutation patterns require deployment policy

## Path Traversal Prevention

- `resolve_inside(base, path)` validates resolved path is inside base
- Symlink resolution before write permission check
- `is_relative_to()` used for all containment checks
