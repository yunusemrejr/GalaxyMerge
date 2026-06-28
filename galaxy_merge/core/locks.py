"""
File-based advisory locking for concurrent .gm/ access.

Uses fcntl.flock on lockfiles. All shared resources (notes/index.json,
project.json, memory/*.jsonl, sessions/registry.jsonl) must be accessed
through an acquired lock to prevent silent corruption from concurrent
gm sessions in the same WorkRoot.
"""

import fcntl
import json
import os
import time
from pathlib import Path
from typing import Any, Callable


LOCK_DIR = "locks"
LOCK_TIMEOUT_SECONDS = 30.0
LOCK_POLL_INTERVAL = 0.05


class LockError(Exception):
    """Raised when a lock cannot be acquired within the timeout."""


class LockTimeout(LockError):
    """Raised when a file-level lock times out."""


class LockManager:
    """Advisory file-lock manager using fcntl.flock.

    All public methods are thread-safe for the same process. Cross-process
    safety relies on the OS kernel's flock semantics.
    """

    def __init__(self, gm_dir: Path):
        self._lock_dir = gm_dir / LOCK_DIR
        self._lock_dir.mkdir(parents=True, exist_ok=True)
        self._held: dict[str, int] = {}  # resource -> fd

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def acquire(self, resource: str, timeout: float | None = None) -> bool:
        """Acquire an exclusive lock on *resource*.

        Returns True if the lock was acquired, False if the resource name
        is empty.  Raises LockError if the lock cannot be acquired within
        *timeout* seconds (defaults to LOCK_TIMEOUT_SECONDS).
        """
        if not resource:
            return False
        effective_timeout = LOCK_TIMEOUT_SECONDS if timeout is None else timeout
        lock_path = self._lock_dir / _safe_name(resource)
        deadline = time.monotonic() + effective_timeout
        while True:
            try:
                fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o644)
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                self._held[resource] = fd
                return True
            except (BlockingIOError, OSError):
                if time.monotonic() >= deadline:
                    raise LockError(
                        f"could not acquire lock for {resource!r} "
                        f"within {effective_timeout:.1f}s"
                    ) from None
                time.sleep(LOCK_POLL_INTERVAL)

    def release(self, resource: str) -> None:
        """Release a previously acquired lock."""
        fd = self._held.pop(resource, None)
        if fd is not None:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            except OSError:
                pass
            try:
                os.close(fd)
            except OSError:
                pass

    def release_all(self) -> None:
        """Release every lock held by this manager instance."""
        for resource in list(self._held.keys()):
            self.release(resource)

    # ------------------------------------------------------------------
    # Context-manager helpers
    # ------------------------------------------------------------------

    def lock_path(self, resource: str) -> Path:
        """Return the lock file path for *resource*."""
        return self._lock_dir / _safe_name(resource)

    def cleanup_stale(self, max_age: float = 300.0) -> int:
        """Remove lock files older than *max_age* seconds.

        Returns the number of files removed.
        """
        removed = 0
        now = time.time()
        for entry in self._lock_dir.iterdir():
            if entry.is_file():
                try:
                    age = now - entry.stat().st_mtime
                    if age > max_age:
                        entry.unlink()
                        removed += 1
                except OSError:
                    pass
        return removed

    def locked(self, resource: str, timeout: float | None = None):
        """Return a context manager that acquires/releases *resource*."""
        return _LockContext(self, resource, timeout)


class FileLock:
    """A context-manager-based file-level lock using flock.

    Usage::

        with FileLock(lock_path, timeout=10.0):
            ...  # exclusive access
    """

    def __init__(self, path: Path, timeout: float = 30.0):
        self._path = path
        self._timeout = timeout
        self._fd: int | None = None

    def __enter__(self) -> "FileLock":
        self._path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + self._timeout
        while True:
            try:
                fd = os.open(str(self._path), os.O_CREAT | os.O_RDWR, 0o644)
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                self._fd = fd
                return self
            except (BlockingIOError, OSError):
                if time.monotonic() >= deadline:
                    raise LockTimeout(
                        f"could not acquire lock on {self._path} "
                        f"within {self._timeout:.1f}s"
                    ) from None
                time.sleep(LOCK_POLL_INTERVAL)

    def __exit__(self, *exc_info):
        if self._fd is not None:
            try:
                fcntl.flock(self._fd, fcntl.LOCK_UN)
            except OSError:
                pass
            try:
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None


class _LockContext:
    """Context manager returned by LockManager.locked()."""

    def __init__(self, mgr: LockManager, resource: str, timeout: float | None):
        self._mgr = mgr
        self._resource = resource
        self._timeout = timeout

    def __enter__(self):
        self._mgr.acquire(self._resource, self._timeout)
        return self

    def __exit__(self, *exc_info):
        self._mgr.release(self._resource)


# ------------------------------------------------------------------
# Higher-level helpers
# ------------------------------------------------------------------

def locked_read_json(path: Path, lock_manager: LockManager, resource: str) -> dict[str, Any]:
    """Read a JSON file under a lock."""
    with lock_manager.locked(resource):
        if path.exists():
            return json.loads(path.read_text())
        return {}


def locked_write_json(path: Path, data: dict[str, Any], lock_manager: LockManager, resource: str) -> None:
    """Write a JSON file under a lock (atomic temp+rename)."""
    with lock_manager.locked(resource):
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, default=str))
        tmp.replace(path)


def locked_update_json(
    path: Path,
    updater: Callable[[dict[str, Any]], dict[str, Any]],
    lock_manager: LockManager,
    resource: str,
) -> dict[str, Any]:
    """Read, update, and write a JSON file atomically under lock.

    *updater* receives the current dict and must return the new dict.
    """
    with lock_manager.locked(resource):
        current = json.loads(path.read_text()) if path.exists() else {}
        updated = updater(current)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(updated, indent=2, default=str))
        tmp.replace(path)
        return updated


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

# ------------------------------------------------------------------
# Low-level atomic file operations
# ------------------------------------------------------------------


def atomic_append(path: Path, line: str, *, _nested_lock: bool = False) -> None:
    """Append *line* (plus newline) to *path* atomically.

    Uses fcntl.flock on the target path with a ``.lock`` suffix.
    If the file does not end with a newline, one is inserted first
    to preserve JSONL integrity.

    Set ``_nested_lock=True`` when the caller already holds a ``FileLock``
    on the same path to avoid deadlock (flock is per-fd, not per-process).
    """
    if _nested_lock:
        prev = b""
        if path.exists():
            prev = path.read_bytes()
        if prev and not prev.endswith(b"\n"):
            prev += b"\n"
        path.write_bytes(prev + (line + "\n").encode("utf-8"))
        return
    lock_path = path.with_suffix(".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        prev = b""
        if path.exists():
            prev = path.read_bytes()
        if prev and not prev.endswith(b"\n"):
            prev += b"\n"
        path.write_bytes(prev + (line + "\n").encode("utf-8"))
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        except OSError:
            pass
        try:
            os.close(fd)
        except OSError:
            pass


def atomic_write(path: Path, content: str | bytes, *, _nested_lock: bool = False) -> None:
    """Write *content* to *path* atomically (temp + rename).

    Uses fcntl.flock on a sidecar ``.lock`` file for cross-process
    safety.

    Set ``_nested_lock=True`` when the caller already holds a ``FileLock``
    on the same path to avoid deadlock (flock is per-fd, not per-process).
    """
    if _nested_lock:
        encoded = content.encode("utf-8") if isinstance(content, str) else content
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(encoded)
        tmp.replace(path)
        return
    lock_path = path.with_suffix(".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        encoded = content.encode("utf-8") if isinstance(content, str) else content
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(encoded)
        tmp.replace(path)
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        except OSError:
            pass
        try:
            os.close(fd)
        except OSError:
            pass





def _safe_name(resource: str) -> str:
    """Sanitize a resource name for use as a filename."""
    safe = resource.replace("/", "_").replace("\\", "_")
    safe = "".join(c if c.isalnum() or c in ("_", "-", ".") else "_" for c in safe)
    return f"lock_{safe}.lock"
