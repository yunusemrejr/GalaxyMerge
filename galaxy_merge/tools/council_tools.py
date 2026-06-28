from typing import Any

from galaxy_merge.tools.schemas import ToolSchema, ToolResult
from galaxy_merge.fusion.council import Council
from galaxy_merge.fusion.synthesizer import Synthesizer
from galaxy_merge.fusion.reviewer import review_fusion_result


def make_council_tools(
    provider_registry,
    fusion_config: dict[str, Any],
    event_log=None,
    session_id: str = "",
) -> list[tuple[ToolSchema, Any]]:
    synthesizer = Synthesizer()

    async def council_spawn(
        goal: str,
        council_name: str | None = None,
        roles: dict[str, Any] | None = None,
    ) -> ToolResult:
        config = fusion_config.copy()
        if council_name:
            councils = config.get("councils", {})
            named = councils.get(council_name)
            if not named:
                return ToolResult(
                    success=False, error=f"council '{council_name}' not found in config"
                )
            config = named
        if roles:
            config["roles"] = roles

        council = Council(
            provider_registry, config, goal, event_log=event_log, session_id=session_id
        )
        results = await council.execute()

        return ToolResult(
            success=True,
            data={
                "council": council_name or "default",
                "goal": goal,
                "results": results,
                "roles_executed": list(results.keys()),
                "degraded_roles": council.get_degraded_roles(),
                "failed_roles": council.get_failed_roles(),
            },
        )

    async def council_synthesize(
        council_results: dict[str, Any],
    ) -> ToolResult:
        fused = synthesizer.fuse(council_results)
        return ToolResult(
            success=True,
            data={
                "output": fused,
            },
        )

    async def council_review(
        fusion_result: dict[str, Any],
    ) -> ToolResult:
        review = review_fusion_result(fusion_result)
        return ToolResult(success=True, data=review)

    return [
        (
            ToolSchema(
                "council.spawn",
                "Spawn a council of AI roles to work on a goal in parallel",
                parameters={
                    "goal": {"type": "string", "required": True},
                    "council_name": {"type": "string", "default": None},
                    "roles": {"type": "object", "default": None},
                },
            ),
            council_spawn,
        ),
        (
            ToolSchema(
                "council.synthesize",
                "Synthesize council results into fused output",
                parameters={
                    "council_results": {"type": "object", "required": True},
                    "synthesis_mode": {
                        "type": "string",
                        "default": "evidence_weighted",
                    },
                },
            ),
            council_synthesize,
        ),
        (
            ToolSchema(
                "council.review",
                "Review a fusion result for quality and safety",
                parameters={
                    "fusion_result": {"type": "object", "required": True},
                },
            ),
            council_review,
        ),
    ]
