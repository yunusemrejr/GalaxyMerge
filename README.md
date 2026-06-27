# GalaxyMerge

Galaxy Merge Harness is an Ubuntu/Linux-native web GUI based Python backend
agentic coding harness for developers.

## Repository

This project is maintained in the public GitHub repository:

```bash
git remote set-url origin https://github.com/yunusemrejr/GalaxyMerge
```

The repository at `https://github.com/yunusemrejr/GalaxyMerge` is public and is expected to remain public. Do not commit or push secrets, credentials, private keys, tokens, provider API keys, `.env` files, customer data, machine-local configuration, or other sensitive material.

Engineers and agents working in this checkout should keep the GitHub repo updated. After local verification, commit focused changes and push them to `origin` unless the user explicitly asks for local-only work.

Provider/config JSON files are local-only. Do not push `providers.json`, model/routing/fusion config JSON, endpoint lists, remote targets, credential JSON, or any derived provider configuration to the public repo.

## Quick Start

```bash
uv sync
uv run gm --help
```

## Local Provider Configuration

Public config examples live in `config/*.example.json`. Copy them into a
local-only config directory before filling provider metadata:

```bash
mkdir -p config_templates
cp config/providers.example.json config_templates/providers.json
cp config/models.example.json config_templates/models.json
cp config/fusion.example.json config_templates/fusion.json
cp config/routing.example.json config_templates/routing.json
```

Keep real API keys in exported environment variables such as
`GM_EXAMPLE_PROVIDER_API_KEY`. Do not commit filled provider configs, endpoint
lists, routing/model choices, `.env` files, logs, or `.gm/` state.

## Verification

```bash
uv run pytest
./scripts/smoke_test.sh
./scripts/secret_scan.sh
```

## Project Notes

- Runtime project state lives under `.gm/` and is intentionally ignored by Git.
- Provider and endpoint config JSON files are intentionally ignored by Git.
- Local virtual environments, caches, logs, build output, and environment files must stay untracked.
- Use `CONTRIBUTING.md`, `SECURITY.md`, and `AGENTS.md` before making or pushing changes.
