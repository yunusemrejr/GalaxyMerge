from pathlib import Path
from typing import Any

from galaxy_merge.tools.schemas import ToolSchema, ToolResult


def make_verification_tools(workroot: Path) -> list[tuple[ToolSchema, Any]]:
    async def verify_syntax(path: str) -> ToolResult:
        target = (workroot / path).resolve()
        if not target.exists():
            return ToolResult(success=False, error="file not found")

        ext = target.suffix
        if ext == ".py":
            import subprocess
            result = subprocess.run(
                ["python3", "-m", "py_compile", str(target)],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0:
                return ToolResult(success=True, data={"valid": True, "message": "Python syntax OK"})
            else:
                return ToolResult(success=True, data={"valid": False, "error": result.stderr})

        return ToolResult(success=True, data={"valid": True, "message": "no syntax check available"})

    async def verify_file_exists(path: str) -> ToolResult:
        target = (workroot / path).resolve()
        exists = target.exists()
        return ToolResult(success=True, data={
            "path": path,
            "exists": exists,
            "size": target.stat().st_size if exists else 0,
        })

    return [
        (ToolSchema("verify.syntax", "Check file syntax", parameters={
            "path": {"type": "string", "required": True},
        }), verify_syntax),
        (ToolSchema("verify.file", "Verify file exists", parameters={
            "path": {"type": "string", "required": True},
        }), verify_file_exists),
    ]
