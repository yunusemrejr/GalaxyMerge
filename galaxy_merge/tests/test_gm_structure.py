"""
Validate that .gm/ project folder matches the full spec structure.
"""
import json
from pathlib import Path
from unittest.mock import patch
import pytest

from galaxy_merge.core.session import init_gm_dir, detect_workroot, _validate_project_json


async def _nt(gm_dir):
    from galaxy_merge.tools.notes_tools import make_notes_tools
    return {schema.name: handler for schema, handler in make_notes_tools(gm_dir)}


# =============================================================================
# .gm/ directory creation
# =============================================================================

class TestInitGmDirStructure:
    def test_init_creates_dot_gm(self, tmp_path):
        init_gm_dir(tmp_path)
        assert (tmp_path / ".gm").is_dir()

    def test_project_json_exists(self, tmp_path):
        init_gm_dir(tmp_path)
        assert (tmp_path / ".gm" / "project.json").is_file()

    def test_project_json_valid(self, tmp_path):
        init_gm_dir(tmp_path)
        data = json.loads((tmp_path / ".gm" / "project.json").read_text())
        assert data["schema_version"] == 1
        assert data["project_id"].startswith("gmproj_")
        assert data["workroot"] == str(tmp_path)
        assert data["name"] == tmp_path.name

    def test_project_json_idempotent(self, tmp_path):
        init_gm_dir(tmp_path)
        pid1 = json.loads((tmp_path / ".gm" / "project.json").read_text())["project_id"]
        init_gm_dir(tmp_path)
        pid2 = json.loads((tmp_path / ".gm" / "project.json").read_text())["project_id"]
        assert pid1 == pid2

    def test_reinit_does_not_lose_fields(self, tmp_path):
        init_gm_dir(tmp_path)
        path = tmp_path / ".gm" / "project.json"
        data = json.loads(path.read_text())
        data["language_hints"] = ["python"]
        path.write_text(json.dumps(data))
        init_gm_dir(tmp_path)
        data2 = json.loads(path.read_text())
        assert data2["language_hints"] == ["python"]

    @pytest.mark.parametrize("subpath", [
        "notes", "notes/history", "notes/.trash",
        "memory", "sessions",
        "indexes", "indexes/embeddings",
        "cache/provider", "cache/file_summaries", "cache/skill_matches",
        "cache/fusion", "cache/command_results",
        "cache/web_search", "cache/browser_pages", "cache/github_scans",
        "web", "browser/profiles", "browser/sessions", "browser/screenshots",
        "locations", "github/scans", "github/issues", "github/pull_requests",
        "logs", "safety", "git/patchsets",
    ])
    def test_subdir_exists(self, tmp_path, subpath):
        init_gm_dir(tmp_path)
        assert (tmp_path / ".gm" / subpath).is_dir()

    @pytest.mark.parametrize("filepath", [
        "README.md",
        "project.json",
        "notes/index.json",
        "safety/policy.snapshot.json",
        "safety/blocked_actions.jsonl",
        "safety/allowed_commands.json",
        "safety/protected_paths.json",
        "git/checkpoints.jsonl",
        "web/searches.jsonl",
        "web/fetched_pages.jsonl",
        "web/wikipedia.jsonl",
        "web/duckduckgo.jsonl",
        "web/curl_fetches.jsonl",
        "browser/console_logs.jsonl",
        "browser/network_logs.jsonl",
        "browser/page_errors.jsonl",
        "github/repos.jsonl",
    ])
    def test_file_exists(self, tmp_path, filepath):
        init_gm_dir(tmp_path)
        assert (tmp_path / ".gm" / filepath).exists()

    def test_notes_index_schema(self, tmp_path):
        init_gm_dir(tmp_path)
        data = json.loads((tmp_path / ".gm" / "notes" / "index.json").read_text())
        assert data["schema_version"] == 1
        assert isinstance(data["notes"], list)

    def test_safety_policy_schema(self, tmp_path):
        init_gm_dir(tmp_path)
        data = json.loads((tmp_path / ".gm" / "safety" / "policy.snapshot.json").read_text())
        assert data["schema_version"] == 1
        assert data["policy"] == "default"

    def test_allowed_commands_schema(self, tmp_path):
        init_gm_dir(tmp_path)
        data = json.loads((tmp_path / ".gm" / "safety" / "allowed_commands.json").read_text())
        assert isinstance(data["allowed_commands"], list)

    def test_protected_paths_schema(self, tmp_path):
        init_gm_dir(tmp_path)
        data = json.loads((tmp_path / ".gm" / "safety" / "protected_paths.json").read_text())
        assert len(data["protected_paths"]) >= 2


class TestProjectJsonValidation:
    def test_validate_valid(self, tmp_path):
        init_gm_dir(tmp_path)
        assert _validate_project_json(tmp_path / ".gm" / "project.json") == []

    def test_validate_bad_schema_version(self, tmp_path):
        init_gm_dir(tmp_path)
        p = tmp_path / ".gm" / "project.json"
        d = json.loads(p.read_text())
        d["schema_version"] = 2
        p.write_text(json.dumps(d))
        assert len(_validate_project_json(p)) > 0

    def test_validate_bad_project_id(self, tmp_path):
        init_gm_dir(tmp_path)
        p = tmp_path / ".gm" / "project.json"
        d = json.loads(p.read_text())
        d["project_id"] = "invalid"
        p.write_text(json.dumps(d))
        assert len(_validate_project_json(p)) > 0

    def test_validate_missing_workroot(self, tmp_path):
        init_gm_dir(tmp_path)
        p = tmp_path / ".gm" / "project.json"
        d = json.loads(p.read_text())
        del d["workroot"]
        p.write_text(json.dumps(d))
        assert len(_validate_project_json(p)) > 0

    def test_validate_corrupt(self, tmp_path):
        init_gm_dir(tmp_path)
        p = tmp_path / ".gm" / "project.json"
        p.write_text("{corrupt}")
        assert len(_validate_project_json(p)) > 0


class TestSessionIsolation:
    def test_session_creates_subdirs(self, tmp_path):
        from galaxy_merge.core.session import Session
        init_gm_dir(tmp_path)
        s = Session(tmp_path)
        s.save_state()
        sd = s.session_dir
        assert sd.is_dir()
        assert (sd / "diffs").is_dir()
        assert (sd / "artifacts").is_dir()
        assert (sd / "transcript.jsonl").exists()
        assert (sd / "council.jsonl").exists()
        assert (sd / "tool_calls.jsonl").exists()
        assert (sd / "safety.jsonl").exists()
        assert (sd / "state.json").exists()
        assert (sd / "events.jsonl").exists()

    def test_sessions_are_isolated(self, tmp_path):
        from galaxy_merge.core.session import Session
        init_gm_dir(tmp_path)
        s1 = Session(tmp_path)
        s2 = Session(tmp_path)
        s1.save_state()
        s2.save_state()
        assert s1.session_id != s2.session_id
        assert s1.session_dir != s2.session_dir
        assert s1.session_dir.parent == s2.session_dir.parent

    def test_goal_persisted(self, tmp_path):
        from galaxy_merge.core.session import Session
        init_gm_dir(tmp_path)
        s = Session(tmp_path)
        s.set_goal("test goal")
        data = json.loads((tmp_path / ".gm" / "sessions" / s.session_id / "state.json").read_text())
        assert data["goal"] == "test goal"
        assert data["status"] == "understanding"

    def test_goal_json_exists(self, tmp_path):
        from galaxy_merge.core.session import Session
        init_gm_dir(tmp_path)
        s = Session(tmp_path)
        s.set_goal("test goal")
        data = json.loads((tmp_path / ".gm" / "sessions" / s.session_id / "goal.json").read_text())
        assert data["goal"] == "test goal"

    def test_completed(self, tmp_path):
        from galaxy_merge.core.session import Session
        init_gm_dir(tmp_path)
        s = Session(tmp_path)
        s.mark_completed()
        data = json.loads((tmp_path / ".gm" / "sessions" / s.session_id / "state.json").read_text())
        assert data["status"] == "complete"
        assert data["active"] is False

    def test_crashed(self, tmp_path):
        from galaxy_merge.core.session import Session
        init_gm_dir(tmp_path)
        s = Session(tmp_path)
        s.mark_crashed()
        data = json.loads((tmp_path / ".gm" / "sessions" / s.session_id / "state.json").read_text())
        assert data["status"] == "crashed"
        assert data["active"] is False


class TestWorkrootDetection:
    def test_detect_workroot_blocks_broad_roots(self, tmp_path):
        fake_home = tmp_path / "home" / "yemre"
        fake_home.mkdir(parents=True)
        blocked_dirs = [
            fake_home,
            fake_home / "Desktop",
            fake_home / "Downloads",
            Path("/"),
            Path("/home"),
            Path("/usr"),
            Path("/etc"),
            Path("/var"),
            Path("/opt"),
            Path("/bin"),
            Path("/sbin"),
            Path("/root"),
            Path("/tmp"),  # not a hard deny in this implementation, but keep as baseline control
        ]
        for d in blocked_dirs:
            if str(d).startswith("/tmp"):
                continue
            d.mkdir(exist_ok=True, parents=True)
            # Seed markers so detection would otherwise short-circuit to this directory.
            if d == fake_home:
                (d / ".git").mkdir(exist_ok=True)

        with patch("galaxy_merge.core.session.Path.home", return_value=fake_home):
            for d in blocked_dirs:
                result = detect_workroot(d)
                if d == Path("/tmp"):
                    assert result == d
                else:
                    assert result is None


class TestNotesCrud:
    @pytest.mark.asyncio
    async def test_create(self, tmp_path):
        init_gm_dir(tmp_path)
        tools = await _nt(tmp_path / ".gm")
        r = await tools["notes.create"]("test", "hello world", "Test")
        assert r.success
        assert (tmp_path / ".gm" / "notes" / "test.md").read_text() == "hello world"

    @pytest.mark.asyncio
    async def test_create_updates_index(self, tmp_path):
        init_gm_dir(tmp_path)
        tools = await _nt(tmp_path / ".gm")
        await tools["notes.create"]("test", "hello")
        idx = json.loads((tmp_path / ".gm" / "notes" / "index.json").read_text())
        entries = [n for n in idx["notes"] if n["path"] == "test.md"]
        assert len(entries) == 1

    @pytest.mark.asyncio
    async def test_read_all(self, tmp_path):
        init_gm_dir(tmp_path)
        tools = await _nt(tmp_path / ".gm")
        await tools["notes.create"]("a", "aaa")
        await tools["notes.create"]("b", "bbb")
        r = await tools["notes.read"]()
        assert r.success
        assert len(r.data["notes"]) == 2

    @pytest.mark.asyncio
    async def test_read_single(self, tmp_path):
        init_gm_dir(tmp_path)
        tools = await _nt(tmp_path / ".gm")
        await tools["notes.create"]("test", "hello")
        r = await tools["notes.read"]("test")
        assert r.success
        assert r.data["content"] == "hello"

    @pytest.mark.asyncio
    async def test_update(self, tmp_path):
        init_gm_dir(tmp_path)
        tools = await _nt(tmp_path / ".gm")
        await tools["notes.create"]("test", "hello")
        r = await tools["notes.update"]("test", "world")
        assert r.success
        assert (tmp_path / ".gm" / "notes" / "test.md").read_text() == "world"

    @pytest.mark.asyncio
    async def test_update_saves_history(self, tmp_path):
        init_gm_dir(tmp_path)
        tools = await _nt(tmp_path / ".gm")
        await tools["notes.create"]("test", "v1")
        await tools["notes.update"]("test", "v2")
        versions = list((tmp_path / ".gm" / "notes" / "history").glob("test_*.md"))
        assert len(versions) >= 1

    @pytest.mark.asyncio
    async def test_rename(self, tmp_path):
        init_gm_dir(tmp_path)
        tools = await _nt(tmp_path / ".gm")
        await tools["notes.create"]("old", "content")
        await tools["notes.rename"]("old", "new")
        assert not (tmp_path / ".gm" / "notes" / "old.md").exists()
        assert (tmp_path / ".gm" / "notes" / "new.md").exists()
        idx = json.loads((tmp_path / ".gm" / "notes" / "index.json").read_text())
        paths = [n["path"] for n in idx["notes"]]
        assert "old.md" not in paths
        assert "new.md" in paths

    @pytest.mark.asyncio
    async def test_soft_delete(self, tmp_path):
        init_gm_dir(tmp_path)
        tools = await _nt(tmp_path / ".gm")
        await tools["notes.create"]("test", "content")
        r = await tools["notes.delete"]("test")
        assert r.success
        assert not (tmp_path / ".gm" / "notes" / "test.md").exists()
        assert (tmp_path / ".gm" / "notes" / ".trash" / "test.md").exists()
        idx = json.loads((tmp_path / ".gm" / "notes" / "index.json").read_text())
        assert "test.md" not in [n["path"] for n in idx["notes"]]

    @pytest.mark.asyncio
    async def test_restore(self, tmp_path):
        init_gm_dir(tmp_path)
        tools = await _nt(tmp_path / ".gm")
        await tools["notes.create"]("test", "content")
        await tools["notes.delete"]("test")
        r = await tools["notes.restore"]("test")
        assert r.success
        assert (tmp_path / ".gm" / "notes" / "test.md").exists()
        idx = json.loads((tmp_path / ".gm" / "notes" / "index.json").read_text())
        assert "test.md" in [n["path"] for n in idx["notes"]]

    @pytest.mark.asyncio
    async def test_tag(self, tmp_path):
        init_gm_dir(tmp_path)
        tools = await _nt(tmp_path / ".gm")
        await tools["notes.create"]("test", "content")
        await tools["notes.tag"]("test", ["python", "docs"])
        idx = json.loads((tmp_path / ".gm" / "notes" / "index.json").read_text())
        entry = [n for n in idx["notes"] if n["path"] == "test.md"][0]
        assert "python" in entry["tags"]
        assert "docs" in entry["tags"]

    @pytest.mark.asyncio
    async def test_pin(self, tmp_path):
        init_gm_dir(tmp_path)
        tools = await _nt(tmp_path / ".gm")
        await tools["notes.create"]("test", "content")
        await tools["notes.pin"]("test", True)
        idx = json.loads((tmp_path / ".gm" / "notes" / "index.json").read_text())
        entry = [n for n in idx["notes"] if n["path"] == "test.md"][0]
        assert entry["pinned"] is True

    def test_notes_and_memory_separate(self, tmp_path):
        init_gm_dir(tmp_path)
        assert (tmp_path / ".gm" / "notes").is_dir()
        assert (tmp_path / ".gm" / "memory").is_dir()
        (tmp_path / ".gm" / "notes" / "test.md").write_text("note")
        (tmp_path / ".gm" / "memory" / "facts.jsonl").write_text('{"fact":"x"}\n')
        assert len(list((tmp_path / ".gm" / "notes").glob("*.md"))) > 0
        assert len(list((tmp_path / ".gm" / "memory").glob("*.jsonl"))) > 0


class TestEventLogging:
    def test_events_jsonl_format(self, tmp_path):
        from galaxy_merge.core.session import Session
        init_gm_dir(tmp_path)
        s = Session(tmp_path)
        s.event_log.emit("first", session_id=s.session_id)
        s.event_log.emit("second", session_id=s.session_id, detail="info")
        lines = (tmp_path / ".gm" / "sessions" / s.session_id / "events.jsonl").read_text().strip().splitlines()
        assert len(lines) == 2
        last = json.loads(lines[-1])
        assert last["event"] == "second"
        assert last["detail"] == "info"

    def test_session_has_all_log_files(self, tmp_path):
        from galaxy_merge.core.session import Session
        init_gm_dir(tmp_path)
        s = Session(tmp_path)
        s.save_state()
        sd = s.session_dir
        assert (sd / "events.jsonl").exists()
        assert (sd / "transcript.jsonl").exists()
        assert (sd / "council.jsonl").exists()
        assert (sd / "tool_calls.jsonl").exists()
        assert (sd / "safety.jsonl").exists()
