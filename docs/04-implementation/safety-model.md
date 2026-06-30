# Safety Model

## Safety Governor (`safety/governor.py`)

Central safety enforcement point. Composes four policies:

```python
class SafetyGovernor:
    path_policy = PathPolicy(workroot)
    command_policy = CommandPolicy(workroot)
    self_protection = SelfProtectionPolicy(workroot, gm_dir)
    credential_policy = CredentialPolicy(workroot)
```

### Check Methods

- `check_path_write(path)` → self_protection → credential_policy → path_policy
- `check_path_read(path)` → credential_policy
- `check_command(command)` → self_protection → command_policy
- `check_credential_exposure(text)` → credential_policy.scan_text

## Path Policy (`safety/path_policy.py`)

### Blocked Write Paths
`/bin`, `/sbin`, `/usr`, `/etc`, `/var`, `/boot`, `/dev`, `/proc`, `/sys`, `/run`, `/root`, `/opt`, `/lib`, `/lib64`

### Blocked User Patterns
`.ssh`, `.gnupg`, `.aws`, `.config`, `.local/bin`, `.bashrc`, `.profile`, `.zshrc`, `.npmrc`, `.pypirc`, `.docker`, `.gitconfig`, `.netrc`, `.env`, `.env.*`

### Git Hook Protection
Blocks writes to `.git/hooks/` and `.git/config`

### WorkRoot Containment
All writes must be inside the resolved WorkRoot. Symlink escapes are detected and blocked.

## Command Policy (`safety/command_policy.py`)

### Blocked Commands
`sudo rm`, `sudo mv`, `sudo cp`, `sudo chmod`, `sudo chown`, `chmod -R 777`, `chown -R`, `mkfs`, `mount`, `umount`, `fdisk`, `parted`

### Blocked Patterns
- `rm -rf` targeting system paths
- `dd` targeting system paths (both `if=` and `of=`)
- Any `sudo` usage
- `curl|sh`, `wget|bash`, download-to-shell pipes
- Dangerous code execution (`python -c os.system`, `node -e child_process`)
- Environment variable injection (`LD_PRELOAD`, `PYTHONPATH`, `BASH_ENV`, etc.)
- `trash` targeting system/credential paths
- Destructive `chmod`/`chown` on system paths
- Shell metacharacters in non-safe-listed commands
- Remote mutation patterns (`git push`, `ssh`, `scp`, `terraform apply`, etc.)

### Safe Command List
Commands with shell metacharacters that are allowed: `echo`, `printf`, `test`, `rg`, `grep`, `sed`, `awk`, `diff`, `cat`, `head`, `tail`, `sort`, `uniq`, `wc`, `cut`, `tr`, `find`, `xargs`, `git log`, `git diff`, `git show`, `python3`, `python`, `node`, `tsc`, `eslint`, `ruff`, `pytest`, `cargo`, `go`

## Credential Policy (`safety/credential_policy.py`)

Scans text for:
- API key patterns (sk-*, sk-ant-*, ghp_*, etc.)
- Bearer tokens
- Base64-encoded credentials
- Environment variable values from known secret vars
- File paths to credential files (.env, .ssh, .aws, etc.)

## Self-Protection (`safety/self_protection.py`)

When WorkRoot is inside the Galaxy Merge source tree:
- All file writes blocked
- All mutating shell commands blocked
- All git mutations blocked
- Read-only diagnostic mode

## Safety Audit (`safety/audit.py`)

All safety decisions are logged to `.gm/safety/blocked_actions.jsonl` as JSONL records.

## Tool Kernel Safety Gate

Before every mutating tool call, `ToolKernel.execute()`:
1. Checks if tool `requires_safety` and `mutates`
2. Extracts target path from params
3. Calls `SafetyGovernor.check_path_write(target)`
4. If blocked: returns `ToolResult(blocked=True)`, emits `tool_blocked` event
