# Agent Instructions

This checkout is the Galaxy Merge Harness project. The canonical remote is:

```bash
https://github.com/yunusemrejr/GalaxyMerge
```

The GitHub repository is public and will remain public. Do not commit or push secrets, credentials, tokens, private keys, `.env` files, local provider configuration, provider/config JSON, endpoint lists, customer data, or machine-local runtime state.

Keep the GitHub repo updated: after implementing and verifying changes, commit focused diffs and push to `origin` unless the user explicitly asks for local-only work.

Before any commit or push:

```bash
git status --short
git diff
git diff --staged
```

Read `SECURITY.md` before publishing changes to GitHub.

Project-specific notes:

- `.gm/` is local runtime state and must stay ignored.
- Provider/config JSON files are local-only and must stay ignored.
- `.venv/`, caches, logs, build output, and environment files must stay untracked.
- Use `uv run pytest` for the Python test suite.
- Use `./scripts/smoke_test.sh` for the broader smoke check when the runtime surface changes.
