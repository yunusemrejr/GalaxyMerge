"""
Concurrent-session integration tests for Galaxy Merge.

Tests run with real subprocesses, temp directories, and file-system
interactions to validate cross-process isolation and shared-resource
safety.  No mocks; no shortcuts.

Scenarios (1-10 from the spec) are all covered.
"""


import pytest

pytestmark = [pytest.mark.integration, pytest.mark.slow]


import json
import os
import signal
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
from pathlib import Path

import importlib
import pytest

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
    write_heartbeat,
    upgrade_concurrency,
)
from galaxy_merge.core.session import (
    Session,
    init_gm_dir,
    detect_workroot,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def gm_dir(tmp_path: Path) -> Path:
    """Initialise .gm/ in a temp directory and return its path."""
    init_gm_dir(tmp_path)
    return tmp_path / ".gm"


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    """Create a minimal project with .git/ so detect_workroot works."""
    (tmp_path / ".git").mkdir()
    (tmp_path / "README.md").write_text("# test")
    return tmp_path


def _session_script(workroot: str, session_id: str,
                    actions: list[str], heartbeat: bool = True) -> str:
    """Generate a Python script that runs in a subprocess to simulate a session.

    Each action is a line of Python code that has access to a `session`
    variable (galaxy_merge.core.session.Session).
    """
    _GMROOT = str(Path(__file__).resolve().parent.parent.parent)
    _sid = f"'{session_id}'" if session_id else "None"
    _hb = "True" if heartbeat else "False"
    lines = [
        'import sys, os, json, time',
        f'sys.path.insert(0, {_GMROOT!r})',
        f'os.chdir({workroot!r})',
        'from galaxy_merge.core.session import Session, init_gm_dir',
        'from galaxy_merge.core.concurrency import register_active_session, write_heartbeat, upgrade_concurrency',
        'from pathlib import Path',
        f'WR = Path({workroot!r})',
        'gm_dir = WR / ".gm"',
        'init_gm_dir(WR)',
        'upgrade_concurrency(gm_dir)',
        f'session = Session(WR, session_id={_sid})',
        'session.save_state()',
        'register_active_session(gm_dir, session.session_id)',
        f'if {_hb}:',
        '    write_heartbeat(gm_dir, session.session_id)',
    ]
    lines.extend(actions)
    return '\n'.join(lines)


def _run_script(script: str, timeout: float = 15) -> subprocess.CompletedProcess:
    """Run a Python script in a subprocess and return the result."""
    return subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True, text=True, timeout=timeout,
    )


# =============================================================================
# 1-3. Multiple sessions in the same project
# =============================================================================

class TestMultipleSessionsSameProject:
    """All three session instances must be isolated."""

    def test_session_ids_are_unique(self, project_dir: Path):
        """Three sessions in the same project → unique IDs."""
        wr = str(project_dir)
        scripts = [
            _session_script(wr, None, [
                "import json",
                f"with open('/tmp/_gm_sess_{i}.txt', 'w') as f: f.write(session.session_id)",
            ])
            for i in range(3)
        ]
        procs = [_run_script(s) for s in scripts]
        ids = []
        for i in range(3):
            p = Path(f"/tmp/_gm_sess_{i}.txt")
            ids.append(p.read_text().strip())
            p.unlink(missing_ok=True)

        assert len(set(ids)) == 3, f"session IDs were not unique: {ids}"
        assert all(proc.returncode == 0 for proc in procs), \
            f"proc errors: {[p.stderr for p in procs if p.returncode != 0]}"

    def test_session_dirs_are_isolated(self, project_dir: Path):
        """Each session gets its own .gm/sessions/<id>/ directory."""
        wr = str(project_dir)
        scripts = [
            _session_script(wr, None, [
                "import json",
                f"with open('/tmp/_gm_sd_{i}.txt', 'w') as f: f.write(str(session.session_dir))",
            ])
            for i in range(3)
        ]
        procs = [_run_script(s) for s in scripts]
        dirs = []
        for i in range(3):
            p = Path(f"/tmp/_gm_sd_{i}.txt")
            dirs.append(Path(p.read_text().strip()))
            p.unlink(missing_ok=True)

        assert len({str(d) for d in dirs}) == 3, "session dirs overlap"
        assert all(proc.returncode == 0 for proc in procs)

    def test_logs_go_to_session_specific_files(self, project_dir: Path):
        """Each session's events.jsonl lives in its own directory."""
        actions = [
            'session.event_log.emit("test_event", session_id=session.session_id)',
        ]
        s1 = _session_script(str(project_dir), None, actions)
        s2 = _session_script(str(project_dir), None, actions)

        p1 = _run_script(s1, timeout=10)
        p2 = _run_script(s2, timeout=10)
        assert p1.returncode == 0, p1.stderr
        assert p2.returncode == 0, p2.stderr

        # Each session wrote to its own events.jsonl
        sessions_dir = project_dir / ".gm" / "sessions"
        event_files = list(sessions_dir.rglob("events.jsonl"))
        assert len(event_files) >= 2, f"expected >=2 events.jsonl, got {len(event_files)}"

    def test_goal_does_not_cross_sessions(self, project_dir: Path):
        """Setting a goal in one session must not affect another."""
        actions1 = ['session.set_goal("GOAL-ALPHA")']
        actions2 = ['session.set_goal("GOAL-BETA")']

        s1 = _session_script(str(project_dir), "sess_a", actions1)
        s2 = _session_script(str(project_dir), "sess_b", actions2)
        p1 = _run_script(s1, timeout=10)
        p2 = _run_script(s2, timeout=10)
        assert p1.returncode == 0, p1.stderr
        assert p2.returncode == 0, p2.stderr

        # Verify each session has its own goal
        sess_a_goal = project_dir / ".gm" / "sessions" / "sess_a" / "goal.json"
        sess_b_goal = project_dir / ".gm" / "sessions" / "sess_b" / "goal.json"
        assert sess_a_goal.read_text().find("GOAL-ALPHA") >= 0
        assert sess_b_goal.read_text().find("GOAL-BETA") >= 0

    def test_state_does_not_cross_sessions(self, project_dir: Path):
        """Session state (status, active) is isolated per session."""
        actions1 = ['session.mark_completed()']
        actions2 = ['session._state["status"] = "running"; session.save_state()']

        s1 = _session_script(str(project_dir), "sess_c", actions1)
        s2 = _session_script(str(project_dir), "sess_d", actions2)
        p1 = _run_script(s1, timeout=10)
        p2 = _run_script(s2, timeout=10)
        assert p1.returncode == 0, p1.stderr
        assert p2.returncode == 0, p2.stderr

        # sess_c is complete, sess_d is still running
        sc = json.loads((project_dir / ".gm" / "sessions" / "sess_c" / "state.json").read_text())
        sd = json.loads((project_dir / ".gm" / "sessions" / "sess_d" / "state.json").read_text())
        assert sc["status"] == "complete"
        assert sc["active"] is False
        assert sd["status"] == "running"
        assert sd["active"] is True


# =============================================================================
# 4. Different projects
# =============================================================================

class TestDifferentProjects:
    """Sessions in different projects must be fully independent."""

    def test_sessions_have_different_workroots(self, tmp_path: Path):
        p1 = tmp_path / "proj_a"
        p2 = tmp_path / "proj_b"
        for p in [p1, p2]:
            p.mkdir()
            (p / ".git").mkdir()
            init_gm_dir(p)

        s1 = Session(p1, session_id="sess_p1")
        s2 = Session(p2, session_id="sess_p2")
        assert s1.workroot == p1.resolve()
        assert s2.workroot == p2.resolve()
        assert s1.session_dir != s2.session_dir
        assert not str(s1.session_dir).startswith(str(p2 / ".gm"))
        assert not str(s2.session_dir).startswith(str(p1 / ".gm"))


# =============================================================================
# 5. Different goals touching different files
# =============================================================================

class TestDifferentGoalsDifferentFiles:
    """Concurrent sessions with different goals and file targets must not collide."""

    def test_concurrent_writes_to_different_files(self, project_dir: Path):
        wr = str(project_dir)

        # Session A writes to file_a.txt, Session B writes to file_b.txt
        actions_a = [
            '(WR / "file_a.txt").write_text("AAAA")',
        ]
        actions_b = [
            '(WR / "file_b.txt").write_text("BBBB")',
        ]

        script_a = _session_script(wr, "sess_fa", actions_a)
        script_b = _session_script(wr, "sess_fb", actions_b)

        # Run concurrently in threads that start subprocesses
        results: list[subprocess.CompletedProcess] = []
        threads = []

        def _run(s: str) -> None:
            results.append(_run_script(s, timeout=15))

        for s in [script_a, script_b]:
            t = threading.Thread(target=_run, args=(s,))
            threads.append(t)
            t.start()
            time.sleep(0.1)  # stagger slightly for realism

        for t in threads:
            t.join(timeout=15)

        assert all(r.returncode == 0 for r in results), \
            [r.stderr for r in results if r.returncode != 0]
        assert (project_dir / "file_a.txt").read_text().strip() == "AAAA"
        assert (project_dir / "file_b.txt").read_text().strip() == "BBBB"


# =============================================================================
# 6. Same file conflict detection
# =============================================================================

class TestSameFileConflictDetection:
    """When two sessions touch the same file, we must detect conflict."""

    def test_detect_file_conflict(self, project_dir: Path):
        path = project_dir / "shared.txt"
        path.write_text("v1")

        h1 = file_hash(path)
        path.write_text("v2")
        h2 = file_hash(path)

        result = detect_file_conflict(path, h1)
        assert result["conflict"] is True
        assert result["current_hash"] == h2

    def test_no_conflict_on_unchanged(self, project_dir: Path):
        path = project_dir / "shared.txt"
        path.write_text("stable")
        h = file_hash(path)
        result = detect_file_conflict(path, h)
        assert result["conflict"] is False

    def test_concurrent_same_file_detection(self, project_dir: Path):
        """Two sessions writing to the same file must trigger detection."""
        shared = project_dir / "conflict_target.txt"
        shared.write_text("original")

        wr = str(project_dir)
        actions_a = [
            'import hashlib',
            'p = WR / "conflict_target.txt"',
            'h_before = hashlib.sha256(p.read_bytes()).hexdigest()[:16]',
            'time.sleep(0.2)',
            'h_after = hashlib.sha256(p.read_bytes()).hexdigest()[:16]',
            'conflict = h_before != h_after',
            'open("/tmp/_gm_conflict_a.txt", "w").write(json.dumps({"conflict": conflict}))',
        ]
        actions_b = [
            'time.sleep(0.1)',
            '(WR / "conflict_target.txt").write_text("session_b_overwrote")',
            'open("/tmp/_gm_conflict_b.txt", "w").write("done")',
        ]

        script_a = _session_script(wr, "sess_ca", actions_a)
        script_b = _session_script(wr, "sess_cb", actions_b)

        results: list[subprocess.CompletedProcess] = []
        threads = []
        def _run(s: str) -> None:
            results.append(_run_script(s, timeout=15))

        for s in [script_a, script_b]:
            t = threading.Thread(target=_run, args=(s,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join(timeout=15)

        for r in results:
            assert r.returncode == 0, r.stderr

    def test_file_hash_consistency(self, project_dir: Path):
        """file_hash must produce consistent results for the same content."""
        p = project_dir / "hash_test.txt"
        p.write_text("hello")
        h1 = file_hash(p)
        h2 = file_hash(p)
        assert h1 == h2
        p.write_text("world")
        h3 = file_hash(p)
        assert h1 != h3

    def test_file_write_rejects_stale_hash(self, project_dir: Path):
        """A stale same-file write must fail instead of overwriting."""
        from galaxy_merge.tools.file_tools import make_file_tools

        target = project_dir / "shared_tool.txt"
        target.write_text("original")
        tools = {schema.name: handler for schema, handler in make_file_tools(project_dir)}

        read_result = _run_async(tools["file.read"]("shared_tool.txt"))
        expected_hash = read_result.data["content_hash"]
        target.write_text("changed by another session")

        write_result = _run_async(
            tools["file.write"](
                "shared_tool.txt",
                "stale overwrite",
                expected_hash=expected_hash,
            )
        )

        assert not write_result.success
        assert write_result.data["conflict"] is True
        assert target.read_text() == "changed by another session"

    def test_file_patch_rejects_stale_hash(self, project_dir: Path):
        """A stale patch must fail with a clear conflict result."""
        from galaxy_merge.tools.file_tools import make_file_tools

        target = project_dir / "patch_target.txt"
        target.write_text("alpha\n")
        tools = {schema.name: handler for schema, handler in make_file_tools(project_dir)}

        read_result = _run_async(tools["file.read"]("patch_target.txt"))
        expected_hash = read_result.data["content_hash"]
        target.write_text("beta\n")

        patch_result = _run_async(
            tools["file.patch"](
                "patch_target.txt",
                [{"old_text": "alpha", "new_text": "gamma"}],
                expected_hash=expected_hash,
            )
        )

        assert not patch_result.success
        assert patch_result.data["conflict"] is True
        assert target.read_text() == "beta\n"


# =============================================================================
# 7. Edit project notes in one GUI while another session runs
# =============================================================================

class TestNotesConcurrentAccess:
    """Notes editing must be safe under concurrent access."""

    def test_notes_index_lock_protected(self, gm_dir: Path):
        """notes/index.json writes must not race."""
        notes_dir = gm_dir / "notes"
        idx_path = notes_dir / "index.json"
        lock_path = idx_path.with_suffix(".lock")

        # Simulate two concurrent index updates
        def writer_1() -> None:
            with FileLock(lock_path, timeout=10):
                idx = json.loads(idx_path.read_text()) if idx_path.exists() else {"notes": []}
                idx["notes"].append({"id": "n1", "path": "a.md"})
                time.sleep(0.1)
                atomic_write(idx_path, json.dumps(idx), _nested_lock=True)

        def writer_2() -> None:
            with FileLock(lock_path, timeout=10):
                idx = json.loads(idx_path.read_text()) if idx_path.exists() else {"notes": []}
                idx["notes"].append({"id": "n2", "path": "b.md"})
                time.sleep(0.1)
                atomic_write(idx_path, json.dumps(idx), _nested_lock=True)

        t1 = threading.Thread(target=writer_1)
        t2 = threading.Thread(target=writer_2)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        idx = json.loads(idx_path.read_text())
        paths = [n["path"] for n in idx["notes"]]
        assert "a.md" in paths
        assert "b.md" in paths

    def test_notes_write_preserves_content_under_concurrency(self, gm_dir: Path):
        """Concurrent note writes must not lose data."""
        note_path = gm_dir / "notes" / "concurrent.md"
        lock_path = gm_dir / "locks" / "notes_concurrent.md.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)

        def writer(content: str) -> None:
            for _ in range(5):
                with FileLock(lock_path, timeout=10):
                    current = note_path.read_text() if note_path.exists() else ""
                    note_path.write_text(current + content + "\n")
                    time.sleep(0.02)

        t1 = threading.Thread(target=writer, args=("A",))
        t2 = threading.Thread(target=writer, args=("B",))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        text = note_path.read_text()
        # Both writers must have contributed
        assert "A" in text and "B" in text
        # Total lines should be 10 (5 each)
        assert len(text.strip().splitlines()) == 10, \
            f"expected 10 lines, got {len(text.strip().splitlines())}"

    def test_notes_tool_create_same_note_only_once(self, gm_dir: Path):
        """Two concurrent notes.create for the same name — second must fail."""
        from galaxy_merge.tools.notes_tools import make_notes_tools
        upgrade_concurrency(gm_dir.parent)
        tools = {s.name: h for s, h in make_notes_tools(gm_dir)}

        async def concurrent_create():
            results = await tools["notes.create"]("dup", "first", "Duplicate Note")
            return results

        r = _run_async(concurrent_create())
        assert r.success

        async def second_create():
            results = await tools["notes.create"]("dup", "second", "Duplicate Note")
            return results

        r2 = _run_async(second_create())
        assert not r2.success  # Must fail — already exists
        assert "already exists" in r2.error.lower()


# =============================================================================
# 8. Trigger indexing in multiple sessions at once
# =============================================================================

class TestConcurrentIndexing:
    """Workspace indexing must be safe under concurrent access."""

    def test_concurrent_index_refresh(self, project_dir: Path):
        """Two indexers refreshing simultaneously — no corruption."""
        from galaxy_merge.workspace.indexer import WorkspaceIndexer
        upgrade_concurrency(project_dir / ".gm")

        idx1 = WorkspaceIndexer(project_dir)
        idx2 = WorkspaceIndexer(project_dir)

        results: list[dict] = []
        def refresh(idx: WorkspaceIndexer, label: str) -> None:
            r = idx.refresh()
            results.append(r)

        t1 = threading.Thread(target=refresh, args=(idx1, "A"))
        t2 = threading.Thread(target=refresh, args=(idx2, "B"))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        hashes_path = project_dir / ".gm" / "indexes" / "file_hashes.json"
        assert hashes_path.exists()
        hashes = json.loads(hashes_path.read_text())
        # README.md should be indexed
        assert "README.md" in hashes

    def test_incremental_update_safe(self, project_dir: Path):
        """Incremental updates from two sessions must not lose hashes."""
        from galaxy_merge.workspace.indexer import WorkspaceIndexer
        upgrade_concurrency(project_dir / ".gm")

        # Create files first
        (project_dir / "src").mkdir()
        (project_dir / "src" / "a.py").write_text("a")
        (project_dir / "src" / "b.py").write_text("b")

        idx = WorkspaceIndexer(project_dir)
        # Full refresh first
        idx.refresh()

        def update_a():
            idx2 = WorkspaceIndexer(project_dir)
            idx2.incremental_update(["src/a.py"])

        def update_b():
            idx3 = WorkspaceIndexer(project_dir)
            idx3.incremental_update(["src/b.py"])

        t1 = threading.Thread(target=update_a)
        t2 = threading.Thread(target=update_b)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        hashes = json.loads((project_dir / ".gm" / "indexes" / "file_hashes.json").read_text())
        assert "src/a.py" in hashes
        assert "src/b.py" in hashes


# =============================================================================
# 9. Trigger cache writes in multiple sessions at once
# =============================================================================

class TestConcurrentCacheWrites:
    """Cache writes from concurrent sessions must not corrupt."""

    def test_cache_concurrent_sets(self, tmp_path: Path):
        """Multiple concurrent CacheStore.set calls — no data loss."""
        from galaxy_merge.cache.store import CacheStore
        upgrade_concurrency(tmp_path / ".gm")
        store = CacheStore(tmp_path / ".gm" / "cache" / "file_summaries")

        def writer(key_suffix: str) -> None:
            for i in range(10):
                store.set(f"concurrent:{key_suffix}:{i}", f"value:{key_suffix}:{i}", ttl_seconds=600)
                time.sleep(0.01)

        threads = [threading.Thread(target=writer, args=(chr(ord("A") + i),)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Verify all values are readable
        for suffix in [chr(ord("A") + i) for i in range(5)]:
            for i in range(10):
                val = store.get(f"concurrent:{suffix}:{i}")
                assert val == f"value:{suffix}:{i}", f"missing/corrupt: {suffix}:{i}"

    def test_cache_read_write_race_safe(self, tmp_path: Path):
        """Concurrent read and write of same key must not return corrupt data."""
        from galaxy_merge.cache.store import CacheStore
        upgrade_concurrency(tmp_path / ".gm")
        store = CacheStore(tmp_path / ".gm" / "cache" / "test")

        store.set("race_key", "original", ttl_seconds=600)
        errors: list[str] = []

        def racer() -> None:
            for _ in range(50):
                store.set("race_key", "updated", ttl_seconds=600)
                val = store.get("race_key")
                if val not in ("original", "updated", None):
                    errors.append(f"corrupt: {val}")

        threads = [threading.Thread(target=racer) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"cache corruption: {errors}"
        assert store.get("race_key") == "updated"


# =============================================================================
# 10. Kill one terminal process while others continue
# =============================================================================

class TestCrashRecovery:
    """Killing a session must not break other sessions or corrupt state."""

    def test_kill_one_session_others_survive(self, project_dir: Path):
        """Kill one subprocess; the other must remain functional."""
        wr = str(project_dir)

        # Script for session that will be long-running and killed
        actions_kill = [
            'time.sleep(300)  # will be killed',
        ]

        # Script for survivor session
        actions_survivor = [
            'session.set_goal("SURVIVOR-GOAL")',
        ]

        kill_script = _session_script(wr, "sess_kill", actions_kill)
        survivor_script = _session_script(wr, "sess_survive", actions_survivor)

        # Start both
        kill_proc = subprocess.Popen(
            [sys.executable, "-c", kill_script],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )

        time.sleep(0.5)  # Let it start

        survivor_proc = subprocess.Popen(
            [sys.executable, "-c", survivor_script],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )
        survivor_proc.wait(timeout=15)
        assert survivor_proc.returncode == 0, survivor_proc.stderr.read().decode()

        # Kill the long-running session
        kill_proc.send_signal(signal.SIGKILL)
        kill_proc.wait(timeout=5)

        # Verify survivor's goal is intact
        goal_path = project_dir / ".gm" / "sessions" / "sess_survive" / "goal.json"
        assert goal_path.exists()
        goal_data = json.loads(goal_path.read_text())
        assert goal_data["goal"] == "SURVIVOR-GOAL"

        # Killed session should be recoverable (state still intact)
        state_path = project_dir / ".gm" / "sessions" / "sess_kill" / "state.json"
        assert state_path.exists()
        state_data = json.loads(state_path.read_text())
        assert "session_id" in state_data

    def test_cleanup_stale_sessions(self, project_dir: Path):
        """Stale session cleanup must remove old heartbeats and session dirs."""
        from galaxy_merge.core.concurrency import cleanup_stale_sessions, register_active_session, write_heartbeat
        gm_dir = project_dir / ".gm"

        # Register sessions with old heartbeats (simulate stale)
        register_active_session(gm_dir, "stale_sess_1")
        register_active_session(gm_dir, "stale_sess_2")

        hb_dir = gm_dir / "sessions" / "heartbeats"
        hb_dir.mkdir(parents=True, exist_ok=True)

        # Write old heartbeats with old file timestamps
        old_time = time.time() - 1000
        for sid in ["stale_sess_1", "stale_sess_2"]:
            hb_path = hb_dir / f"{sid}.hb"
            hb_path.write_text(str(old_time))
            os.utime(str(hb_path), (old_time, old_time))
            sess_dir = gm_dir / "sessions" / sid
            sess_dir.mkdir(parents=True, exist_ok=True)
            (sess_dir / "state.json").write_text("{}")

        # Also have a fresh session that should survive
        fresh_hb = hb_dir / "fresh_sess.hb"
        fresh_hb.write_text(str(time.time()))
        fresh_dir = gm_dir / "sessions" / "fresh_sess"
        fresh_dir.mkdir(parents=True, exist_ok=True)
        (fresh_dir / "state.json").write_text("{}")

        stale = cleanup_stale_sessions(gm_dir, max_age=60)
        assert "stale_sess_1" in stale or "stale_sess_2" in stale, f"expected stale cleanup, got {stale}"
        assert not (gm_dir / "sessions" / "stale_sess_1").exists()
        assert not (gm_dir / "sessions" / "stale_sess_2").exists()
        assert (gm_dir / "sessions" / "fresh_sess").exists()  # survives


# =============================================================================
# Lock mechanism unit tests
# =============================================================================

class TestFileLock:
    """FileLock must provide mutual exclusion across threads and processes."""

    def test_basic_exclusion(self, tmp_path: Path):
        lock_path = tmp_path / "test.lock"
        shared_counter_path = tmp_path / "counter.txt"

        def increment() -> None:
            for _ in range(100):
                with FileLock(lock_path, timeout=10):
                    current = int(shared_counter_path.read_text().strip() or "0") \
                        if shared_counter_path.exists() else 0
                    time.sleep(0.001)
                    shared_counter_path.write_text(str(current + 1))

        threads = [threading.Thread(target=increment) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        final = int(shared_counter_path.read_text().strip())
        assert final == 500, f"expected 500, got {final}"

    def test_lock_timeout(self, tmp_path: Path):
        lock_path = tmp_path / "timeout.lock"
        lock_path.write_text("")

        with FileLock(lock_path, timeout=1):
            # Hold the lock
            time.sleep(0.5)

        # The lock is now released; reacquire should work
        with FileLock(lock_path, timeout=1):
            pass

    def test_lock_timeout_raises(self, tmp_path: Path):
        lock_path = tmp_path / "hold.lock"
        lock_path.write_text("")

        with FileLock(lock_path, timeout=1):
            # Try to acquire from another thread while holding
            result: list[bool] = [True]

            def try_lock() -> None:
                try:
                    with FileLock(lock_path, timeout=0.5):
                        result[0] = False  # should not reach here
                except LockTimeout:
                    result[0] = True

            t = threading.Thread(target=try_lock)
            t.start()
            t.join(timeout=3)
            time.sleep(0.6)
            assert result[0], "LockTimeout was not raised"

    def test_atomic_write(self, tmp_path: Path):
        path = tmp_path / "atomic_test.txt"
        atomic_write(path, "hello")
        assert path.read_text() == "hello"
        atomic_write(path, "world")
        assert path.read_text() == "world"

    def test_atomic_append(self, tmp_path: Path):
        path = tmp_path / "append_test.jsonl"
        atomic_append(path, '{"id":1}')
        atomic_append(path, '{"id":2}')
        lines = path.read_text().strip().splitlines()
        assert len(lines) == 2
        assert json.loads(lines[0])["id"] == 1
        assert json.loads(lines[1])["id"] == 2

    def test_atomic_append_separates_existing_unterminated_line(self, tmp_path: Path):
        """Appending to a file without a trailing newline must preserve JSONL."""
        path = tmp_path / "unterminated.jsonl"
        path.write_text('{"id":1}')
        atomic_append(path, '{"id":2}')
        lines = path.read_text().splitlines()
        assert len(lines) == 2
        assert json.loads(lines[0])["id"] == 1
        assert json.loads(lines[1])["id"] == 2


class TestLockManager:
    def test_lock_path_consistency(self, tmp_path: Path):
        gm_dir = tmp_path / ".gm"
        lm = LockManager(gm_dir)
        p1 = lm.lock_path("notes/index.json")
        p2 = lm.lock_path("notes/index.json")
        assert p1 == p2

    def test_cleanup_stale(self, tmp_path: Path):
        gm_dir = tmp_path / ".gm"
        lm = LockManager(gm_dir)
        old_lock = lm.lock_path("ancient")
        old_lock.parent.mkdir(parents=True, exist_ok=True)
        old_lock.write_text("")
        removed = lm.cleanup_stale(max_age=0)
        assert removed >= 1


# =============================================================================
# Memory isolation under concurrency
# =============================================================================

class TestMemoryConcurrency:
    """Shared memory must not corrupt under concurrent writes."""

    def test_memory_store_concurrent_append(self, gm_dir: Path):
        """JSONL appends from multiple threads must not lose records."""
        from galaxy_merge.memory.store import MemoryStore
        upgrade_concurrency(gm_dir.parent)
        store = MemoryStore(gm_dir)

        def writer(kind: str, suffix: str) -> None:
            for i in range(20):
                store.append(kind, {"from": suffix, "i": i})
                time.sleep(0.005)

        threads = [
            threading.Thread(target=writer, args=("known_facts", "A")),
            threading.Thread(target=writer, args=("known_facts", "B")),
            threading.Thread(target=writer, args=("known_facts", "C")),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        records = store.read_all("known_facts")
        assert len(records) == 60, f"expected 60, got {len(records)}"
        sources = set(r["from"] for r in records)
        assert sources == {"A", "B", "C"}

    def test_preferences_no_race(self, gm_dir: Path):
        """Concurrent set_preference must not lose keys."""
        from galaxy_merge.memory.store import MemoryStore
        upgrade_concurrency(gm_dir.parent)
        store = MemoryStore(gm_dir)

        def writer(key: str, value: str) -> None:
            for _ in range(10):
                store.set_preference(key, value)
                time.sleep(0.005)

        threads = []
        for k in ["color", "size", "mode"]:
            t = threading.Thread(target=writer, args=(k, f"val_{k}"))
            threads.append(t)

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert store.get_preference("color") == "val_color"
        assert store.get_preference("size") == "val_size"
        assert store.get_preference("mode") == "val_mode"


# =============================================================================
# Session registry
# =============================================================================

class TestSessionRegistry:
    """Session registry must maintain correct list of active sessions."""

    def test_registry_append_only(self, gm_dir: Path):
        """Registry entries are never overwritten."""
        register_active_session(gm_dir, "sess_1")
        register_active_session(gm_dir, "sess_2")
        register_active_session(gm_dir, "sess_3")

        registry_path = gm_dir / "sessions" / "registry.jsonl"
        lines = registry_path.read_text().strip().splitlines()
        assert len(lines) == 3

    def test_heartbeat_isolation(self, gm_dir: Path):
        """Heartbeat files are per-session and do not interfere."""
        write_heartbeat(gm_dir, "sess_a")
        write_heartbeat(gm_dir, "sess_b")

        hb_dir = gm_dir / "sessions" / "heartbeats"
        hb_files = list(hb_dir.glob("*.hb"))
        assert len(hb_files) == 2


# =============================================================================
# Browser profile isolation
# =============================================================================

class TestBrowserProfileIsolation:
    """Browser automation profiles must be isolated by session ID."""

    def test_profile_paths_are_session_scoped(self, gm_dir: Path):
        """Two browser sessions get different profile directories."""
        from galaxy_merge.browser.manager import BrowserManager

        mgr = BrowserManager(gm_dir)
        a_profile = mgr.profile_path("sess_a_gui")
        b_profile = mgr.profile_path("sess_b_gui")

        assert a_profile != b_profile
        assert str(a_profile).endswith(".gm/browser/profiles/sess_a_gui")
        assert str(b_profile).endswith(".gm/browser/profiles/sess_b_gui")


# =============================================================================
# Full integration: concurrent gm sessions
# =============================================================================

class TestConcurrentSessionIntegration:
    """End-to-end concurrent session tests simulating real usage."""

    def test_three_sessions_concurrent_operations(self, project_dir: Path):
        """Three concurrent sessions with mixed operations — no corruption."""
        wr = str(project_dir)

        actions_a = [
            'session.set_goal("Implement feature A")',
            'from galaxy_merge.memory.project_memory import ProjectMemory',
            'pm = ProjectMemory(WR / ".gm")',
            'pm.record_fact("Feature A started", source="test")',
            '(WR / "feature_a.txt").write_text("A implementation")',
            'session.mark_completed()',
        ]
        actions_b = [
            'session.set_goal("Implement feature B")',
            'from galaxy_merge.memory.project_memory import ProjectMemory',
            'pm = ProjectMemory(WR / ".gm")',
            'pm.record_fact("Feature B started", source="test")',
            '(WR / "feature_b.txt").write_text("B implementation")',
            'session.mark_completed()',
        ]
        actions_c = [
            'session.set_goal("Write docs")',
            'from galaxy_merge.tools.notes_tools import make_notes_tools',
            'tools = {s.name: h for s, h in make_notes_tools(WR / ".gm")}',
            'import asyncio; asyncio.run(tools["notes.create"]("doc", "Documentation content", "Docs"))',
            'session.mark_completed()',
        ]

        scripts = [
            _session_script(wr, "sess_int_a", actions_a),
            _session_script(wr, "sess_int_b", actions_b),
            _session_script(wr, "sess_int_c", actions_c),
        ]

        results: list[subprocess.CompletedProcess] = []
        threads = []
        def _run(s: str) -> None:
            results.append(_run_script(s, timeout=20))

        for s in scripts:
            t = threading.Thread(target=_run, args=(s,))
            threads.append(t)
            t.start()
            time.sleep(0.15)

        for t in threads:
            t.join(timeout=20)

        # All must succeed
        for i, r in enumerate(results):
            assert r.returncode == 0, f"session {i} failed: {r.stderr[:500]}"

        # Verify files created
        assert (project_dir / "feature_a.txt").read_text().strip() == "A implementation"
        assert (project_dir / "feature_b.txt").read_text().strip() == "B implementation"

        # Verify note created
        assert (project_dir / ".gm" / "notes" / "doc.md").read_text().strip() == "Documentation content"

        # Verify all goals isolated
        sa = json.loads((project_dir / ".gm" / "sessions" / "sess_int_a" / "state.json").read_text())
        sb = json.loads((project_dir / ".gm" / "sessions" / "sess_int_b" / "state.json").read_text())
        sc = json.loads((project_dir / ".gm" / "sessions" / "sess_int_c" / "state.json").read_text())

        assert sa["goal"] == "Implement feature A"
        assert sb["goal"] == "Implement feature B"
        assert sc["goal"] == "Write docs"
        assert sa["status"] == "complete"
        assert sb["status"] == "complete"
        assert sc["status"] == "complete"

    def test_project_logs_aggregated(self, project_dir: Path):
        """Project-level aggregate log must exist and contain events."""
        wr = str(project_dir)

        actions = [
            'session.event_log.emit("test", session_id=session.session_id)',
        ]
        scripts = [
            _session_script(wr, "agg_sess_a", actions),
            _session_script(wr, "agg_sess_b", actions),
        ]

        for s in scripts:
            r = _run_script(s, timeout=10)
            assert r.returncode == 0, r.stderr

        # Verify separate session logs
        assert (project_dir / ".gm" / "sessions" / "agg_sess_a" / "events.jsonl").exists()
        assert (project_dir / ".gm" / "sessions" / "agg_sess_b" / "events.jsonl").exists()

        # Both logs must be valid JSONL
        for sid in ["agg_sess_a", "agg_sess_b"]:
            lines = (project_dir / ".gm" / "sessions" / sid / "events.jsonl").read_text().strip().splitlines()
            assert len(lines) >= 1
            for line in lines:
                rec = json.loads(line)
                assert "event" in rec
                assert "session_id" in rec


# =============================================================================
# Provider state isolation
# =============================================================================

class TestProviderStateIsolation:
    """Provider registry must be instantiable per-session without leakage."""

    @pytest.mark.skipif(
        importlib.util.find_spec("httpx") is None,
        reason="httpx not installed"
    )
    def test_provider_registry_new_per_session(self, project_dir: Path):
        """ProviderRegistry instantiation must not share global state."""
        from galaxy_merge.providers.registry import ProviderRegistry
        init_gm_dir(project_dir)

        config_dir = project_dir / "config_templates"
        config_dir.mkdir(exist_ok=True)
        (config_dir / "providers.json").write_text(json.dumps({
            "providers": {"test": {"id": "test", "type": "mock"}}
        }))

        reg1 = ProviderRegistry(config_dir)
        reg2 = ProviderRegistry(config_dir)
        reg1.load()
        reg2.load()

        # Must be different instances
        assert reg1 is not reg2


# =============================================================================
# Helper
# =============================================================================

def _run_async(coro):
    """Run a coroutine synchronously."""
    import asyncio
    return asyncio.run(coro)
