"""Concurrency primitives for Galaxy Merge's shared .gm/ resources.

File-locking mechanisms:
  - FileLock: cross-process advisory lock via POSIX flock
  - NullLock: no-op for when locking is disabled
  - LockTimeout: raised when a lock cannot be acquired in time

Atomic-file helpers:
  - atomic_write: write content via temp file + rename
  - atomic_append: thread/process-safe JSONL append
  - read_with_lock: read shared state while holding a read lock

Resource-level lock pool:
  - LockManager: central registry of named locks so callers don't
    create overlapping paths.
"""

import json
import os
import fcntl
import tempfile
import time
from pathlib import Path
from typing import Any, Callable


class LockTimeout(Exception):
    """Raised when a lock cannot be acquired before the deadline."""


class FileLock:
    """Cross-process advisory file lock using POSIX flock.

    Usage:

        with FileLock(lock_path):
            # critical section — safe across processes

    Thread-safe within the same process because Python serializes
    file-descriptor operations for the GIL, but the flock itself is
    process-scoped (all threads share the fd).
    """

    def __init__(self, path: Path, timeout: float = 10.0):
        self._path = path.resolve()
        self._timeout = timeout
        self._fd: int | None = None

    def __enter__(self) -> "FileLock":
        self._fd = os.open(str(self._path), os.O_CREAT | os.O_RDWR, 0o644)
        deadline = time.monotonic() + self._timeout
        while True:
            try:
                fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return self
            except (IOError, OSError) as exc:
                if time.monotonic() > deadline:
                    os.close(self._fd)
                    self._fd = None
                    raise LockTimeout(
                        f"could not acquire lock on {self._path} "
                        f"within {self._timeout}s"
                    ) from exc
                time.sleep(0.05)

    def __exit__(self, *exc: Any) -> None:
        if self._fd is not None:
            fcntl.flock(self._fd, fcntl.LOCK_UN)
            os.close(self._fd)
            self._fd = None

    def __repr__(self) -> str:
        return f"FileLock({self._path}, timeout={self._timeout})"


class NullLock:
    """No-op lock for when concurrency guards are disabled."""

    def __enter__(self) -> "NullLock":
        return self

    def __exit__(self, *exc: Any) -> None:
        pass


# ── Atomic file helpers ──────────────────────────────────────────────

def atomic_write(path: Path, content: str) -> None:
    """Write *content* to *path* atomically via temp-file + rename.

    On Linux this is a file-system metadata operation and is
    atomic at the VFS level for the rename(2) call.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f"._{path.name}_")
    try:
        os.write(fd, content.encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(tmp, str(path))


def atomic_append(path: Path, line: str) -> None:
    """Append *line* to a JSONL file safely.

    For lines smaller than PIPE_BUF (typically 4096 bytes on Linux)
    a plain O_APPEND write is atomic at the kernel level.  For safety
    we still wrap in an advisory lock so readers that iterate the
    file never see a partially-written line.
    """
    lock_path = path.with_suffix(".lock")
    with FileLock(lock_path, timeout=5.0):
        with open(path, "a+") as f:
            f.seek(0, os.SEEK_END)
            if f.tell() > 0:
                f.seek(f.tell() - 1)
                if f.read(1) != "\n":
                    f.write("\n")
            f.write(line if line.endswith("\n") else line + "\n")
            f.flush()
            os.fsync(f.fileno())


def read_with_lock(path: Path, reader: Callable[[], Any]) -> Any:
    """Run *reader* while holding a shared (LOCK_SH) advisory lock."""
    lock_path = path.with_suffix(".lock")
    fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_SH)
        return reader()
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


# ── Lock Manager ─────────────────────────────────────────────────────

_RESOURCE_LOCKS: dict[str, Path] = {}


class LockManager:
    """Central registry for named resource locks under .gm/locks/."""

    def __init__(self, gm_dir: Path):
        self._lock_dir = gm_dir / "locks"
        self._lock_dir.mkdir(parents=True, exist_ok=True)

    def lock_path(self, resource: str) -> Path:
        """Return the lock-file path for a named resource."""
        # Sanitise: replace path separators / with _
        safe = resource.replace("/", "_").replace("\\", "_")
        return self._lock_dir / f"{safe}.lock"

    def acquire(self, resource: str, timeout: float = 10.0) -> FileLock:
        """Return a FileLock context-manager for *resource*."""
        return FileLock(self.lock_path(resource), timeout=timeout)

    def cleanup_stale(self, max_age: float = 3600) -> int:
        """Remove lock files older than *max_age* seconds.

        Returns the number of locks removed.
        """
        now = time.time()
        removed = 0
        for f in self._lock_dir.glob("*.lock"):
            try:
                if now - f.stat().st_mtime > max_age:
                    f.unlink(missing_ok=True)
                    removed += 1
            except OSError:
                pass
        return removed
