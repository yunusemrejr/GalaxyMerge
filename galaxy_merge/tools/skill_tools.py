from typing import Any

from galaxy_merge.tools.schemas import ToolSchema, ToolResult
from galaxy_merge.skills.registry import SkillRegistry


def make_skill_tools(registry: SkillRegistry) -> list[tuple[ToolSchema, Any]]:
    async def skill_search(query: str) -> ToolResult:
        results = registry.search(query)
        return ToolResult(
            success=True,
            data={
                "query": query,
                "matches": results,
                "count": len(results),
            },
        )

    return [
        (
            ToolSchema(
                "skill.search",
                "Search for matching skills",
                parameters={
                    "query": {"type": "string", "required": True},
                },
            ),
            skill_search,
        ),
    ]
