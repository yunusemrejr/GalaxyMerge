from typing import Any

from galaxy_merge.tools.schemas import ToolSchema, ToolResult
from galaxy_merge.fusion.reviewer import review_fusion_result


def make_completion_tools() -> list[tuple[ToolSchema, Any]]:
    async def completion_review(
        result: dict[str, Any],
        criteria: list[str] | None = None,
    ) -> ToolResult:
        review = review_fusion_result(result)
        if criteria:
            checks = []
            unmet = []
            content = str(result).lower()
            for criterion in criteria:
                if criterion.lower() in content:
                    checks.append({"criterion": criterion, "met": True})
                else:
                    checks.append({"criterion": criterion, "met": False})
                    unmet.append(criterion)
            review["criteria_checks"] = checks
            if unmet:
                review["approved"] = False
                review.setdefault("issues", []).append(
                    f"Unmet completion criteria: {', '.join(unmet)}",
                )
        return ToolResult(success=True, data=review)

    async def completion_verify(
        file_path: str,
        expected: str | None = None,
    ) -> ToolResult:
        from pathlib import Path
        target = Path(file_path)
        if not target.exists():
            return ToolResult(success=False, error=f"file not found: {file_path}")
        content = target.read_text()
        result = {
            "path": str(target),
            "exists": True,
            "size": len(content),
            "lines": content.count("\n") + 1,
        }
        if expected:
            result["matches_expected"] = expected in content
        return ToolResult(success=True, data=result)

    return [
        (ToolSchema("completion.review", "Review a completion result for quality, safety, and criteria", parameters={
            "result": {"type": "object", "required": True},
            "criteria": {"type": "array", "items": {"type": "string"}, "default": None},
        }), completion_review),
        (ToolSchema("completion.verify", "Verify a file was created/modified as expected", parameters={
            "file_path": {"type": "string", "required": True},
            "expected": {"type": "string", "default": None},
        }), completion_verify),
    ]
