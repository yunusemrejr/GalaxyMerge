import subprocess
from pathlib import Path
from typing import Any

from galaxy_merge.safety.credential_policy import CredentialPolicy
from galaxy_merge.tools.schemas import ToolResult, ToolSchema


def make_security_tools(workroot: Path, install_dir: Path | None = None) -> list[tuple[ToolSchema, Any]]:
    scanner_root = install_dir or workroot
    scanner = scanner_root / "scripts" / "secret_scan.sh"
    redactor = CredentialPolicy(workroot)

    def run_scan(include_history: bool = False) -> dict[str, Any]:
        if not scanner.exists():
            return {
                "success": False,
                "error": "secret scanner not found",
                "scanner": str(scanner),
            }
        args = [str(scanner)]
        if include_history:
            args.append("--history")
        result = subprocess.run(
            args,
            cwd=str(scanner_root),
            capture_output=True,
            text=True,
            timeout=120,
        )
        return {
            "success": result.returncode == 0,
            "exit_code": result.returncode,
            "stdout": redactor.redact(result.stdout),
            "stderr": redactor.redact(result.stderr),
            "scanner": str(scanner),
            "history": include_history,
        }

    async def secret_scan(include_history: bool = False) -> ToolResult:
        result = run_scan(include_history)
        if not result["success"]:
            return ToolResult(success=False, error=result.get("stderr") or result.get("error"), data=result)
        return ToolResult(success=True, data=result)

    async def public_safety_audit(include_history: bool = True) -> ToolResult:
        scan = run_scan(include_history)
        git_status = subprocess.run(
            ["git", "status", "--short"],
            cwd=str(scanner_root),
            capture_output=True,
            text=True,
            timeout=30,
        )
        is_clean = git_status.returncode == 0 and not git_status.stdout.strip()
        return ToolResult(success=scan["success"] and git_status.returncode == 0, data={
            "secret_scan": scan,
            "git_status": redactor.redact(git_status.stdout).splitlines(),
            "git_status_error": redactor.redact(git_status.stderr),
            "public_ready": scan["success"] and is_clean,
        })

    return [
        (ToolSchema("secret.scan", "Scan public candidate files for secret-like values", parameters={
            "include_history": {"type": "boolean", "default": False},
        }), secret_scan),
        (ToolSchema("repo.public_safety.audit", "Run public-repository release safety checks", parameters={
            "include_history": {"type": "boolean", "default": True},
        }), public_safety_audit),
    ]
