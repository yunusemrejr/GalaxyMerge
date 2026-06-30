# Build and Run

## Prerequisites

- Python ≥ 3.12
- Ubuntu/Linux (primary platform)
- uv package manager (recommended) or pip

## Install

```bash
cd ~/Desktop
git clone https://github.com/yunusemrejr/GalaxyMerge.git Galaxymerge
cd Galaxymerge
./scripts/install_local.sh
```

The install script:
1. Checks Python ≥ 3.12
2. Creates `.venv/` virtual environment
3. Installs dependencies via uv
4. Creates `~/.local/bin/gm` launcher
5. Copies config templates
6. Checks PATH configuration

## Run on a Project

```bash
cd ~/Desktop/MyProject
gm
```

## Build Wheel

```bash
uv build
# or
pip install hatchling && hatch build
```

## Development Setup

```bash
cd ~/Desktop/Galaxymerge
uv sync
uv run python -m galaxy_merge --version
```

## Key Commands

| Command | Purpose |
|---------|---------|
| `gm` | Launch on current directory |
| `gm --doctor` | Run diagnostics |
| `gm --version` | Print version |
| `gm --no-browser` | Don't open browser |
| `gm --port 8080` | Use specific port |
| `gm --project /path` | Use explicit project dir |
| `gm --resume <id>` | Resume crashed session |
| `uv run pytest` | Run test suite |
| `./scripts/smoke_test.sh` | End-to-end smoke test |
| `./scripts/secret_scan.sh` | Check for secrets |
| `./scripts/uninstall_local.sh` | Uninstall |

## Uninstall

```bash
./scripts/uninstall_local.sh
```

Or manually:
```bash
rm ~/.local/bin/gm
rm -rf ~/.config/galaxy-merge
rm -rf ~/.local/share/galaxy-merge
```

User projects and their `.gm/` directories are never touched.
