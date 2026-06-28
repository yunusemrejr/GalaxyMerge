import json

from galaxy_merge.memory.store import MemoryStore
from galaxy_merge.memory.project_memory import ProjectMemory
from galaxy_merge.memory.compaction import Compactor
from galaxy_merge.core.events import EventLog
from galaxy_merge.core.locks import atomic_append, atomic_write


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


class TestCompactor:
    def test_compaction_logs_events_and_preserves_mission_state(self, tmp_path):
        gm_dir = tmp_path / ".gm"
        session_dir = gm_dir / "sessions" / "sess_a"
        session_dir.mkdir(parents=True)
        atomic_write(session_dir / "state.json", json.dumps({
            "session_id": "sess_a",
            "workroot": str(tmp_path),
            "status": "testing",
            "goal": "Fix failing login page",
        }))
        atomic_write(session_dir / "goal.json", json.dumps({
            "goal": "Fix failing login page",
            "status": "testing",
            "parsed": {"task_type": "webapp_repair", "estimated_scope": "src/login"},
            "completion_criteria": ["tests pass", "browser console clean"],
        }))
        event_log = EventLog(session_dir / "events.jsonl")
        event_log.emit("goal_received", session_id="sess_a", goal="Fix failing login page")
        event_log.emit("file_changed", session_id="sess_a", path="src/login.tsx")
        event_log.emit("browser_console_error", session_id="sess_a", message="ReferenceError")
        event_log.emit("web_search_completed", session_id="sess_a", source="duckduckgo")
        event_log.emit("council_completed", session_id="sess_a", roles=["planner", "reviewer"])
        event_log.emit("fusion_completed", session_id="sess_a", changes_proposed=1)
        event_log.emit("provider_failed", session_id="sess_a", provider_id="p1", model="m1")
        event_log.emit("location_classified", session_id="sess_a", classification="local_taskscope")
        event_log.emit("tool_call_blocked", session_id="sess_a", tool="shell.run", reason="remote mutation")
        event_log.emit("verification_completed", session_id="sess_a", passed=False)
        atomic_append(session_dir / "tool_calls.jsonl", json.dumps({
            "tool": "file.patch",
            "status": "success",
        }))
        atomic_append(session_dir / "safety.jsonl", json.dumps({
            "action": "block_shell",
            "reason": "remote mutation",
        }))

        summary = Compactor(gm_dir).compact(
            session_dir,
            reason="event count (650) exceeds threshold",
            model_id="test-model",
            role="synthesizer",
        )

        assert (session_dir / "compacted.md").exists()
        assert (session_dir / "compaction.jsonl").exists()
        assert "Active goal: Fix failing login page" in summary
        assert "WorkRoot:" in summary
        assert "TaskScope: src/login" in summary
        assert "Changed files: src/login.tsx" in summary
        assert "Browser evidence: browser_console_error" in summary
        assert "Web evidence: web_search_completed" in summary
        assert "Council/fusion state: council_completed, fusion_completed" in summary
        assert "Provider failures: p1:m1" in summary
        assert "Location registry events: location_classified" in summary
        assert "Verification status: failed" in summary
        assert "Completion criteria: ['tests pass', 'browser console clean']" in summary

        event_types = [event["event"] for event in EventLog(session_dir / "events.jsonl").replay()]
        assert "compaction_started" in event_types
        assert "compaction_completed" in event_types
        compaction_records = [
            json.loads(line)
            for line in (session_dir / "compaction.jsonl").read_text().splitlines()
            if line.strip()
        ]
        assert [record["event"] for record in compaction_records] == [
            "compaction_started",
            "compaction_completed",
        ]
        completed = compaction_records[-1]
        assert completed["model_id"] == "test-model"
        assert completed["role"] == "synthesizer"
        assert completed["reason"] == "event count (650) exceeds threshold"
        assert completed["context_before_tokens"] > 0
        assert completed["context_after_tokens"] > 0
        assert completed["summary_path"].endswith("compacted.md")

    def test_compaction_redacts_placeholder_env_values_from_summary_and_event_logs(self, tmp_path):
        gm_dir = tmp_path / ".gm"
        session_dir = gm_dir / "sessions" / "sess_secret"
        session_dir.mkdir(parents=True)
        placeholder_env = "OPENAI_API_KEY=placeholder-provider-value"
        atomic_write(session_dir / "state.json", json.dumps({
            "session_id": "sess_secret",
            "workroot": str(tmp_path),
            "goal": placeholder_env,
        }))
        EventLog(session_dir / "events.jsonl").emit("goal_received", session_id="sess_secret", goal=placeholder_env)

        Compactor(gm_dir).compact(session_dir, reason=placeholder_env)

        summary = (session_dir / "compacted.md").read_text()
        compaction = (session_dir / "compaction.jsonl").read_text()
        compaction_events = [
            event for event in EventLog(session_dir / "events.jsonl").replay()
            if event["event"].startswith("compaction_")
        ]
        assert placeholder_env not in summary
        assert placeholder_env not in compaction
        assert placeholder_env not in json.dumps(compaction_events)
        assert "OPENAI_API_KEY=***REDACTED***" in summary
