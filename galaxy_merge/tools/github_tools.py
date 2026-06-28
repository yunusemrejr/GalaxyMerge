import os
from pathlib import Path
from typing import Any

from galaxy_merge.tools.schemas import ToolSchema, ToolResult
from galaxy_merge.github.scanner import GitHubScanner


def make_github_tools(cache_dir: Path | None = None) -> list[tuple[ToolSchema, Any]]:
    token = os.environ.get("GITHUB_TOKEN", os.environ.get("GH_TOKEN", ""))
    scanner = GitHubScanner(token=token, cache_dir=cache_dir)

    async def github_repo_scan(url: str) -> ToolResult:
        result = await scanner.scan_repo(url)
        if "error" in result:
            return ToolResult(success=False, error=result["error"])
        return ToolResult(success=True, data=result)

    return [
        (
            ToolSchema(
                "github.repo.scan",
                "Scan a GitHub repository and return metadata + file tree",
                parameters={
                    "url": {"type": "string", "required": True},
                },
            ),
            github_repo_scan,
        ),
    ]
