# CLI Commands

## Entry Point

`galaxy_merge/__main__.py:main()` — registered as `gm` in pyproject.toml

## Commands and Flags

### `gm`
Launch Galaxy Merge on the current directory. Detects WorkRoot, creates `.gm/`, starts server, opens browser.

### `gm --version`
Print version and exit. Output: `Galaxy Merge Harness v0.1.0`

### `gm --doctor`
Run diagnostics. Checks:
- Python version ≥ 3.12
- Virtual environment active
- Required packages installed (fastapi, uvicorn, pydantic, httpx, websockets, pyyaml, requests)
- Optional packages (beautifulsoup4, lxml)
- Launcher at `~/.local/bin/gm`
- `~/.local/bin` in PATH
- Config files exist
- Example configs exist
- Provider keys (13 env vars)
- Secret safety (.gitignore entries)
- `.env.example` exists

### `gm --no-browser`
Start server without opening the browser GUI.

### `gm --port <N>`
Specify server port. Default: `0` (auto-select, starting from 7419).

### `gm --project <path>`
Explicit project directory instead of using CWD.

### `gm --resume <session_id>`
Resume a previously stopped/crashed session.
