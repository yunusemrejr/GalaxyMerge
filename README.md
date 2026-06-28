# GalaxyMerge

Galaxy Merge Harness is an Ubuntu/Linux-native web GUI based Python backend
agentic coding harness for developers.

## Repository

This project is maintained in the public GitHub repository:

```bash
git remote set-url origin https://github.com/yunusemrejr/GalaxyMerge
```

The repository at `https://github.com/yunusemrejr/GalaxyMerge` is public and is expected to remain public. Do not commit or push secrets, credentials, private keys, tokens, provider API keys, `.env` files, customer data, machine-local configuration, or other sensitive material.

## Install and Use

### Important: Two Folders

Galaxy Merge uses **two separate folders**:

```
~/Desktop/Galaxymerge/     = Galaxy Merge app/source/install folder
~/Desktop/MyProject/       = target project you want Galaxy Merge to work on
```

**Do not run normal autonomous work inside the Galaxy Merge source tree.**
Running `gm` from the Galaxy Merge source tree enters read-only diagnostic mode.

### Quick Install

```bash
cd ~/Desktop
git clone https://github.com/yunusemrejr/GalaxyMerge.git Galaxymerge
cd Galaxymerge
./scripts/install_local.sh
```

The install script will:
- Check Python >= 3.12
- Create a local `.venv/` virtual environment
- Install all Python dependencies
- Create a `gm` launcher at `~/.local/bin/gm`
- Set up config templates
- Check PATH configuration

### Use on a Project

After installing, navigate to **any project directory** and run `gm`:

```bash
cd ~/Desktop/MyProject
gm
```

Galaxy Merge will:
1. Detect the project's WorkRoot
2. Create `.gm/` runtime state in your project
3. Start the backend server on localhost
4. Open the browser GUI
5. Stream logs to the terminal
6. Shut down cleanly on Ctrl+C

### Diagnostics

```bash
gm --doctor
```

Checks Python version, packages, launcher health, config files, provider keys,
secret safety, and PATH configuration.

### Version

```bash
gm --version
```

## Self-Codebase Protection

If you run `gm` inside the Galaxy Merge source tree:

```bash
cd ~/Desktop/Galaxymerge
gm
```

Galaxy Merge detects this and enters **read-only diagnostic mode**:

- File writes are disabled
- File patches are disabled
- Mutating shell commands are disabled
- Git mutations are disabled
- Read/index/diagnose operations are allowed
- Terminal shows a warning with instructions

To use Galaxy Merge on a project:

```bash
cd /path/to/your/project
gm
```

## Provider Configuration

Galaxy Merge reads provider keys from **environment variables**. No keys are
committed to the repository.

### Supported Environment Variables

```bash
OPENAI_API_KEY
ANTHROPIC_API_KEY
GOOGLE_API_KEY
DEEPSEEK_API_KEY
MINIMAX_API_KEY
STREAMLAKE_API_KEY
STEPFUN_API_KEY
OPENROUTER_API_KEY
GITHUB_TOKEN
GH_TOKEN
```

### Setting Keys

Export them in your shell profile (`~/.bashrc` or `~/.zshrc`):

```bash
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."
```

Or create a `.env` file in your project (never commit it):

```bash
cp ~/Desktop/Galaxymerge/.env.example .env
# Edit .env with your keys
```

### Missing Keys

Missing keys do **not** crash the harness. Providers without keys are marked
unavailable. The GUI shows provider availability. The terminal shows
loaded/available/unavailable provider counts.

### Config Templates

Public config examples live in `config/*.example.json`. During install,
they are copied to `galaxy_merge/config_templates/` for local use.

```bash
config/providers.example.json
config/models.example.json
config/fusion.example.json
config/routing.example.json
```

All examples use placeholders only — no real keys or endpoints.

## Runtime State

- `.gm/` is project-local runtime state (sessions, notes, memory, caches, logs)
- `.gm/` is intentionally ignored by Git
- `.gm/` should not be committed unless intentionally using fake schema examples
- Terminal owns runtime logs
- Browser GUI is the main interaction surface

## Uninstall

```bash
./scripts/uninstall_local.sh
```

Or manually:

```bash
rm ~/.local/bin/gm
rm -rf ~/.config/galaxy-merge
rm -rf ~/.local/share/galaxy-merge
# Optional: rm -rf ~/Desktop/Galaxymerge/.venv
```

User projects and their `.gm/` directories are never touched by uninstall.

## Verification

```bash
# Run unit tests (quick)
uv run pytest galaxy_merge/tests/test_gm_structure.py galaxy_merge/tests/test_config.py -v

# Run new safety, config, and cache tests
uv run pytest galaxy_merge/tests/test_safety_governor.py galaxy_merge/tests/test_provider_config.py galaxy_merge/tests/test_cache.py -v

# Run full smoke test (end-to-end, ~30s)
./scripts/smoke_test.sh

# Secret scan
./scripts/secret_scan.sh
python scripts/secret_scan.py
```

### CI

The CI pipeline (`.github/workflows/ci.yml`) runs on every push and PR:
- Unit tests (excluding slow integration/redteam suites)
- Smoke test
- Secret scan
- Repository hygiene checks (no `.gm/` or `.env` tracked, config examples clean)

## Testing Coverage

The test suite covers these layers:

**Unit tests:**
- `.gm/` structure creation and validation
- Notes CRUD operations with index management
- Safety Governor path and command policies
- Credential redaction
- Cache key generation and TTL expiration
- Config loading and validation
- Session isolation
- Event logging format

**Integration tests:**
- `gm` launcher creates session state
- Backend starts on localhost with port fallback
- WebSocket event streaming
- GUI API endpoints
- Provider degradation handling
- Concurrent session management

**Smoke tests (E2E):**
- Full `gm` lifecycle from a generated project
- `.gm/` directory structure verification
- API endpoint responsiveness
- Goal execution and event persistence
- Clean shutdown and crash recovery
- Secret safety in generated logs

## Project Notes

- Runtime project state lives under `.gm/` and is intentionally ignored by Git.
- Provider and endpoint config JSON files are intentionally ignored by Git.
- Local virtual environments, caches, logs, build output, and environment files must stay untracked.
- Use `CONTRIBUTING.md`, `SECURITY.md`, and `AGENTS.md` before making or pushing changes.
