"""
Backend runtime correctness tests for Galaxy Merge.

Covers: port allocation, crash recovery, double-shutdown prevention,
session isolation, WebSocket broadcast safety, goal cancellation,
safety boundaries, session-scoped notes injection, and atomic writes.
"""


import pytest

pytestmark = [pytest.mark.integration]


import asyncio
import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from galaxy_merge.app.ports import reserve_socket, find_free_port
from galaxy_merge.core.session import Session, init_gm_dir, detect_workroot
from galaxy_merge.core.events import EventLog
from galaxy_merge.core.locks import (
    FileLock,
    LockTimeout,
    atomic_write,
    atomic_append,
    LockManager,
)
from galaxy_merge.core.concurrency import (
    file_hash,
    detect_file_conflict,
    cleanup_stale_sessions,
    register_active_session,
    read_active_port_map,
    write_heartbeat,
    upgrade_concurrency,
)
from galaxy_merge.tools.notes_tools import (
    get_injected_notes,
    clear_goal_injections,
    _injected_by_gm_dir,
)


# =============================================================================
# Port Allocation
# =============================================================================

class TestPortAllocation:
    def test_find_free_port_returns_localhost_port(self):
        port = find_free_port()
        assert 1024 <= port <= 65535

    def test_find_free_port_avoids_busy_port(self):
        busy = reserve_socket(0)
        try:
            busy_port = busy.getsockname()[1]
            port = find_free_port(start=busy_port)
            assert port != busy_port
        finally:
            busy.close()

    def test_reserve_socket_binds_localhost_only(self):
        sock = reserve_socket(0)
        try:
            addr, port = sock.getsockname()
            assert addr == "127.0.0.1"
            assert port > 0
        finally:
            sock.close()

    def test_concurrent_port_allocation_no_collision(self):
        ports_acquired: list[int] = []
        errors: list[str] = []
        lock = threading.Lock()

        def acquire_port():
            try:
                sock = reserve_socket(0)
                port = sock.getsockname()[1]
                with lock:
                    ports_acquired.append(port)
                time.sleep(0.05)
                sock.close()
            except Exception as e:
                with lock:
                    errors.append(str(e))

        threads = [threading.Thread(target=acquire_port) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert not errors, f"Port allocation errors: {errors}"
        assert len(ports_acquired) == 10
        assert len(set(ports_acquired)) == 10, "All ports must be unique"

    def test_reserve_socket_specific_port(self):
        sock = reserve_socket(0)
        try:
            port = sock.getsockname()[1]
        finally:
            sock.close()

        sock2 = reserve_socket(port)
        try:
            assert sock2.getsockname()[1] == port
        finally:
            sock2.close()


# =============================================================================
# Crash Recovery
# =============================================================================

class TestCrashRecovery:
    def test_state_json_readable_after_crash(self, tmp_path):
        init_gm_dir(tmp_path)
        session = Session(tmp_path)
        session.save_state()

        state_path = session.session_dir / "state.json"
        assert state_path.exists()
        state = json.loads(state_path.read_text())
        assert state["session_id"] == session.session_id
        assert state["status"] == "running"

    def test_events_jsonl_readable_after_crash(self, tmp_path):
        init_gm_dir(tmp_path)
        session = Session(tmp_path)
        session.save_state()
        session.event_log.emit("test_event", session_id=session.session_id, data="ok")

        events = session.event_log.replay()
        assert len(events) == 1
        assert events[0]["event"] == "test_event"

    def test_mark_crashed_persists_state(self, tmp_path):
        init_gm_dir(tmp_path)
        session = Session(tmp_path)
        session.save_state()
        session.mark_crashed()

        state = json.loads(session.state_path.read_text())
        assert state["status"] == "crashed"
        assert state["active"] is False

    def test_session_dir_structure_after_init(self, tmp_path):
        init_gm_dir(tmp_path)
        session = Session(tmp_path)
        session.save_state()

        for fname in ["transcript.jsonl", "council.jsonl", "tool_calls.jsonl",
                       "safety.jsonl", "provider_events.jsonl", "compaction.jsonl"]:
            assert (session.session_dir / fname).exists(), f"Missing {fname}"

        assert (session.session_dir / "diffs").is_dir()
        assert (session.session_dir / "artifacts").is_dir()


# =============================================================================
# Double-Shutdown Prevention
# =============================================================================

class TestDoubleShutdown:
    def test_shutdown_idempotent(self, tmp_path):
        init_gm_dir(tmp_path)
        session = Session(tmp_path)
        session.save_state()

        from galaxy_merge.app.launcher import Launcher
        launcher = Launcher()
        launcher.session = session
        launcher.server_info = None

        launcher._shutdown()
        state1 = json.loads(session.state_path.read_text())

        launcher._shutdown()
        state2 = json.loads(session.state_path.read_text())

        assert state1 == state2, "Double shutdown should be idempotent"

    def test_shutdown_closes_socket(self, tmp_path):
        init_gm_dir(tmp_path)
        session = Session(tmp_path)
        session.save_state()

        from galaxy_merge.app.launcher import Launcher
        launcher = Launcher()
        launcher.session = session

        mock_socket = MagicMock()
        mock_server = MagicMock()
        mock_server._socket = mock_socket
        launcher.server_info = {"server": mock_server, "port": 12345, "url": "http://localhost:12345"}

        launcher._shutdown()
        mock_socket.close.assert_called_once()
        assert mock_server._socket is None


# =============================================================================
# Session Isolation
# =============================================================================

class TestSessionIsolation:
    def test_unique_session_ids(self, tmp_path):
        init_gm_dir(tmp_path)
        s1 = Session(tmp_path)
        s2 = Session(tmp_path)
        assert s1.session_id != s2.session_id

    def test_session_directories_isolated(self, tmp_path):
        init_gm_dir(tmp_path)
        s1 = Session(tmp_path)
        s1.save_state()
        s2 = Session(tmp_path)
        s2.save_state()

        assert s1.session_dir != s2.session_dir
        assert s1.session_dir.exists()
        assert s2.session_dir.exists()

    def test_session_state_independent(self, tmp_path):
        init_gm_dir(tmp_path)
        s1 = Session(tmp_path)
        s1.save_state()
        s2 = Session(tmp_path)
        s2.save_state()

        s1.set_goal("goal A")
        s2.set_goal("goal B")

        state1 = json.loads(s1.state_path.read_text())
        state2 = json.loads(s2.state_path.read_text())
        assert state1["goal"] == "goal A"
        assert state2["goal"] == "goal B"

    def test_resume_session_loads_existing_state(self, tmp_path):
        init_gm_dir(tmp_path)
        s1 = Session(tmp_path)
        s1.set_goal("original goal")

        s2 = Session(tmp_path, session_id=s1.session_id)
        assert s2.session_id == s1.session_id
        state = json.loads(s2.state_path.read_text())
        assert state["goal"] == "original goal"


# =============================================================================
# Session-Scoped Notes Injection
# =============================================================================

class TestSessionScopedNotes:
    def test_injection_is_per_gm_dir(self, tmp_path):
        init_gm_dir(tmp_path)
        gm_a = tmp_path / "a" / ".gm"
        gm_b = tmp_path / "b" / ".gm"
        gm_a.mkdir(parents=True)
        gm_b.mkdir(parents=True)

        _injected_by_gm_dir.pop(str(gm_a), None)
        _injected_by_gm_dir.pop(str(gm_b), None)

        _injected_by_gm_dir.setdefault(str(gm_a), []).append("note1")
        _injected_by_gm_dir.setdefault(str(gm_b), []).append("note2")

        assert get_injected_notes(gm_a) == ["note1"]
        assert get_injected_notes(gm_b) == ["note2"]

        clear_goal_injections(gm_a)
        assert get_injected_notes(gm_a) == []
        assert get_injected_notes(gm_b) == ["note2"]

        _injected_by_gm_dir.pop(str(gm_a), None)
        _injected_by_gm_dir.pop(str(gm_b), None)

    def test_clear_does_not_affect_other_sessions(self, tmp_path):
        gm_a = tmp_path / "a"
        gm_b = tmp_path / "b"

        _injected_by_gm_dir[str(gm_a)] = ["note1"]
        _injected_by_gm_dir[str(gm_b)] = ["note2"]

        clear_goal_injections(gm_a)

        assert get_injected_notes(gm_a) == []
        assert get_injected_notes(gm_b) == ["note2"]

        _injected_by_gm_dir.pop(str(gm_a), None)
        _injected_by_gm_dir.pop(str(gm_b), None)


# =============================================================================
# EventLog Thread Safety
# =============================================================================

class TestEventLogConcurrency:
    def test_concurrent_emits_produce_valid_jsonl(self, tmp_path):
        events_path = tmp_path / "events.jsonl"
        log = EventLog(events_path)

        errors: list[str] = []
        lock = threading.Lock()

        def emit_batch(batch_id: int):
            try:
                for i in range(20):
                    log.emit(f"event_{batch_id}_{i}", session_id=f"sess_{batch_id}")
            except Exception as e:
                with lock:
                    errors.append(str(e))

        threads = [threading.Thread(target=emit_batch, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)

        assert not errors, f"Emit errors: {errors}"
        records = log.replay()
        assert len(records) == 100

        for rec in records:
            assert "event" in rec
            assert "time" in rec
            assert "session_id" in rec

    def test_replay_during_emit_is_safe(self, tmp_path):
        events_path = tmp_path / "events.jsonl"
        log = EventLog(events_path)
        stop = threading.Event()
        replay_results: list[int] = []

        def emitter():
            i = 0
            while not stop.is_set():
                log.emit(f"event_{i}")
                i += 1

        def replayer():
            while not stop.is_set():
                try:
                    records = log.replay()
                    replay_results.append(len(records))
                except Exception:
                    replay_results.append(-1)

        t1 = threading.Thread(target=emitter)
        t2 = threading.Thread(target=replayer)
        t1.start()
        t2.start()
        time.sleep(0.2)
        stop.set()
        t1.join(timeout=5)
        t2.join(timeout=5)

        assert all(r >= 0 for r in replay_results), "Replay should never fail"


# =============================================================================
# Atomic Write Correctness
# =============================================================================

class TestAtomicWrites:
    def test_atomic_write_creates_file(self, tmp_path):
        target = tmp_path / "test.json"
        atomic_write(target, '{"key": "value"}')
        assert target.exists()
        assert json.loads(target.read_text()) == {"key": "value"}

    def test_atomic_write_overwrites_safely(self, tmp_path):
        target = tmp_path / "test.json"
        atomic_write(target, "first")
        atomic_write(target, "second")
        assert target.read_text() == "second"

    def test_atomic_append_produces_valid_jsonl(self, tmp_path):
        path = tmp_path / "events.jsonl"
        for i in range(50):
            atomic_append(path, json.dumps({"i": i}))

        records = []
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
        assert len(records) == 50
        assert records[0]["i"] == 0
        assert records[-1]["i"] == 49

    def test_atomic_write_concurrent_no_corruption(self, tmp_path):
        target = tmp_path / "shared.json"
        errors: list[str] = []
        lock = threading.Lock()

        def writer(writer_id: int):
            try:
                for i in range(20):
                    atomic_write(target, json.dumps({"writer": writer_id, "i": i}))
            except Exception as e:
                with lock:
                    errors.append(str(e))

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)

        assert not errors
        content = target.read_text()
        data = json.loads(content)
        assert "writer" in data
        assert "i" in data


# =============================================================================
# Conflict Detection
# =============================================================================

class TestConflictDetection:
    def test_no_conflict_when_unchanged(self, tmp_path):
        path = tmp_path / "file.txt"
        path.write_text("hello")
        h = file_hash(path)
        result = detect_file_conflict(path, h)
        assert result["conflict"] is False

    def test_conflict_when_content_changes(self, tmp_path):
        path = tmp_path / "file.txt"
        path.write_text("hello")
        h = file_hash(path)
        path.write_text("world")
        result = detect_file_conflict(path, h)
        assert result["conflict"] is True
        assert result["current_hash"] != h

    def test_no_conflict_on_new_file_when_expected_hash_empty(self, tmp_path):
        path = tmp_path / "file.txt"
        result = detect_file_conflict(path, "")
        assert result["conflict"] is False

    def test_no_conflict_on_missing_file_with_expected_hash(self, tmp_path):
        path = tmp_path / "file.txt"
        result = detect_file_conflict(path, "somehash")
        assert result["conflict"] is False

    def test_hash_stable_for_same_content(self, tmp_path):
        path = tmp_path / "file.txt"
        path.write_text("stable content")
        h1 = file_hash(path)
        h2 = file_hash(path)
        assert h1 == h2


# =============================================================================
# WorkRoot Detection
# =============================================================================

class TestWorkRootDetection:
    def test_detects_git_project(self, tmp_path):
        (tmp_path / ".git").mkdir()
        result = detect_workroot(tmp_path)
        assert result == tmp_path

    def test_detects_pyproject_toml(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[project]\nname='test'")
        result = detect_workroot(tmp_path)
        assert result == tmp_path

    def test_rejects_system_root(self):
        result = detect_workroot(Path("/usr"))
        assert result is None

    def test_rejects_home_directory(self):
        result = detect_workroot(Path.home())
        assert result is None

    def test_rejects_desktop(self):
        result = detect_workroot(Path.home() / "Desktop")
        assert result is None

    def test_walks_up_to_find_project(self, tmp_path):
        (tmp_path / ".git").mkdir()
        deep = tmp_path / "src" / "components"
        deep.mkdir(parents=True)
        result = detect_workroot(deep)
        assert result == tmp_path

    def test_walks_up_past_deep_subdirs(self, tmp_path):
        (tmp_path / ".git").mkdir()
        deep = tmp_path / "a" / "b" / "c"
        deep.mkdir(parents=True)
        result = detect_workroot(deep)
        assert result == tmp_path


# =============================================================================
# Stale Session Cleanup
# =============================================================================

class TestStaleSessionCleanup:
    def test_cleanup_removes_old_heartbeats(self, tmp_path):
        init_gm_dir(tmp_path)
        gm_dir = tmp_path / ".gm"
        hb_dir = gm_dir / "sessions" / "heartbeats"
        hb_dir.mkdir(parents=True)

        old_hb = hb_dir / "old_session.hb"
        old_hb.write_text(str(time.time() - 600))

        stale = cleanup_stale_sessions(gm_dir, max_age=300)
        assert "old_session" in stale
        assert not old_hb.exists()

    def test_cleanup_preserves_recent_heartbeats(self, tmp_path):
        init_gm_dir(tmp_path)
        gm_dir = tmp_path / ".gm"
        hb_dir = gm_dir / "sessions" / "heartbeats"
        hb_dir.mkdir(parents=True)

        recent_hb = hb_dir / "recent_session.hb"
        recent_hb.write_text(str(time.time()))

        stale = cleanup_stale_sessions(gm_dir, max_age=300)
        assert "recent_session" not in stale
        assert recent_hb.exists()

    def test_cleanup_removes_stale_session_dirs(self, tmp_path):
        init_gm_dir(tmp_path)
        gm_dir = tmp_path / ".gm"
        hb_dir = gm_dir / "sessions" / "heartbeats"
        hb_dir.mkdir(parents=True)

        session_dir = gm_dir / "sessions" / "stale_session"
        session_dir.mkdir(parents=True)
        (session_dir / "state.json").write_text("{}")

        hb = hb_dir / "stale_session.hb"
        hb.write_text(str(time.time() - 600))

        cleanup_stale_sessions(gm_dir, max_age=300)
        assert not session_dir.exists()


# =============================================================================
# Safety Boundary
# =============================================================================

class TestSafetyBoundary:
    def test_path_policy_blocks_system_paths(self):
        from galaxy_merge.safety.path_policy import PathPolicy
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            wp = Path(td)
            policy = PathPolicy(wp)
            result = policy.check_write(Path("/etc/passwd"))
            assert result["decision"] == "block"

    def test_governor_blocks_outside_workroot(self, tmp_path):
        from galaxy_merge.safety.governor import SafetyGovernor
        from galaxy_merge.safety.audit import SafetyAudit
        init_gm_dir(tmp_path)
        audit = SafetyAudit(tmp_path / ".gm" / "safety" / "blocked_actions.jsonl")
        gov = SafetyGovernor(tmp_path, tmp_path / ".gm", audit)
        result = gov.check_path_write("/tmp/evil.txt")
        assert result["decision"] == "block"

    def test_governor_allows_inside_workroot(self, tmp_path):
        from galaxy_merge.safety.governor import SafetyGovernor
        from galaxy_merge.safety.audit import SafetyAudit
        init_gm_dir(tmp_path)
        audit = SafetyAudit(tmp_path / ".gm" / "safety" / "blocked_actions.jsonl")
        gov = SafetyGovernor(tmp_path, tmp_path / ".gm", audit)
        result = gov.check_path_write(str(tmp_path / "src" / "file.txt"))
        assert result["decision"] == "allow"

    def test_command_policy_blocks_dangerous_commands(self):
        from galaxy_merge.safety.command_policy import CommandPolicy
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            cp = CommandPolicy(Path(td))
            result = cp.check("sudo rm -rf /")
            assert result["decision"] == "block"

    def test_credential_detection_in_text(self):
        from galaxy_merge.safety.credential_policy import CredentialPolicy
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            policy = CredentialPolicy(Path(td))
            findings = policy.scan_text("api_key=sk-1234567890abcdef1234567890abcdef")
            assert len(findings) > 0

    def test_credential_redaction(self):
        from galaxy_merge.safety.credential_policy import CredentialPolicy
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            policy = CredentialPolicy(Path(td))
            redacted = policy.redact("token: ghp_123456789012345678901234567890123456")
            assert "123456789012345678901234567890123456" not in redacted
            assert "REDACTED" in redacted


# =============================================================================
# Lock Manager
# =============================================================================

class TestLockManager:
    def test_acquire_and_release(self, tmp_path):
        gm_dir = tmp_path / ".gm"
        gm_dir.mkdir()
        mgr = LockManager(gm_dir)
        assert mgr.acquire("test_resource")
        mgr.release("test_resource")

    def test_locked_context_manager(self, tmp_path):
        gm_dir = tmp_path / ".gm"
        gm_dir.mkdir()
        mgr = LockManager(gm_dir)
        with mgr.locked("resource1"):
            pass

    def test_concurrent_lock_contention(self, tmp_path):
        gm_dir = tmp_path / ".gm"
        gm_dir.mkdir()
        results: list[str] = []
        lock = threading.Lock()

        def worker(name: str):
            mgr = LockManager(gm_dir)
            with mgr.locked("shared"):
                with lock:
                    results.append(f"{name}_start")
                time.sleep(0.01)
                with lock:
                    results.append(f"{name}_end")

        threads = [threading.Thread(target=worker, args=(f"w{i}",)) for i in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert len(results) == 6
        for i in range(0, 6, 2):
            name = results[i].split("_")[0]
            assert results[i + 1] == f"{name}_end", "Lock should be held sequentially"


# =============================================================================
# File Lock
# =============================================================================

class TestFileLock:
    def test_basic_lock_unlock(self, tmp_path):
        lock_path = tmp_path / "test.lock"
        with FileLock(lock_path, timeout=5.0):
            assert lock_path.exists()

    def test_lock_timeout_raises(self, tmp_path):
        lock_path = tmp_path / "test.lock"

        def hold_lock():
            with FileLock(lock_path, timeout=30.0):
                time.sleep(0.5)

        t = threading.Thread(target=hold_lock)
        t.start()
        time.sleep(0.05)

        with pytest.raises(LockTimeout):
            with FileLock(lock_path, timeout=0.2):
                pass

        t.join(timeout=3)


# =============================================================================
# Parallel Session File Conflict
# =============================================================================

class TestParallelSessionConflict:
    def test_hash_before_write_detects_conflict(self, tmp_path):
        init_gm_dir(tmp_path)
        target = tmp_path / "shared.txt"
        target.write_text("original")

        from galaxy_merge.core.concurrency import file_hash
        h = file_hash(target)

        target.write_text("modified by session A")

        from galaxy_merge.tools.file_tools import _file_hash
        current = _file_hash(target)
        assert current != h

    def test_hash_before_write_detects_change(self, tmp_path):
        init_gm_dir(tmp_path)
        target = tmp_path / "contested.txt"
        target.write_text("original content")

        from galaxy_merge.core.concurrency import file_hash
        h = file_hash(target)

        from galaxy_merge.tools.file_tools import _file_hash
        assert _file_hash(target) == h

        target.write_text("modified by someone else")
        assert _file_hash(target) != h

    def test_file_lock_prevents_concurrent_write(self, tmp_path):
        from galaxy_merge.core.locks import FileLock, atomic_write
        target = tmp_path / "locked.txt"
        target.write_text("v1")

        lock_path = target.with_suffix(".lock")
        with FileLock(lock_path, timeout=5.0):
            content = target.read_text()
            assert content == "v1"
            atomic_write(target, "v2", _nested_lock=True)

        assert target.read_text() == "v2"


# =============================================================================
# WebSocket Broadcast Safety
# =============================================================================

class TestWebSocketBroadcastSafety:
    @pytest.mark.asyncio
    async def test_broadcast_with_no_clients(self):
        from galaxy_merge.app.server import SessionServer
        from galaxy_merge.core.session import Session, init_gm_dir

        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            init_gm_dir(tmp)
            session = Session(tmp)
            session.save_state()

            server = SessionServer(session, port=0)
            try:
                await server._broadcast({"type": "test"})
            finally:
                if server._socket:
                    server._socket.close()

    @pytest.mark.asyncio
    async def test_broadcast_handles_dead_client(self):
        from galaxy_merge.app.server import SessionServer
        from galaxy_merge.core.session import Session, init_gm_dir

        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            init_gm_dir(tmp)
            session = Session(tmp)
            session.save_state()

            server = SessionServer(session, port=0)
            try:
                dead_ws = AsyncMock()
                dead_ws.send_json = AsyncMock(side_effect=ConnectionResetError("closed"))
                server._ws_clients.append(dead_ws)

                good_ws = AsyncMock()
                server._ws_clients.append(good_ws)

                await server._broadcast({"type": "test"})

                dead_ws.send_json.assert_called_once()
                good_ws.send_json.assert_called_once()
                assert dead_ws not in server._ws_clients
                assert good_ws in server._ws_clients
            finally:
                if server._socket:
                    server._socket.close()

    @pytest.mark.asyncio
    async def test_replay_from_cursor_sends_ordered_events(self):
        from galaxy_merge.app.server import SessionServer
        from galaxy_merge.core.session import Session, init_gm_dir

        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            init_gm_dir(tmp)
            session = Session(tmp)
            session.save_state()
            for i in range(5):
                session.event_log.emit("step", session_id=session.session_id, step=i)

            server = SessionServer(session, port=0)
            try:
                ws = AsyncMock()

                await server._send_replay(ws, since=2, limit=10)

                payloads = [call.args[0] for call in ws.send_json.call_args_list]
                assert payloads[0]["event"] == "step"
                assert payloads[0]["step"] == 2
                assert payloads[-1] == {
                    "type": "events_replayed",
                    "count": 3,
                    "since": 2,
                }
            finally:
                if server._socket:
                    server._socket.close()


class TestEventsPagination:
    def test_events_payload_with_offset_and_limit(self):
        from galaxy_merge.app.server import SessionServer
        from galaxy_merge.core.session import Session, init_gm_dir

        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            init_gm_dir(tmp)
            session = Session(tmp)
            session.save_state()
            for i in range(10):
                session.event_log.emit("log", session_id=session.session_id, index=i)

            server = SessionServer(session, port=0)
            events, total, next_offset = server._events_payload(limit=4, offset=3)
            assert total == 10
            assert len(events) == 4
            assert next_offset == 7
            assert events[0]["index"] == 3

            redacted, _, _ = server._events_payload(limit=2, offset=0, redact=False)
            assert redacted[0]["event"] == "log"


    def test_events_endpoint_defaults_to_legacy_list_shape(self):
        from fastapi.testclient import TestClient
        from galaxy_merge.app.server import SessionServer
        from galaxy_merge.core.session import Session, init_gm_dir

        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            init_gm_dir(tmp)
            session = Session(tmp)
            session.save_state()
            for i in range(3):
                session.event_log.emit("log", session_id=session.session_id, index=i)

            server = SessionServer(session, port=0)
            client = TestClient(server.app)
            response = client.get("/api/events")

            assert response.status_code == 200
            payload = response.json()
            assert isinstance(payload, list)
            assert payload[-1]["index"] == 2


class TestSessionServerResume:
    def test_resume_refuses_completed_session(self):
        from fastapi.testclient import TestClient
        from galaxy_merge.app.server import SessionServer
        from galaxy_merge.core.session import Session, init_gm_dir

        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            init_gm_dir(tmp)
            session = Session(tmp)
            session.mark_completed()

            server = SessionServer(session, port=0)
            response = TestClient(server.app).post("/api/resume")

            assert response.status_code == 409

    def test_resume_restores_crashed_session(self):
        from fastapi.testclient import TestClient
        from galaxy_merge.app.server import SessionServer
        from galaxy_merge.core.session import Session, init_gm_dir

        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            init_gm_dir(tmp)
            session = Session(tmp)
            session.mark_crashed("boom")

            server = SessionServer(session, port=0)
            response = TestClient(server.app).post("/api/resume")

            assert response.status_code == 200
            assert response.json()["status"] == "resumed"
            state = json.loads((tmp / ".gm" / "sessions" / session.session_id / "state.json").read_text())
            assert state["status"] == "running"


class TestPortMapState:
    def test_register_active_session_records_port_mapping(self, tmp_path):
        init_gm_dir(tmp_path)
        gm_dir = tmp_path / ".gm"
        register_active_session(gm_dir, "sess_a", port=12345, pid=777)
        mapping = read_active_port_map(gm_dir)
        assert "sess_a" in mapping
        assert mapping["sess_a"]["port"] == 12345
        assert mapping["sess_a"]["pid"] == 777

    def test_cleanup_stale_sessions_removes_port_map_entry(self, tmp_path):
        init_gm_dir(tmp_path)
        gm_dir = tmp_path / ".gm"
        hb = gm_dir / "sessions" / "heartbeats"
        hb.mkdir(parents=True)

        register_active_session(gm_dir, "stale", port=23456, pid=111)
        (hb / "stale.hb").write_text(str(time.time() - 600))

        mapping_before = read_active_port_map(gm_dir)
        assert "stale" in mapping_before

        stale = cleanup_stale_sessions(gm_dir, max_age=300)
        mapping_after = read_active_port_map(gm_dir)
        assert "stale" in stale
        assert "stale" not in mapping_after


# =============================================================================
# Self-Codebase Detection
# =============================================================================

class TestSelfCodebaseDetection:
    def test_detects_own_codebase(self, tmp_path):
        from galaxy_merge.app.launcher import _is_inside_galaxy_merge_codebase
        install_dir = Path(__file__).resolve().parent.parent.parent
        result = _is_inside_galaxy_merge_codebase(install_dir)
        assert result is True

    def test_allows_external_project(self, tmp_path):
        from galaxy_merge.app.launcher import _is_inside_galaxy_merge_codebase
        result = _is_inside_galaxy_merge_codebase(tmp_path)
        assert result is False


# =============================================================================
# Project JSON Validation
# =============================================================================

class TestProjectJsonValidation:
    def test_valid_project_json(self, tmp_path):
        from galaxy_merge.core.session import _init_project_json
        gm_dir = tmp_path / ".gm"
        gm_dir.mkdir()
        _init_project_json(gm_dir, tmp_path)

        data = json.loads((gm_dir / "project.json").read_text())
        assert data["schema_version"] == 1
        assert data["project_id"].startswith("gmproj_")
        assert data["workroot"] == str(tmp_path)

    def test_corrupted_project_json_detected(self, tmp_path):
        from galaxy_merge.core.session import _validate_project_json
        gm_dir = tmp_path / ".gm"
        gm_dir.mkdir()
        (gm_dir / "project.json").write_text("not json {{{")
        errors = _validate_project_json(gm_dir / "project.json")
        assert len(errors) > 0
        assert "invalid JSON" in errors[0]
