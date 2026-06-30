# Troubleshooting

## Common Issues

### `gm: command not found`
- Run `./scripts/install_local.sh` from the Galaxy Merge source directory
- Check `~/.local/bin` is in PATH: `export PATH="$HOME/.local/bin:$PATH"`
- Verify launcher exists: `ls -la ~/.local/bin/gm`

### Server fails to start (port in use)
- Use `--port` to specify a different port: `gm --port 8080`
- Or kill the process using the port: `lsof -i :7419`

### Python version error
- Galaxy Merge requires Python ≥ 3.12
- Check: `python3 --version`
- Install Python 3.12+ if needed

### Missing packages
- Run `uv sync` from the source directory
- Or `pip install -r requirements.txt` if not using uv

### Provider not available
- Check environment variables are set: `gm --doctor`
- Missing keys don't crash the harness — providers are marked unavailable
- Set keys in `~/.bashrc` or `.env` file

### Session stuck / can't resume
- Check session state: `cat .gm/sessions/<id>/state.json`
- Heartbeat timeout is 300s — stale sessions are auto-cleaned
- Force resume: `gm --resume <session_id>`

### .gm/ structure warnings
- Run `gm --doctor` to check
- Delete `.gm/` and restart: `rm -rf .gm && gm`

### Browser doesn't open
- Use `gm --no-browser` and open `http://127.0.0.1:<port>` manually
- Check terminal output for the GUI URL

### Tests failing
- Ensure in venv: `source .venv/bin/activate`
- Run specific test: `uv run pytest galaxy_merge/tests/test_config.py -v`
- Check timeout: tests have 30s timeout by default

### Secret scan false positives
- Review the scan output carefully
- Config examples should use placeholders only
- `.env` files should never be committed

## Diagnostic Command

```bash
gm --doctor
```

Checks: Python version, venv, packages, launcher, PATH, config files, provider keys, secret safety, .env.example.
