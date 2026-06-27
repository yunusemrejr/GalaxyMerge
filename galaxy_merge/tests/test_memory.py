import pytest
from pathlib import Path

from galaxy_merge.memory.store import MemoryStore
from galaxy_merge.memory.project_memory import ProjectMemory
from galaxy_merge.memory.compaction import Compactor
from galaxy_merge.core.session import Session


class TestMemoryStore:
    def test_append_and_read(self, tmp_path):
        store = MemoryStore(tmp_path / ".gm")
        store.append("test_kind", {"key": "value"})
        records = store.read_all("test_kind")
        assert len(records) == 1
        assert records[0]["key"] == "value"

    def test_read_recent(self, tmp_path):
        store = MemoryStore(tmp_path / ".gm")
        for i in range(5):
            store.append("test_kind", {"i": i})
        recent = store.read_recent("test_kind", 2)
        assert len(recent) == 2

    def test_preferences(self, tmp_path):
        store = MemoryStore(tmp_path / ".gm")
        store.set_preference("theme", "dark")
        assert store.get_preference("theme") == "dark"
        assert store.get_preference("nonexistent", "default") == "default"

    def test_clear(self, tmp_path):
        store = MemoryStore(tmp_path / ".gm")
        store.append("test", {"x": 1})
        store.clear("test")
        assert store.read_all("test") == []


class TestProjectMemory:
    def test_record_fact(self, tmp_path):
        gm = tmp_path / ".gm"
        pm = ProjectMemory(gm)
        pm.record_fact("project uses fastapi")
        facts = pm.get_facts()
        assert len(facts) == 1
        assert facts[0]["fact"] == "project uses fastapi"

    def test_relevant_context(self, tmp_path):
        gm = tmp_path / ".gm"
        pm = ProjectMemory(gm)
        pm.record_fact("database is postgresql")
        context = pm.get_relevant_context("postgresql")
        assert "postgresql" in context
