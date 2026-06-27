# Security

## Public Repository

`https://github.com/yunusemrejr/GalaxyMerge` is public and will remain public. Assume all pushed commits, branches, tags, issues, and pull requests are visible outside the team.

## No Secrets

Do not commit or push:

- API keys, access tokens, passwords, private keys, session cookies, or credentials
- `.env` files or machine-local provider configuration
- Provider/config JSON files, including provider endpoints, routing, model maps, credential JSON, and remote target JSON
- Customer data, personal data, proprietary files, or deployment credentials
- Runtime state from `.gm/`, logs, caches, browser profiles, or local test artifacts

If a secret is committed, rotate the credential immediately and remove it from Git history before pushing.

## Before Publishing

Review the actual diff before every commit and push:

```bash
git status --short
git diff
git diff --staged
./scripts/secret_scan.sh
```

Run `./scripts/secret_scan.sh --history` before the first public push or any
release. If the history scan reports a real secret, rotate that credential and
clean the history before pushing.
