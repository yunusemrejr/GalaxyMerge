import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from galaxy_merge.core.events import EventLog
from galaxy_merge.core.locks import atomic_append, atomic_write
from galaxy_merge.memory.store import MemoryStore
from galaxy_merge.safety.credential_policy import CredentialPolicy

COMPACTION_THRESHOLD_EVENTS = 500
COMPACTION_THRESHOLD_TOOL_CALLS = 100


class Compactor:
    def __init__(self, gm_dir: Path):
        self.gm_dir = gm_dir
        self.store = MemoryStore(gm_dir)
        self.redactor = CredentialPolicy(gm_dir.parent)

    def should_compact(self, session_dir: Path) -> tuple[bool, str]:
        events_path = session_dir / "events.jsonl"
        if events_path.exists():
            count = sum(1 for _ in open(events_path) if _.strip())
            if count > COMPACTION_THRESHOLD_EVENTS:
                return True, f"event count ({count}) exceeds threshold"

        tool_calls_path = session_dir / "tool_calls.jsonl"
        if tool_calls_path.exists():
            count = sum(1 for _ in open(tool_calls_path) if _.strip())
            if count > COMPACTION_THRESHOLD_TOOL_CALLS:
                return True, f"tool call count ({count}) exceeds threshold"

        return False, ""

    def compact(
        self,
        session_dir: Path,
        reason: str = "",
        model_id: str = "local_compactor",
        role: str = "compactor",
    ) -> str:
        session_dir.mkdir(parents=True, exist_ok=True)
        session_id = self._session_id(session_dir)
        summary_path = session_dir / "compacted.md"
        context_before_tokens = self._estimate_session_tokens(session_dir)
        self._emit_compaction_event(
            session_dir,
            "compaction_started",
            session_id=session_id,
            status="started",
            model_id=model_id,
            role=role,
            reason=reason,
            context_before_tokens=context_before_tokens,
            summary_path=str(summary_path),
        )

        compacted = []
        if reason:
            compacted.append(f"Compaction reason: {reason}")

        state_path = session_dir / "state.json"
        state: dict[str, Any] = {}
        if state_path.exists():
            state = self._read_json(state_path)
            compacted.append(f"Session: {state.get('session_id', 'unknown')}")
            compacted.append(f"Status: {state.get('status', 'unknown')}")
            compacted.append(f"Goal: {state.get('goal', 'none')}")
            compacted.append(f"WorkRoot: {state.get('workroot', 'unknown')}")

        events_path = session_dir / "events.jsonl"
        safety_path = session_dir / "safety.jsonl"
        tool_calls_path = session_dir / "tool_calls.jsonl"
        open_risks: list[str] = []
        blocked_actions: list[str] = []
        key_events: list[dict[str, Any]] = []
        changed_files: list[str] = []
        tool_results: list[str] = []
        browser_evidence: list[str] = []
        web_evidence: list[str] = []
        council_evidence: list[str] = []
        provider_failures: list[str] = []
        location_events: list[str] = []
        verification_status = "unknown"
        tool_calls_count = 0

        if events_path.exists():
            events = self._read_jsonl(events_path)
            compacted.append(f"Events: {len(events)} total")

            for e in events:
                event = e.get("event", "")
                if event in (
                    "goal_received",
                    "goal_parsed",
                    "tool_call_blocked",
                    "completion_accepted",
                    "completion_rejected",
                    "session_completed",
                    "council_completed",
                    "fusion_completed",
                    "provider_failed",
                    "completion_review_started",
                    "verification_completed",
                ):
                    key_events.append(e)
                if event == "tool_call_blocked":
                    blocked_actions.append(e.get("tool", e.get("target", "unknown")))
                    open_risks.append(
                        f"blocked: {e.get('tool', e.get('target', ''))} - {e.get('reason', '')}"
                    )
                if event == "file_changed":
                    changed_files.append(e.get("path", e.get("target", "unknown")))
                if event in ("tool_call_completed", "tool_call_blocked"):
                    tool_results.append(
                        f"{e.get('tool', 'unknown')}:{e.get('status', event)}"
                    )
                if event.startswith("browser_"):
                    browser_evidence.append(event)
                if event.startswith("web_"):
                    web_evidence.append(event)
                if event in ("council_completed", "fusion_completed"):
                    council_evidence.append(event)
                if event == "provider_failed":
                    failure = f"{e.get('provider_id', 'unknown')}:{e.get('model', e.get('role', 'unknown'))}"
                    provider_failures.append(failure)
                    open_risks.append(f"provider failed: {failure}")
                if event.startswith("location_"):
                    location_events.append(event)
                if event == "verification_completed":
                    verification_status = "passed" if e.get("passed") else "failed"

            for e in key_events:
                compacted.append(
                    f"  [{e['event']}] {e.get('goal', e.get('tool', e.get('task_type', '')))}"
                )

        if safety_path.exists():
            with open(safety_path) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            rec = json.loads(line)
                            if rec.get("action", "").startswith("block"):
                                blocked_actions.append(rec.get("action", "unknown"))
                        except json.JSONDecodeError:
                            pass

        if tool_calls_path.exists():
            tool_calls = self._read_jsonl(tool_calls_path)
            tool_calls_count = len(tool_calls)
            compacted.append(f"Tool calls: {tool_calls_count}")
            for call in tool_calls[-5:]:
                tool_results.append(
                    f"{call.get('tool', 'unknown')}:{call.get('status', call.get('success', 'unknown'))}"
                )

        plan_path = session_dir / "goal.json"
        active_goal = state.get("goal", "")
        completion_criteria: Any = ""
        task_scope = "unknown"
        if plan_path.exists():
            try:
                goal_data = self._read_json(plan_path)
                active_goal = goal_data.get("goal", active_goal)
                status = goal_data.get("status", "")
                if status:
                    compacted.append(f"Last status: {status}")
                parsed = goal_data.get("parsed", {})
                if parsed:
                    compacted.append(f"Task type: {parsed.get('task_type', 'unknown')}")
                    task_scope = parsed.get(
                        "estimated_scope", parsed.get("task_scope", task_scope)
                    )
                completion_criteria = goal_data.get(
                    "completion_criteria", parsed.get("completion_criteria", "")
                )
            except Exception:
                pass

        compacted.append(f"Active goal: {active_goal or 'none'}")
        compacted.append(f"TaskScope: {task_scope}")
        compacted.append(
            f"Changed files: {', '.join(sorted(set(changed_files))) or 'none recorded'}"
        )
        compacted.append(
            f"Tool results: {', '.join(tool_results[-10:]) or 'none recorded'}"
        )
        compacted.append(
            f"Browser evidence: {', '.join(browser_evidence[-10:]) or 'none recorded'}"
        )
        compacted.append(
            f"Web evidence: {', '.join(web_evidence[-10:]) or 'none recorded'}"
        )
        compacted.append(
            f"Council/fusion state: {', '.join(council_evidence[-10:]) or 'none recorded'}"
        )
        compacted.append(
            f"Provider failures: {', '.join(provider_failures[-10:]) or 'none recorded'}"
        )
        compacted.append(
            f"Location registry events: {', '.join(location_events[-10:]) or 'none recorded'}"
        )
        compacted.append(
            f"Completion criteria: {completion_criteria or 'not recorded'}"
        )

        if open_risks:
            compacted.append(f"Open risks: {'; '.join(open_risks[:5])}")
        if blocked_actions:
            compacted.append(f"Blocked actions: {len(blocked_actions)}")

        compacted.append(f"Verification status: {verification_status}")

        compacted.append(
            "Preserved: active goal, current plan/status, WorkRoot, TaskScope, changed files, tool results, browser evidence, web evidence, council outputs, open risks, blocked actions, safety state, location registry, degraded provider state, verification status, completion criteria"
        )

        compacted_str = self.redactor.redact("\n".join(compacted))
        context_after_tokens = self._estimate_tokens(compacted_str)
        atomic_write(summary_path, compacted_str)
        self._emit_compaction_event(
            session_dir,
            "compaction_completed",
            session_id=session_id,
            status="completed",
            model_id=model_id,
            role=role,
            reason=reason,
            context_before_tokens=context_before_tokens,
            context_after_tokens=context_after_tokens,
            summary_path=str(summary_path),
        )

        return compacted_str

    def compact_if_needed(self, session_dir: Path) -> str | None:
        should, reason = self.should_compact(session_dir)
        if should:
            return self.compact(session_dir, reason)
        return None

    def _emit_compaction_event(
        self, session_dir: Path, event: str, session_id: str, **fields: Any
    ) -> None:
        fields = self._redact_fields(fields)
        EventLog(session_dir / "events.jsonl").emit(
            event, session_id=session_id, **fields
        )
        record = {
            "time": datetime.now(timezone.utc).isoformat(),
            "session_id": session_id,
            "event": event,
            **fields,
        }
        atomic_append(session_dir / "compaction.jsonl", json.dumps(record, default=str))

    def _redact_fields(self, fields: dict[str, Any]) -> dict[str, Any]:
        return {key: self._redact_value(value) for key, value in fields.items()}

    def _redact_value(self, value: Any) -> Any:
        if isinstance(value, str):
            return self.redactor.redact(value)
        if isinstance(value, list):
            return [self._redact_value(item) for item in value]
        if isinstance(value, dict):
            return {key: self._redact_value(item) for key, item in value.items()}
        return value

    def _session_id(self, session_dir: Path) -> str:
        state_path = session_dir / "state.json"
        if state_path.exists():
            state = self._read_json(state_path)
            if state.get("session_id"):
                return str(state["session_id"])
        return session_dir.name

    def _estimate_session_tokens(self, session_dir: Path) -> int:
        parts = []
        for name in (
            "state.json",
            "goal.json",
            "events.jsonl",
            "tool_calls.jsonl",
            "safety.jsonl",
            "council.jsonl",
            "transcript.jsonl",
        ):
            path = session_dir / name
            if path.exists():
                try:
                    parts.append(path.read_text(errors="ignore"))
                except OSError:
                    pass
        return self._estimate_tokens("\n".join(parts))

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        if not text:
            return 0
        return max(1, len(text) // 4)

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            return {}

    @staticmethod
    def _read_jsonl(path: Path) -> list[dict[str, Any]]:
        records = []
        try:
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            records.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
        except OSError:
            return []
        return records
