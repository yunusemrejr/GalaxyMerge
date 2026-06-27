from typing import Any


class SkillMatcher:
    def match(self, skills: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
        query_lower = query.lower()
        scored = []

        for skill in skills:
            score = 0
            name = skill.get("name", "").lower()
            summary = skill.get("summary", "").lower()

            if query_lower in name:
                score += 10
            if query_lower in summary:
                score += 5

            for trigger in skill.get("triggers", []):
                if query_lower in trigger.lower():
                    score += 8

            if score > 0:
                scored.append((score, skill))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [s for _, s in scored]
