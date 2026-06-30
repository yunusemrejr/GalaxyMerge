# Concurrency

## Advisory File Locking

All shared resources use `fcntl.flock()` POSIX advisory locks via `LockManager` and `FileLock`.

### Lock Types
- `LOCK_EX` — exclusive (for writes)
- `LOCK_SH` — shared (for reads, used by EventLog.replay)
- `LOCK_NB` — non-blocking (with timeout retry)

### Lock Timeout
Default: 30 seconds. Configurable per lock. Poll interval: 50ms.

### Locked Resources
- `notes/index.json`
- `project.json`
- `memory/*.jsonl`
- `sessions/registry.jsonl`
- `sessions/ports.json`
- `sessions/<id>/events.jsonl`
- `sessions/<id>/transcript.jsonl`
- `indexes/file_hashes.json`
- All cache files

## Atomic Operations

### `atomic_write(path, content)`
1. Acquire flock on `path.lock`
2. Write to `path.tmp`
3. Rename `path.tmp` → `path`
4. Release flock

### `atomic_append(path, line)`
1. Acquire flock on `path.lock`
2. Ensure file ends with newline
3. Append `line + "\n"`
4. Release flock

## Concurrency Patches (`core/concurrency.py`)

`upgrade_concurrency(gm_dir)` monkey-patches shared classes with lock-safe versions:
- `MemoryStore.append`, `read_all`, `set_preference`
- `ProjectMemory.record_fact`, `record_failure`, `record_fix`, `record_lesson`
- `CacheStore.set`, `get`, `invalidate`
- `Session.save_state`, `set_goal`
- `WorkspaceIndexer._save_hashes`, `refresh`, `incremental_update`
- `EventLog.emit`
- `SessionMemory.add_entry`
- Notes tools `_save_index`, `_get_index`

Patches are idempotent (safe to call multiple times).

## File Conflict Detection

Before writing a file, the orchestrator injects `expected_hash` (SHA-256[:16] of current content). The tool handler compares with current content. If hash mismatch → conflict detected and reported.

## Session Isolation

Each session gets:
- Unique ID: `gmsess_YYYYMMDD_HHMMSS_<hex>`
- Own directory: `.gm/sessions/<session_id>/`
- Own event log, transcript, tool calls, safety log
- Heartbeat file for liveness detection
- Port mapping for API access

## Background Threads

- Heartbeat thread: daemon, writes every 3s, stops on shutdown
- Port allocation lock: threading.Lock for offline port registry
