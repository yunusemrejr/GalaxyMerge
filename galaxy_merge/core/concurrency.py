"""Concurrency-safety upgrades for Galaxy Merge shared resources.

This module provides a single entry point (upgrade_concurrency) that
patches the existing classes in memory with file-locking, atomic
writes, and conflict detection.

Patching is safe to call multiple times (idempotent).
"""

import functools
import json
import time
from pathlib import Path
from typing import Any

from galaxy_merge.core.locks import FileLock, LockManager, LockTimeout, atomic_write

_LOCK_MANAGER: LockManager | None = None
_PATCHED: set[str] = set()

# ── Session registry ─────────────────────────────────────────────────


def register_active_session(gm_dir: Path, session_id: str) -> None:
    """Append this session to the project-level active-sessions registry.

    The registry is an append-only JSONL so concurrent registrations
    are safe under our atomic_append.
    """
    registry_path = gm_dir / "sessions" / "registry.jsonl"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    from galaxy_merge.core.locks import atomic_append
    record = {
        "session_id": session_id,
        "started_at": time.time(),
        "last_heartbeat": time.time(),
    }
    atomic_append(registry_path, json.dumps(record))


def write_heartbeat(gm_dir: Path, session_id: str) -> None:
    """Update the heartbeat file for an active session."""
    hb_dir = gm_dir / "sessions" / "heartbeats"
    hb_dir.mkdir(parents=True, exist_ok=True)
    atomic_write(hb_dir / f"{session_id}.hb", str(time.time()))


def cleanup_stale_sessions(
    gm_dir: Path, max_age: float = 300
) -> list[str]:
    """Remove session directories that have no heartbeat within *max_age*.

    Returns a list of stale session IDs that were cleaned up.
    """
    stale: list[str] = []
    hb_dir = gm_dir / "sessions" / "heartbeats"
    now = time.time()

    for hb_file in hb_dir.glob("*.hb"):
        try:
            if now - hb_file.stat().st_mtime > max_age:
                session_id = hb_file.stem
                session_dir = gm_dir / "sessions" / session_id
                if session_dir.exists():
                    import shutil
                    shutil.rmtree(session_dir, ignore_errors=True)
                hb_file.unlink(missing_ok=True)
                stale.append(session_id)
        except OSError:
            pass

    # Also remove stale entries from registry
    registry_path = gm_dir / "sessions" / "registry.jsonl"
    if registry_path.exists():
        active_ids = {s.stem for s in hb_dir.glob("*.hb")}
        new_lines: list[str] = []
        try:
            for line in registry_path.read_text().splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    if rec.get("session_id") in active_ids:
                        new_lines.append(line)
                except json.JSONDecodeError:
                    pass
            content = "\n".join(new_lines)
            atomic_write(registry_path, content + ("\n" if content else ""))
        except OSError:
            pass

    return stale


# ── Conflict detection ────────────────────────────────────────────────

_FILE_HASH_CACHE: dict[str, str] = {}


def file_hash(path: Path) -> str:
    """Return a short SHA-256 hex digest of *path* contents.

    No in-memory caching so that callers always see the latest
    on-disk content — important for conflict detection.
    """
    import hashlib
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()[:16]
    except OSError:
        return ""


def detect_file_conflict(
    path: Path, expected_hash: str
) -> dict[str, Any]:
    """Check if *path* has changed since *expected_hash* was recorded.

    Returns {"conflict": False} or {"conflict": True, "current_hash": ..., "path": ...}.
    """
    current = file_hash(path)
    if current and current != expected_hash:
        return {
            "conflict": True,
            "path": str(path),
            "expected_hash": expected_hash,
            "current_hash": current,
        }
    return {"conflict": False}


# ── Lock-manager singleton ──────────────────────────────────────────

def get_lock_manager(gm_dir: Path) -> LockManager:
    global _LOCK_MANAGER
    if _LOCK_MANAGER is None:
        _LOCK_MANAGER = LockManager(gm_dir)
    return _LOCK_MANAGER


# ── Patching functions ──────────────────────────────────────────────

def patch_memory_store() -> None:
    """Replace MemoryStore.append and set_preference with lock-safe versions."""
    if "memory_store" in _PATCHED:
        return
    from galaxy_merge.memory.store import MemoryStore

    _orig_append = MemoryStore.append
    _orig_set_pref = MemoryStore.set_preference
    _orig_read_all = MemoryStore.read_all

    @functools.wraps(_orig_append)
    def _safe_append(self, kind: str, data: dict[str, Any]) -> None:
        path = self.memory_dir / f"{kind}.jsonl"
        from galaxy_merge.core.locks import atomic_append
        atomic_append(path, json.dumps(data, default=str))

    @functools.wraps(_orig_set_pref)
    def _safe_set_pref(self, key: str, value: Any) -> None:
        prefs_path = self.memory_dir / "preferences.json"
        lock_path = prefs_path.with_suffix(".lock")
        with FileLock(lock_path, timeout=5.0):
            prefs: dict[str, Any] = {}
            if prefs_path.exists():
                try:
                    prefs = json.loads(prefs_path.read_text())
                except (json.JSONDecodeError, OSError):
                    pass
            prefs[key] = value
            atomic_write(prefs_path, json.dumps(prefs, indent=2))

    @functools.wraps(_orig_read_all)
    def _safe_read_all(self, kind: str) -> list[dict[str, Any]]:
        path = self.memory_dir / f"{kind}.jsonl"
        if not path.exists():
            return []
        lock_path = path.with_suffix(".lock")
        try:
            with FileLock(lock_path, timeout=5.0):
                records = []
                with open(path) as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                records.append(json.loads(line))
                            except json.JSONDecodeError:
                                pass
                return records
        except LockTimeout:
            # Fallback: read without lock
            records = []
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            records.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass
            return records

    MemoryStore.append = _safe_append
    MemoryStore.set_preference = _safe_set_pref
    MemoryStore.read_all = _safe_read_all
    _PATCHED.add("memory_store")


def patch_project_memory() -> None:
    """Replace ProjectMemory record_* methods with atomic writes."""
    if "project_memory" in _PATCHED:
        return
    from galaxy_merge.memory.project_memory import ProjectMemory

    _orig_rf = ProjectMemory.record_fact
    _orig_rfail = ProjectMemory.record_failure
    _orig_rfix = ProjectMemory.record_fix
    _orig_rlesson = ProjectMemory.record_lesson

    @functools.wraps(_orig_rf)
    def _safe_rf(self, fact: str, source: str = "session") -> None:
        path = self.store.memory_dir / "known_facts.jsonl"
        from galaxy_merge.core.locks import atomic_append
        atomic_append(path, json.dumps({"fact": fact, "source": source}, default=str))

    @functools.wraps(_orig_rfail)
    def _safe_rfail(self, error: str, context: str = "") -> None:
        path = self.store.memory_dir / "known_failures.jsonl"
        from galaxy_merge.core.locks import atomic_append
        atomic_append(path, json.dumps({"error": error, "context": context}, default=str))

    @functools.wraps(_orig_rfix)
    def _safe_rfix(self, issue: str, fix: str, verified: bool = False) -> None:
        path = self.store.memory_dir / "verified_fixes.jsonl"
        from galaxy_merge.core.locks import atomic_append
        atomic_append(path, json.dumps({"issue": issue, "fix": fix, "verified": verified}, default=str))

    @functools.wraps(_orig_rlesson)
    def _safe_rlesson(self, lesson: str, category: str = "general") -> None:
        path = self.store.memory_dir / "lessons.jsonl"
        from galaxy_merge.core.locks import atomic_append
        atomic_append(path, json.dumps({"lesson": lesson, "category": category}, default=str))

    ProjectMemory.record_fact = _safe_rf
    ProjectMemory.record_failure = _safe_rfail
    ProjectMemory.record_fix = _safe_rfix
    ProjectMemory.record_lesson = _safe_rlesson
    _PATCHED.add("project_memory")


def patch_cache_store() -> None:
    """Replace CacheStore.set/get with lock-safe versions."""
    if "cache_store" in _PATCHED:
        return
    from galaxy_merge.cache.store import CacheStore

    _orig_set = CacheStore.set
    _orig_get = CacheStore.get
    _orig_invalidate = CacheStore.invalidate

    @functools.wraps(_orig_set)
    def _safe_set(self, key: str, value: Any, ttl_seconds: int = 300) -> None:
        path = self._key_path(key)
        lock_path = path.with_suffix(".lock")
        expires = time.time() + ttl_seconds if ttl_seconds else 0
        data = {"value": value, "_expires": expires, "_created": time.time()}
        with FileLock(lock_path, timeout=5.0):
            atomic_write(path, json.dumps(data, default=str))

    @functools.wraps(_orig_get)
    def _safe_get(self, key: str) -> Any | None:
        path = self._key_path(key)
        if not path.exists():
            return None
        lock_path = path.with_suffix(".lock")
        try:
            with FileLock(lock_path, timeout=5.0):
                try:
                    data = json.loads(path.read_text())
                    expires = data.get("_expires", 0)
                    if expires and time.time() > expires:
                        path.unlink(missing_ok=True)
                        return None
                    return data.get("value")
                except (json.JSONDecodeError, OSError):
                    return None
        except LockTimeout:
            # Fallback: read without lock
            try:
                data = json.loads(path.read_text())
                expires = data.get("_expires", 0)
                if expires and time.time() > expires:
                    return None
                return data.get("value")
            except (json.JSONDecodeError, OSError):
                return None

    @functools.wraps(_orig_invalidate)
    def _safe_invalidate(self, key: str) -> None:
        path = self._key_path(key)
        lock_path = path.with_suffix(".lock")
        with FileLock(lock_path, timeout=5.0):
            path.unlink(missing_ok=True)
            lock_path.unlink(missing_ok=True)

    CacheStore.set = _safe_set
    CacheStore.get = _safe_get
    CacheStore.invalidate = _safe_invalidate
    _PATCHED.add("cache_store")


def patch_session() -> None:
    """Replace Session.save_state with atomic write."""
    if "session" in _PATCHED:
        return
    from galaxy_merge.core.session import Session

    _orig_save = Session.save_state
    _orig_set_goal = Session.set_goal

    @functools.wraps(_orig_save)
    def _safe_save_state(self) -> None:
        self.session_dir.mkdir(parents=True, exist_ok=True)
        for sub in ["diffs", "artifacts"]:
            (self.session_dir / sub).mkdir(parents=True, exist_ok=True)
        for fname in ["transcript.jsonl", "council.jsonl", "tool_calls.jsonl", "safety.jsonl"]:
            p = self.session_dir / fname
            if not p.exists():
                p.touch()
        state = {
            "session_id": self.session_id,
            "workroot": str(self.workroot),
            "created_at": self.created_at.isoformat(),
            "updated_at": __import__("datetime").datetime.now(
                __import__("datetime").timezone.utc
            ).isoformat(),
            "status": self._state.get("status", "running"),
            "goal": self._state.get("goal", ""),
            "active": self._state.get("active", True),
        }
        atomic_write(self.state_path, json.dumps(state, indent=2, default=str))

    @functools.wraps(_orig_set_goal)
    def _safe_set_goal(self, goal: str) -> None:
        self._state["goal"] = goal
        self._state["status"] = "understanding"
        self.save_state()
        goal_data = {
            "goal": goal,
            "parsed": {},
            "status": "understanding",
            "created_at": __import__("datetime").datetime.now(
                __import__("datetime").timezone.utc
            ).isoformat(),
        }
        self.goal_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(self.goal_path, json.dumps(goal_data, indent=2))

    Session.save_state = _safe_save_state
    Session.set_goal = _safe_set_goal
    _PATCHED.add("session")


def patch_workspace_indexer() -> None:
    """Replace WorkspaceIndexer._save_hashes with lock-safe version."""
    if "workspace_indexer" in _PATCHED:
        return
    from galaxy_merge.workspace.indexer import WorkspaceIndexer

    _orig_save = WorkspaceIndexer._save_hashes
    _orig_refresh = WorkspaceIndexer.refresh
    _orig_inc = WorkspaceIndexer.incremental_update

    @functools.wraps(_orig_save)
    def _safe_save_hashes(self) -> None:
        path = self.index_dir / "file_hashes.json"
        lock_path = path.with_suffix(".lock")
        with FileLock(lock_path, timeout=10.0):
            atomic_write(path, json.dumps(self._file_hashes, indent=2))

    @functools.wraps(_orig_refresh)
    def _safe_refresh(self) -> dict[str, Any]:
        import hashlib
        changed: list[str] = []
        removed: list[str] = []
        current_hashes: dict[str, str] = {}
        file_count = 0

        for path in self.workroot.rglob("*"):
            if path.is_file() and not path.name.startswith("."):
                relative = str(path.relative_to(self.workroot))
                try:
                    h = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
                    current_hashes[relative] = h
                    file_count += 1
                    if relative in self._file_hashes:
                        if self._file_hashes[relative] != h:
                            changed.append(relative)
                    else:
                        changed.append(relative)
                except (OSError, PermissionError):
                    pass

        for rel in self._file_hashes:
            if rel not in current_hashes:
                removed.append(rel)

        self._file_hashes = current_hashes
        self._save_hashes()

        from galaxy_merge.workspace.tree import FileTree
        tree = FileTree(self.workroot).build()

        summary = {
            "total_files": file_count,
            "changed": changed,
            "removed": removed,
            "tree": tree,
        }
        meta_path = self.index_dir / "index.meta.json"
        atomic_write(meta_path, json.dumps({"changed": changed, "removed": removed, "total": file_count}))
        return summary

    @functools.wraps(_orig_inc)
    def _safe_inc(self, files: list[str]) -> dict[str, Any]:
        import hashlib
        hashes_path = self.index_dir / "file_hashes.json"
        lock_path = hashes_path.with_suffix(".lock")
        with FileLock(lock_path, timeout=10.0):
            # Re-read within lock to get latest state
            if hashes_path.exists():
                self._file_hashes = json.loads(hashes_path.read_text())
            changed = []
            for f in files:
                fp = (self.workroot / f).resolve()
                if fp.exists() and fp.is_file():
                    try:
                        h = hashlib.sha256(fp.read_bytes()).hexdigest()[:16]
                        relative = str(fp.relative_to(self.workroot))
                        old_hash = self._file_hashes.get(relative)
                        self._file_hashes[relative] = h
                        if old_hash != h:
                            changed.append(relative)
                    except (OSError, ValueError):
                        pass
            atomic_write(hashes_path, json.dumps(self._file_hashes, indent=2))
        return {"changed": changed, "total": len(self._file_hashes)}

    WorkspaceIndexer._save_hashes = _safe_save_hashes
    WorkspaceIndexer.refresh = _safe_refresh
    WorkspaceIndexer.incremental_update = _safe_inc
    _PATCHED.add("workspace_indexer")


def patch_event_log() -> None:
    """Replace EventLog.emit with atomic append."""
    if "event_log" in _PATCHED:
        return
    from galaxy_merge.core.events import EventLog

    _orig_emit = EventLog.emit

    @functools.wraps(_orig_emit)
    def _safe_emit(self, event: str, session_id: str = "", **kwargs: Any) -> dict[str, Any]:
        record = {
            "time": __import__("datetime").datetime.now(
                __import__("datetime").timezone.utc
            ).isoformat(),
            "session_id": session_id,
            "event": event,
            **kwargs,
        }
        line = json.dumps(record, default=str)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.touch()
        from galaxy_merge.core.locks import atomic_append
        atomic_append(self.path, line)
        return record

    EventLog.emit = _safe_emit
    _PATCHED.add("event_log")


def patch_session_memory() -> None:
    """Replace SessionMemory.add_entry with atomic append."""
    if "session_memory" in _PATCHED:
        return
    from galaxy_merge.memory.session_memory import SessionMemory

    _orig_add = SessionMemory.add_entry

    @functools.wraps(_orig_add)
    def _safe_add(self, entry_type: str, content: Any) -> None:
        import json
        entry = {"type": entry_type, "content": content}
        self._entries.append(entry)
        from galaxy_merge.core.locks import atomic_append
        atomic_append(self.transcript_path, json.dumps(entry, default=str))

    SessionMemory.add_entry = _safe_add
    _PATCHED.add("session_memory")


def patch_notes_tools() -> None:
    """Replace notes_create/notes_update/notes_write with lock-safe versions.

    This patches the closures returned by make_notes_tools by replacing
    the _save_index and _get_index helpers in the notes_tools module.
    """
    if "notes_tools" in _PATCHED:
        return
    import galaxy_merge.tools.notes_tools as nt

    _orig_save_idx = nt._save_index
    _orig_get_idx = nt._get_index

    @functools.wraps(_orig_save_idx)
    def _safe_save_index(notes_dir: Path, index: dict[str, Any]) -> None:
        idx_path = notes_dir / "index.json"
        lock_path = idx_path.with_suffix(".lock")
        with FileLock(lock_path, timeout=5.0):
            atomic_write(idx_path, json.dumps(index, indent=2))

    @functools.wraps(_orig_get_idx)
    def _safe_get_index(notes_dir: Path) -> dict[str, Any]:
        idx_path = notes_dir / "index.json"
        if idx_path.exists():
            lock_path = idx_path.with_suffix(".lock")
            try:
                with FileLock(lock_path, timeout=5.0):
                    return json.loads(idx_path.read_text())
            except (LockTimeout, json.JSONDecodeError, OSError):
                return json.loads(idx_path.read_text())
        return {"schema_version": 1, "notes": []}

    nt._save_index = _safe_save_index
    nt._get_index = _safe_get_index
    _PATCHED.add("notes_tools")


def upgrade_concurrency(gm_dir: Path | None = None) -> None:
    """Apply all concurrency-safety patches.

    Safe to call multiple times (idempotent).  Call early in app startup.
    """
    patch_memory_store()
    patch_project_memory()
    patch_cache_store()
    patch_session()
    patch_workspace_indexer()
    patch_event_log()
    patch_session_memory()
    patch_notes_tools()
