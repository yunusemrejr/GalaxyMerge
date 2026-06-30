# Deployment

## Distribution Model

Galaxy Merge is distributed as a Git repository clone. No package registry publication (yet).

## Install Methods

### Local Install (recommended)
```bash
git clone https://github.com/yunusemrejr/GalaxyMerge.git ~/Desktop/Galaxymerge
cd ~/Desktop/Galaxymerge
./scripts/install_local.sh
```

### Development Install
```bash
cd ~/Desktop/Galaxymerge
uv sync
```

### Wheel Build
```bash
uv build
pip install dist/galaxy_merge-0.1.0-py3-none-any.whl
```

## Launcher

The `gm` command is a shell script at `~/.local/bin/gm` created by `install_local.sh`. It activates the venv and runs `python -m galaxy_merge`.

## No Server-Side Deployment

Galaxy Merge is a local-only tool. There is no server-side deployment, no Docker, no cloud. The server runs on localhost only.

## Public Repository

The GitHub repository is public. All commits, branches, tags are public. Never push secrets.
