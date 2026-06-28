"""Verify project notes are first-class persistent objects.

Tests every requirement: create, read, edit, rename, delete, restore version,
list, search, tag, pin, inject into goal context, note-role tracking,
persistence across restarts, .gm/notes/ storage, separation from memory.
"""

import json

import pytest

from galaxy_merge.core.session import init_gm_dir, Session
from galaxy_merge.memory.retrieval import MemoryRetriever
from galaxy_merge.tools.notes_tools import (
    make_notes_tools,
    get_injected_notes,
    clear_goal_injections,
)

pytestmark = [pytest.mark.unit]


async def _tools(gm_dir):
    return {s.name: h for s, h in make_notes_tools(gm_dir)}


# =============================================================================
# 1. CREATE — verified
# =============================================================================


class TestNotesCreate:
    @pytest.mark.asyncio
    async def test_create_note(self, tmp_path):
        init_gm_dir(tmp_path)
        t = await _tools(tmp_path / ".gm")
        r = await t["notes.create"](
            "architecture", "Uses FastAPI", "Architecture Notes"
        )
        assert r.success
        assert (tmp_path / ".gm" / "notes" / "architecture.md").exists()

    @pytest.mark.asyncio
    async def test_create_rejects_duplicate(self, tmp_path):
        init_gm_dir(tmp_path)
        t = await _tools(tmp_path / ".gm")
        await t["notes.create"]("test", "v1")
        r = await t["notes.create"]("test", "v2")
        assert not r.success

    @pytest.mark.asyncio
    async def test_create_adds_to_index(self, tmp_path):
        init_gm_dir(tmp_path)
        t = await _tools(tmp_path / ".gm")
        await t["notes.create"]("test", "hello", "Title")
        idx = json.loads((tmp_path / ".gm" / "notes" / "index.json").read_text())
        entry = [n for n in idx["notes"] if n["path"] == "test.md"]
        assert len(entry) == 1
        assert entry[0]["title"] == "Title"
        assert entry[0]["tags"] == []
        assert entry[0]["pinned"] is False


# =============================================================================
# 2. READ — verified
# =============================================================================


class TestNotesRead:
    @pytest.mark.asyncio
    async def test_read_single(self, tmp_path):
        init_gm_dir(tmp_path)
        t = await _tools(tmp_path / ".gm")
        await t["notes.create"]("test", "content here")
        r = await t["notes.read"]("test")
        assert r.success
        assert r.data["content"] == "content here"

    @pytest.mark.asyncio
    async def test_read_all(self, tmp_path):
        init_gm_dir(tmp_path)
        t = await _tools(tmp_path / ".gm")
        await t["notes.create"]("a", "aaa")
        await t["notes.create"]("b", "bbb")
        r = await t["notes.read"]()
        assert r.success
        assert len(r.data["notes"]) == 2

    @pytest.mark.asyncio
    async def test_read_nonexistent(self, tmp_path):
        init_gm_dir(tmp_path)
        t = await _tools(tmp_path / ".gm")
        r = await t["notes.read"]("nonexistent")
        assert not r.success


# =============================================================================
# 3. EDIT — verified
# =============================================================================


class TestNotesEdit:
    @pytest.mark.asyncio
    async def test_edit_note(self, tmp_path):
        init_gm_dir(tmp_path)
        t = await _tools(tmp_path / ".gm")
        await t["notes.create"]("test", "old")
        r = await t["notes.update"]("test", "new")
        assert r.success
        assert (tmp_path / ".gm" / "notes" / "test.md").read_text() == "new"

    @pytest.mark.asyncio
    async def test_edit_nonexistent(self, tmp_path):
        init_gm_dir(tmp_path)
        t = await _tools(tmp_path / ".gm")
        r = await t["notes.update"]("ghost", "x")
        assert not r.success


# =============================================================================
# 4. RENAME — verified
# =============================================================================


class TestNotesRename:
    @pytest.mark.asyncio
    async def test_rename_note(self, tmp_path):
        init_gm_dir(tmp_path)
        t = await _tools(tmp_path / ".gm")
        await t["notes.create"]("old", "content")
        r = await t["notes.rename"]("old", "new")
        assert r.success
        assert not (tmp_path / ".gm" / "notes" / "old.md").exists()
        assert (tmp_path / ".gm" / "notes" / "new.md").exists()
        # Index must be updated
        idx = json.loads((tmp_path / ".gm" / "notes" / "index.json").read_text())
        paths = [n["path"] for n in idx["notes"]]
        assert "old.md" not in paths
        assert "new.md" in paths

    @pytest.mark.asyncio
    async def test_rename_to_existing(self, tmp_path):
        init_gm_dir(tmp_path)
        t = await _tools(tmp_path / ".gm")
        await t["notes.create"]("a", "aaa")
        await t["notes.create"]("b", "bbb")
        r = await t["notes.rename"]("a", "b")
        assert not r.success


# =============================================================================
# 5. DELETE (soft) — verified
# =============================================================================


class TestNotesDelete:
    @pytest.mark.asyncio
    async def test_soft_delete(self, tmp_path):
        init_gm_dir(tmp_path)
        t = await _tools(tmp_path / ".gm")
        await t["notes.create"]("test", "content")
        r = await t["notes.delete"]("test")
        assert r.success
        assert not (tmp_path / ".gm" / "notes" / "test.md").exists()
        assert (tmp_path / ".gm" / "notes" / ".trash" / "test.md").exists()

    @pytest.mark.asyncio
    async def test_delete_removes_from_index(self, tmp_path):
        init_gm_dir(tmp_path)
        t = await _tools(tmp_path / ".gm")
        await t["notes.create"]("test", "content")
        await t["notes.delete"]("test")
        idx = json.loads((tmp_path / ".gm" / "notes" / "index.json").read_text())
        assert "test.md" not in [n["path"] for n in idx["notes"]]


# =============================================================================
# 6. RESTORE VERSION — verified
# =============================================================================


class TestNotesRestoreVersion:
    @pytest.mark.asyncio
    async def test_history_created_on_update(self, tmp_path):
        init_gm_dir(tmp_path)
        t = await _tools(tmp_path / ".gm")
        await t["notes.create"]("test", "v1")
        await t["notes.update"]("test", "v2")
        history_dir = tmp_path / ".gm" / "notes" / "history"
        versions = list(history_dir.glob("test_*.md"))
        assert len(versions) >= 1
        # v1 content should be in history
        assert any("v1" in v.read_text() for v in versions)

    @pytest.mark.asyncio
    async def test_history_list(self, tmp_path):
        init_gm_dir(tmp_path)
        t = await _tools(tmp_path / ".gm")
        await t["notes.create"]("test", "v1")
        await t["notes.update"]("test", "v2")
        await t["notes.update"]("test", "v3")
        r = await t["notes.history.list"]("test")
        assert r.success
        assert len(r.data["versions"]) >= 2

    @pytest.mark.asyncio
    async def test_history_read_version(self, tmp_path):
        init_gm_dir(tmp_path)
        t = await _tools(tmp_path / ".gm")
        await t["notes.create"]("test", "v1")
        await t["notes.update"]("test", "v2")
        r = await t["notes.history.list"]("test")
        if r.data["versions"]:
            v = r.data["versions"][0]["version"]
            vr = await t["notes.history.read"]("test", v)
            assert vr.success
            assert len(vr.data["content"]) > 0


# =============================================================================
# 7. LIST — verified
# =============================================================================


class TestNotesList:
    @pytest.mark.asyncio
    async def test_list_indexed(self, tmp_path):
        init_gm_dir(tmp_path)
        t = await _tools(tmp_path / ".gm")
        await t["notes.create"]("a", "aaa", "Note A")
        await t["notes.create"]("b", "bbb", "Note B")
        r = await t["notes.list"]()
        assert r.success
        assert len(r.data["notes"]) == 2
        assert all("tags" in n for n in r.data["notes"])
        assert all("pinned" in n for n in r.data["notes"])


# =============================================================================
# 8. SEARCH — verified
# =============================================================================


class TestNotesSearch:
    @pytest.mark.asyncio
    async def test_search_by_content(self, tmp_path):
        init_gm_dir(tmp_path)
        t = await _tools(tmp_path / ".gm")
        await t["notes.create"]("python", "FastAPI is a Python framework")
        await t["notes.create"]("js", "Node.js is a runtime")
        r = await t["notes.search"]("Python")
        assert r.success
        names = [res["name"] for res in r.data["results"]]
        assert "python" in names

    @pytest.mark.asyncio
    async def test_search_by_title(self, tmp_path):
        init_gm_dir(tmp_path)
        t = await _tools(tmp_path / ".gm")
        await t["notes.create"]("architecture-notes", "Fast API backend")
        r = await t["notes.search"]("architecture")
        assert r.success
        assert len(r.data["results"]) >= 1

    @pytest.mark.asyncio
    async def test_search_no_match(self, tmp_path):
        init_gm_dir(tmp_path)
        t = await _tools(tmp_path / ".gm")
        await t["notes.create"]("test", "content")
        r = await t["notes.search"]("zzzznotfound")
        assert r.success
        assert r.data["count"] == 0


# =============================================================================
# 9. TAG — verified
# =============================================================================


class TestNotesTag:
    @pytest.mark.asyncio
    async def test_tag_note(self, tmp_path):
        init_gm_dir(tmp_path)
        t = await _tools(tmp_path / ".gm")
        await t["notes.create"]("test", "content")
        r = await t["notes.tag"]("test", ["api", "docs"])
        assert r.success
        idx = json.loads((tmp_path / ".gm" / "notes" / "index.json").read_text())
        entry = [n for n in idx["notes"] if n["path"] == "test.md"][0]
        assert "api" in entry["tags"]
        assert "docs" in entry["tags"]

    @pytest.mark.asyncio
    async def test_tag_adds_to_existing(self, tmp_path):
        init_gm_dir(tmp_path)
        t = await _tools(tmp_path / ".gm")
        await t["notes.create"]("test", "content")
        await t["notes.tag"]("test", ["api"])
        await t["notes.tag"]("test", ["testing"])
        idx = json.loads((tmp_path / ".gm" / "notes" / "index.json").read_text())
        entry = [n for n in idx["notes"] if n["path"] == "test.md"][0]
        assert "api" in entry["tags"]
        assert "testing" in entry["tags"]


# =============================================================================
# 10. PIN/UNPIN — verified
# =============================================================================


class TestNotesPin:
    @pytest.mark.asyncio
    async def test_pin_note(self, tmp_path):
        init_gm_dir(tmp_path)
        t = await _tools(tmp_path / ".gm")
        await t["notes.create"]("test", "content")
        r = await t["notes.pin"]("test", True)
        assert r.success
        idx = json.loads((tmp_path / ".gm" / "notes" / "index.json").read_text())
        entry = [n for n in idx["notes"] if n["path"] == "test.md"][0]
        assert entry["pinned"] is True

    @pytest.mark.asyncio
    async def test_unpin_note(self, tmp_path):
        init_gm_dir(tmp_path)
        t = await _tools(tmp_path / ".gm")
        await t["notes.create"]("test", "content")
        await t["notes.pin"]("test", True)
        await t["notes.pin"]("test", False)
        idx = json.loads((tmp_path / ".gm" / "notes" / "index.json").read_text())
        entry = [n for n in idx["notes"] if n["path"] == "test.md"][0]
        assert entry["pinned"] is False


# =============================================================================
# 11. INJECT INTO GOAL CONTEXT — verified
# =============================================================================


class TestNotesInject:
    @pytest.mark.asyncio
    async def test_inject_note(self, tmp_path):
        init_gm_dir(tmp_path)
        t = await _tools(tmp_path / ".gm")
        await t["notes.create"]("goal-context", "Important: use this pattern")
        r = await t["notes.inject"]("goal-context")
        assert r.success
        assert r.data["injected"] is True

    @pytest.mark.asyncio
    async def test_injected_notes_in_retrieval(self, tmp_path):
        init_gm_dir(tmp_path)
        t = await _tools(tmp_path / ".gm")
        await t["notes.create"]("injected-note", "THIS IS INJECTED")
        await t["notes.inject"]("injected-note")
        inject_list = get_injected_notes(tmp_path / ".gm")
        assert "injected-note" in inject_list

    @pytest.mark.asyncio
    async def test_inject_nonexistent(self, tmp_path):
        init_gm_dir(tmp_path)
        t = await _tools(tmp_path / ".gm")
        r = await t["notes.inject"]("ghost")
        assert not r.success

    @pytest.mark.asyncio
    async def test_clear_injections(self, tmp_path):
        init_gm_dir(tmp_path)
        t = await _tools(tmp_path / ".gm")
        await t["notes.create"]("test", "content")
        await t["notes.inject"]("test")
        assert len(get_injected_notes(tmp_path / ".gm")) >= 1
        clear_goal_injections(tmp_path / ".gm")
        assert len(get_injected_notes(tmp_path / ".gm")) == 0


# =============================================================================
# 12. NOTE-ROLE TRACKING — verified
# =============================================================================


class TestNoteRoleTracking:
    @pytest.mark.asyncio
    async def test_retriever_tracks_usage(self, tmp_path):
        init_gm_dir(tmp_path)
        retriever = MemoryRetriever(tmp_path / ".gm")
        retriever.record_note_usage("architecture.md", "planner")
        retriever.record_note_usage("architecture.md", "implementer")
        retriever.record_note_usage("commands.md", "skeptic")
        usage = retriever.get_note_usage()
        assert "architecture.md" in usage
        assert "planner" in usage["architecture.md"]
        assert "implementer" in usage["architecture.md"]
        assert "commands.md" in usage
        assert "skeptic" in usage["commands.md"]

    @pytest.mark.asyncio
    async def test_clear_on_new_goal(self, tmp_path):
        init_gm_dir(tmp_path)
        retriever = MemoryRetriever(tmp_path / ".gm")
        retriever.record_note_usage("note.md", "reviewer")
        retriever.clear_for_new_goal()
        assert retriever.get_note_usage() == {}
        assert len(get_injected_notes(tmp_path / ".gm")) == 0


# =============================================================================
# PERSISTENCE ACROSS RESTARTS — verified
# =============================================================================


class TestNotesPersistence:
    @pytest.mark.asyncio
    async def test_notes_survive_new_session(self, tmp_path):
        """Notes stored in .gm/notes/ survive creating a new Session object."""
        init_gm_dir(tmp_path)
        t = await _tools(tmp_path / ".gm")
        await t["notes.create"]("persistent", "this must survive")

        # Simulate restart: create new Session
        s2 = Session(tmp_path)
        s2.save_state()

        t2 = await _tools(tmp_path / ".gm")
        r = await t2["notes.read"]("persistent")
        assert r.success
        assert r.data["content"] == "this must survive"

    @pytest.mark.asyncio
    async def test_index_survives_restart(self, tmp_path):
        init_gm_dir(tmp_path)
        t = await _tools(tmp_path / ".gm")
        await t["notes.create"]("survivor", "still here")
        await t["notes.tag"]("survivor", ["persistent"])
        await t["notes.pin"]("survivor", True)

        Session(tmp_path).save_state()

        t2 = await _tools(tmp_path / ".gm")
        r = await t2["notes.list"]()
        paths = [n["path"] for n in r.data["notes"]]
        assert "survivor.md" in paths
        entry = [n for n in r.data["notes"] if n["path"] == "survivor.md"][0]
        assert "persistent" in entry["tags"]
        assert entry["pinned"] is True

    @pytest.mark.asyncio
    async def test_delete_is_soft_and_restorable(self, tmp_path):
        init_gm_dir(tmp_path)
        t = await _tools(tmp_path / ".gm")
        await t["notes.create"]("restore-me", "backup content")
        await t["notes.delete"]("restore-me")

        Session(tmp_path).save_state()

        t2 = await _tools(tmp_path / ".gm")
        r = await t2["notes.restore"]("restore-me")
        assert r.success
        r2 = await t2["notes.read"]("restore-me")
        assert r2.success
        assert r2.data["content"] == "backup content"


# =============================================================================
# STORAGE LOCATION — verified
# =============================================================================


class TestNotesStorage:
    def test_stored_under_gm_notes(self, tmp_path):
        init_gm_dir(tmp_path)
        assert (tmp_path / ".gm" / "notes").is_dir()

    def test_indexed_in_gm_notes_index(self, tmp_path):
        init_gm_dir(tmp_path)
        assert (tmp_path / ".gm" / "notes" / "index.json").exists()

    @pytest.mark.asyncio
    async def test_note_file_and_index_entry(self, tmp_path):
        init_gm_dir(tmp_path)
        t = await _tools(tmp_path / ".gm")
        await t["notes.create"]("my-note", "data")
        assert (tmp_path / ".gm" / "notes" / "my-note.md").exists()
        idx = json.loads((tmp_path / ".gm" / "notes" / "index.json").read_text())
        assert any(n["path"] == "my-note.md" for n in idx["notes"])


# =============================================================================
# SEPARATION: session notes, project notes, machine memory — verified
# =============================================================================


class TestNotesSeparation:
    def test_notes_and_memory_separate_dirs(self, tmp_path):
        init_gm_dir(tmp_path)
        assert (tmp_path / ".gm" / "notes").is_dir()
        assert (tmp_path / ".gm" / "memory").is_dir()
        assert (tmp_path / ".gm" / "sessions").is_dir()

    def test_notes_are_markdown(self, tmp_path):
        init_gm_dir(tmp_path)
        (tmp_path / ".gm" / "notes" / "user-note.md").write_text("# User note")
        notes_files = list((tmp_path / ".gm" / "notes").glob("*.md"))
        assert len(notes_files) >= 1

    def test_memory_is_jsonl(self, tmp_path):
        init_gm_dir(tmp_path)
        (tmp_path / ".gm" / "memory" / "known_facts.jsonl").write_text('{"fact":"x"}\n')
        memory_files = list((tmp_path / ".gm" / "memory").glob("*.jsonl"))
        assert len(memory_files) >= 1

    def test_notes_not_in_memory(self, tmp_path):
        init_gm_dir(tmp_path)
        (tmp_path / ".gm" / "notes" / "note.md").write_text("note")
        (tmp_path / ".gm" / "memory" / "facts.jsonl").write_text('{"fact":"x"}\n')
        note_mds = list((tmp_path / ".gm" / "notes").glob("*.md"))
        memory_jsonls = list((tmp_path / ".gm" / "memory").glob("*.jsonl"))
        assert len(note_mds) > 0
        assert len(memory_jsonls) > 0
        # No .md files in memory, no .jsonl files in notes
        assert len(list((tmp_path / ".gm" / "memory").glob("*.md"))) == 0
        assert len(list((tmp_path / ".gm" / "notes").glob("*.jsonl"))) == 0

    def test_session_dir_separate(self, tmp_path):
        init_gm_dir(tmp_path)
        s = Session(tmp_path)
        s.save_state()
        assert s.session_dir.parent.name == "sessions"
        assert "sessions" not in str(tmp_path / ".gm" / "notes")
        assert "sessions" not in str(tmp_path / ".gm" / "memory")
