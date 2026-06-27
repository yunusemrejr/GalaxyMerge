import re
from typing import Any

TASK_TYPE_PATTERNS: list[tuple[str, str]] = [
    (r"(fix|bug|error|issue|broken)", "bug_fix"),
    (r"(refactor|restructure|rewrite|reorganize)", "large_refactor"),
    (r"(add|feature|implement|create|new)", "feature"),
    (r"(update|change|modify|edit)", "small_edit"),
    (r"(test|spec|coverage)", "testing"),
    (r"(doc|readme|comment|document)", "documentation"),
    (r"(config|configure|setup)", "configuration"),
]


class GoalEngine:
    def parse(self, goal: str) -> dict[str, Any]:
        goal_lower = goal.lower()

        task_type = "small_edit"
        for pattern, ttype in TASK_TYPE_PATTERNS:
            if re.search(pattern, goal_lower):
                task_type = ttype
                break

        files = self._extract_files(goal)
        scope = self._estimate_scope(goal)

        return {
            "goal": goal,
            "task_type": task_type,
            "mentioned_files": files,
            "estimated_scope": scope,
            "parsed_at": __import__("datetime").datetime.now().isoformat(),
        }

    def _extract_files(self, goal: str) -> list[str]:
        paths = re.findall(r'[\w/.-]+\.\w+', goal)
        return [p for p in paths if "/" in p or "." in p]

    def _estimate_scope(self, goal: str) -> str:
        goal_len = len(goal)
        if goal_len < 50:
            return "small"
        elif goal_len < 200:
            return "medium"
        return "large"
