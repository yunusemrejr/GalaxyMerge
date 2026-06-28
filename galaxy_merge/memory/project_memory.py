from pathlib import Path
from typing import Any

from galaxy_merge.memory.store import MemoryStore

PROMOTABLE_PATTERNS = [
    "test command",
    "test suite",
    "npm test",
    "pytest",
    "cargo test",
    "build command",
    "architecture",
    "dependency",
    "config",
    "convention",
    "rule",
    "preference",
]

NON_PROMOTABLE_PATTERNS = [
    "debug",
    "print(",
    "console.log",
    "temp",
    "temporary",
    "random",
    "hallucination",
    "wrong",
]


class ProjectMemory:
    def __init__(self, gm_dir: Path):
        self.store = MemoryStore(gm_dir)

    def record_fact(self, fact: str, source: str = "session") -> None:
        self.store.append("known_facts", {"fact": fact, "source": source})

    def record_failure(self, error: str, context: str = "") -> None:
        self.store.append("known_failures", {"error": error, "context": context})

    def record_fix(self, issue: str, fix: str, verified: bool = False) -> None:
        self.store.append(
            "verified_fixes", {"issue": issue, "fix": fix, "verified": verified}
        )

    def record_lesson(self, lesson: str, category: str = "general") -> None:
        self.store.append("lessons", {"lesson": lesson, "category": category})

    def get_facts(self) -> list[dict[str, Any]]:
        return self.store.read_all("known_facts")

    def get_failures(self) -> list[dict[str, Any]]:
        return self.store.read_all("known_failures")

    def get_fixes(self) -> list[dict[str, Any]]:
        return self.store.read_all("verified_fixes")

    def get_lessons(self) -> list[dict[str, Any]]:
        return self.store.read_all("lessons")

    def get_relevant_context(self, query: str) -> str:
        query_lower = query.lower()
        relevant = []
        for fact in self.get_facts():
            if query_lower in fact.get("fact", "").lower():
                relevant.append(f"Fact: {fact['fact']}")
        for fix in self.get_fixes():
            if query_lower in fix.get("issue", "").lower():
                relevant.append(f"Fix: {fix['issue']} → {fix['fix']}")
        for lesson in self.get_lessons():
            if query_lower in lesson.get("lesson", "").lower():
                relevant.append(f"Lesson: {lesson['lesson']}")
        return "\n".join(relevant[-10:]) if relevant else ""

    def promote_candidates(self, session_summary: str) -> list[str]:
        candidates = []
        lines = session_summary.lower().splitlines()
        for line in lines:
            if any(p in line for p in PROMOTABLE_PATTERNS):
                if not any(np in line for np in NON_PROMOTABLE_PATTERNS):
                    candidates.append(line.strip())
        return candidates[:5]

    def promote_from_session(self, session_entries: list[dict[str, Any]]) -> int:
        promoted = 0
        for entry in session_entries:
            if (
                entry.get("type") == "completion"
                and entry.get("content", {}).get("status") == "complete"
            ):
                self.record_fact("completed a goal successfully", source="session")
                promoted += 1
            if entry.get("type") == "goal":
                goal_text = str(entry.get("content", ""))
                candidates = self.promote_candidates(goal_text)
                for c in candidates:
                    self.record_fact(c, source="session")
                    promoted += 1
        return promoted
