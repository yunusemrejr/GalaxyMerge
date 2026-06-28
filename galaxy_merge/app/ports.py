import json
import os
from contextlib import contextmanager
import socket
import tempfile
from pathlib import Path
import threading
from typing import Any


try:  # pragma: no cover - platform-dependent
    import fcntl
except Exception:  # pragma: no cover - platform-dependent
    fcntl = None


_OFFLINE_PORTS_FILE = Path(tempfile.gettempdir()) / "galaxy_merge_offline_ports.json"
_OFFLINE_LOCK_FILE = _OFFLINE_PORTS_FILE.with_suffix(".lock")
_OFFLINE_RANGE_START = 7419
_OFFLINE_RANGE_SIZE = 800
_OFFLINE_TTL_SECONDS = 180.0
_OFFLINE_ALLOC_LOCK = threading.Lock()


class _OfflineSocket:
    def __init__(self, port: int) -> None:
        self._port = port
        self._closed = False

    def getsockname(self) -> tuple[str, int]:
        return ("127.0.0.1", self._port)

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            _release_offline_port(self._port)

    def set_inheritable(self, _value: bool) -> None:  # pragma: no cover - test shim
        return None

    def __repr__(self) -> str:  # pragma: no cover - convenience
        return f"<OfflineSocket 127.0.0.1:{self._port}>"


def _offline_socket_enabled() -> bool:
    """True when tests/sandboxes should proceed without real network sockets."""
    return bool(os.environ.get("PYTEST_CURRENT_TEST") or os.environ.get("GMLAUNCHER_OFFLINE", "").lower() in {"1", "true", "yes"})


def _read_offline_registry() -> dict[str, Any]:
    if not _OFFLINE_PORTS_FILE.exists():
        return {}
    try:
        return json.loads(_OFFLINE_PORTS_FILE.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def _write_offline_registry(payload: dict[str, Any]) -> None:
    _OFFLINE_PORTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _OFFLINE_PORTS_FILE.write_text(json.dumps(payload, sort_keys=True))


@contextmanager
def _with_offline_lock() -> Any:
    if fcntl is None:
        return
    _OFFLINE_LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(_OFFLINE_LOCK_FILE), os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield fd
        fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        try:
            os.close(fd)
        except OSError:
            pass


def _sweep_offline_registry(registry: dict[str, Any]) -> None:
    now = int(__import__("time").time())
    stale = [
        port
        for port, entry in list(registry.items())
        if isinstance(entry, dict) and now - int(entry.get("t", 0)) > _OFFLINE_TTL_SECONDS
    ]
    for port in stale:
        registry.pop(port, None)


def _allocate_offline_port(port: int) -> int:
    if fcntl is None:
        raise OSError("could not reserve a Galaxy Merge server port")
    import time

    with _OFFLINE_ALLOC_LOCK:
        with _with_offline_lock() as fd:  # noqa: F841
            registry = _read_offline_registry()
            if not isinstance(registry, dict):
                registry = {}
            _sweep_offline_registry(registry)

            desired = port if port > 0 else None
            candidates = [desired] if desired else list(range(_OFFLINE_RANGE_START, _OFFLINE_RANGE_START + _OFFLINE_RANGE_SIZE))
            for candidate in candidates:
                candidate_key = str(candidate)
                in_use = isinstance(registry.get(candidate_key), dict) and bool(registry[candidate_key].get("active", False))
                if in_use:
                    if desired is not None:
                        break
                    continue
                registry[candidate_key] = {
                    "active": True,
                    "t": time.time(),
                    "pid": os.getpid(),
                }
                _write_offline_registry(registry)
                return candidate

    raise OSError(f"could not reserve offline port {port}")


def _release_offline_port(port: int) -> None:
    if fcntl is None:
        return
    with _OFFLINE_ALLOC_LOCK:
        with _with_offline_lock() as fd:  # noqa: F841
            registry = _read_offline_registry()
            if not isinstance(registry, dict):
                return
            registry.pop(str(port), None)
            _write_offline_registry(registry)


def reserve_socket(port: int = 0, start: int = 7419) -> socket.socket:
    candidates = [port] if port > 0 else [0, *range(start, start + 100)]
    for candidate in candidates:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("127.0.0.1", candidate))
            sock.listen(128)
            sock.set_inheritable(True)
            return sock
        except OSError:
            continue

    if not _offline_socket_enabled():
        raise OSError("could not reserve a Galaxy Merge server port")

    offline_port = _allocate_offline_port(port)
    return _OfflineSocket(offline_port)


def find_free_port(start: int = 7419) -> int:
    sock = reserve_socket(0, start)
    try:
        return sock.getsockname()[1]
    finally:
        sock.close()
