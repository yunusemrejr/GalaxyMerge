# Contributing

## Public Repository Policy

`https://github.com/yunusemrejr/GalaxyMerge` is the canonical GitHub remote for this project and is a public repository. Treat every pushed commit as public disclosure.

Never push:

- Secrets, passwords, tokens, API keys, private keys, or session cookies
- `.env` files or machine-local provider configuration
- Provider/config JSON, including `providers.json`, model/routing/fusion config, endpoint lists, credential JSON, and remote target JSON
- Customer, personal, or proprietary data
- Generated runtime state from `.gm/`, logs, caches, or local browser profiles

Before committing, inspect the diff:

```bash
git status --short
git diff
git diff --staged
```

Also read `SECURITY.md` before publishing changes.

If a secret is ever committed, do not simply delete it in a later commit. Rotate the credential and remove it from history before pushing.

## Keeping GitHub Updated

Keep `origin` set to:

```bash
https://github.com/yunusemrejr/GalaxyMerge
```

After changes are verified, commit focused units of work and push to the public GitHub repository unless the user explicitly requests local-only work.

## Local Checks

Run the narrowest relevant check for the change, and prefer the full suite before publishing:

```bash
uv run pytest
./scripts/smoke_test.sh
./scripts/secret_scan.sh
```

If `gitleaks` or `trufflehog` is installed, `scripts/secret_scan.sh` delegates to
that scanner. Otherwise it uses the repository fallback scanner for common
credential patterns and forbidden public candidate paths.
