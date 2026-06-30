# Process Lifecycle

## Session States

```
created → running → understanding → planning → executing → testing → complete
                │                                              │
                ├─► stopped_by_signal                          │
                ├─► crashed                                    │
                └─► failed_safe ◄──────────────────────────────┘
```

Valid states: `running`, `understanding`, `planning`, `executing`, `testing`, `complete`, `stopped`, `stopped_by_signal`, `crashed`, `failed_safe`, `recovering`

Resumable states: `stopped`, `crashed`, `failed_safe`, `recovering`

## Heartbeat System

- Background daemon thread writes `.gm/sessions/heartbeats/<session_id>.hb` every 3 seconds
- Contains unix timestamp of last write
- `cleanup_stale_sessions()` removes sessions with no heartbeat in 300 seconds
- Stale session cleanup also removes the session directory and prunes the registry

## Session Registry

`.gm/sessions/registry.jsonl` — one JSON line per session with:
- `session_id`, `started_at`, `last_heartbeat`

`.gm/sessions/ports.json` — maps session_id to:
- `port`, `pid`, `workroot`, `updated_at`, `status`

Both files are locked with `fcntl.flock` for concurrent access safety.

## Multi-Session Safety

When multiple `gm` instances run on the same project:
- Each gets a unique session ID (`gmsess_YYYYMMDD_HHMMSS_<hex>`)
- Shared files (notes/index.json, memory/*.jsonl, sessions/registry.jsonl) use advisory file locks
- File write conflict detection via SHA-256 hash comparison (`expected_hash` injection)
- The `concurrency.py` module monkey-patches shared classes with lock-safe versions at startup

## Crash Recovery

On startup, `cleanup_stale_sessions()`:
1. Scans heartbeat files for sessions older than 300s
2. Removes stale session directories
3. Prunes registry and port mapping

A crashed session's state file persists with `status: "crashed"` and `error: <reason>`. It can be resumed with `gm --resume <session_id>`.

## Self-Codebase Protection

When `gm` detects it's running inside its own source tree:
1. `_is_inside_galaxy_merge_codebase(workroot)` checks if workroot is under the install dir
2. Server sets `_is_readonly = True`
3. All mutating API endpoints return 403
4. Safety Governor blocks all mutation commands
5. File write/patch tools are blocked
6. Git mutation commands are blocked
7. Read/index/diagnose operations remain available
