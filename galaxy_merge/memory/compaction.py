import json
from pathlib import Path
from typing import Any

from galaxy_merge.core.locks import atomic_write
from galaxy_merge.memory.store import MemoryStore

COMPACTION_THRESHOLD_EVENTS = 500
COMPACTION_THRESHOLD_TOOL_CALLS = 100


class Compactor:
    def __init__(self, gm_dir: Path):
        self.gm_dir = gm_dir
        self.store = MemoryStore(gm_dir)

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

    def compact(self, session_dir: Path, reason: str = "") -> str:
        compacted = []
        if reason:
            compacted.append(f"Compaction reason: {reason}")

        state_path = session_dir / "state.json"
        if state_path.exists():
            state = json.loads(state_path.read_text())
            compacted.append(f"Session: {state.get('session_id', 'unknown')}")
            compacted.append(f"Status: {state.get('status', 'unknown')}")
            compacted.append(f"Goal: {state.get('goal', 'none')}")

        events_path = session_dir / "events.jsonl"
        safety_path = session_dir / "safety.jsonl"
        tool_calls_path = session_dir / "tool_calls.jsonl"
        open_risks: list[str] = []
        blocked_actions: list[str] = []
        key_events: list[dict[str, Any]] = []
        tool_calls_count = 0

        if events_path.exists():
            events = []
            with open(events_path) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        events.append(json.loads(line))
            compacted.append(f"Events: {len(events)} total")

            for e in events:
                event = e.get("event", "")
                if event in ("goal_received", "goal_parsed", "tool_call_blocked",
                             "completion_accepted", "completion_rejected",
                             "session_completed", "council_completed", "fusion_completed",
                             "provider_failed", "completion_review_started", "verification_completed"):
                    key_events.append(e)
                if event == "tool_call_blocked":
                    blocked_actions.append(e.get("tool", e.get("target", "unknown")))
                    open_risks.append(f"blocked: {e.get('tool', e.get('target', ''))} — {e.get('reason', '')}")
                if event == "provider_failed":
                    open_risks.append(f"provider failed: {e.get('provider_id', 'unknown')}")

            for e in key_events:
                compacted.append(f"  [{e['event']}] {e.get('goal', e.get('tool', e.get('task_type', '')))}")

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
            tool_calls_count = sum(1 for _ in open(tool_calls_path) if _.strip())
            compacted.append(f"Tool calls: {tool_calls_count}")

        plan_path = session_dir / "goal.json"
        if plan_path.exists():
            try:
                goal_data = json.loads(plan_path.read_text())
                status = goal_data.get("status", "")
                if status:
                    compacted.append(f"Last status: {status}")
                parsed = goal_data.get("parsed", {})
                if parsed:
                    compacted.append(f"Task type: {parsed.get('task_type', 'unknown')}")
            except Exception:
                pass

        if open_risks:
            compacted.append(f"Open risks: {'; '.join(open_risks[:5])}")
        if blocked_actions:
            compacted.append(f"Blocked actions: {len(blocked_actions)}")

        compacted.append("Verification status: unknown (replay events to determine)")

        compacted.append("Preserved: active goal, completion criteria, changed files, tool results, open risks, blocked actions, safety state, verification status")

        compacted_str = "\n".join(compacted)
        compacted_path = session_dir / "compacted.md"
        atomic_write(compacted_path, compacted_str)

        return compacted_str

    def compact_if_needed(self, session_dir: Path) -> str | None:
        should, reason = self.should_compact(session_dir)
        if should:
            return self.compact(session_dir, reason)
        return None
