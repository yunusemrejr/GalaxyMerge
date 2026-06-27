from pathlib import Path
from typing import Any

from galaxy_merge.tools.schemas import ToolSchema, ToolResult
from galaxy_merge.safety.credential_policy import CredentialPolicy


def make_git_tools(workroot: Path) -> list[tuple[ToolSchema, Any]]:
    tools = []
    _cred_policy = CredentialPolicy(workroot)

    def _run_git(args: list[str]) -> dict[str, Any]:
        import os
        import subprocess
        try:
            safe_env = os.environ.copy()
            redact_keys = [
                "API_KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL",
                "OPENAI", "ANTHROPIC", "DEEPSEEK", "GEMINI",
                "MINIMAX", "STEPFUN", "STREAMLAKE", "KIMI",
            ]
            for key in list(safe_env.keys()):
                for rk in redact_keys:
                    if rk in key.upper():
                        safe_env[key] = "***REDACTED***"
                        break
            result = subprocess.run(
                ["git"] + args,
                cwd=str(workroot),
                capture_output=True,
                text=True,
                timeout=30,
                env=safe_env,
            )
            stdout = result.stdout or ""
            stderr = result.stderr or ""
            stdout = _cred_policy.redact(stdout)
            stderr = _cred_policy.redact(stderr)
            return {
                "stdout": stdout,
                "stderr": stderr,
                "exit_code": result.returncode,
            }
        except FileNotFoundError:
            return {"stdout": "", "stderr": "git not found", "exit_code": -1}
        except Exception as e:
            return {"stdout": "", "stderr": str(e), "exit_code": -1}

    async def git_status() -> ToolResult:
        result = _run_git(["status", "--short"])
        if result["exit_code"] != 0:
            return ToolResult(success=False, error=result["stderr"])
        return ToolResult(success=True, data={
            "status": result["stdout"].splitlines(),
            "is_clean": len(result["stdout"].strip()) == 0,
        })

    async def git_diff(staged: bool = False) -> ToolResult:
        args = ["diff"]
        if staged:
            args.append("--staged")
        result = _run_git(args)
        if result["exit_code"] != 0:
            return ToolResult(success=False, error=result["stderr"])
        return ToolResult(success=True, data={
            "diff": result["stdout"],
            "has_changes": len(result["stdout"].strip()) > 0,
        })

    async def git_branch() -> ToolResult:
        result = _run_git(["branch", "--show-current"])
        if result["exit_code"] != 0:
            return ToolResult(success=False, error=result["stderr"])
        return ToolResult(success=True, data={"branch": result["stdout"].strip()})

    async def git_log(count: int = 10) -> ToolResult:
        result = _run_git([
            "log", f"--max-count={count}",
            "--oneline", "--decorate",
        ])
        if result["exit_code"] != 0:
            return ToolResult(success=False, error=result["stderr"])
        return ToolResult(success=True, data={
            "log": result["stdout"].splitlines(),
        })

    tools.append((
        ToolSchema("git.status", "Show git working tree status"),
        git_status,
    ))

    tools.append((
        ToolSchema("git.diff", "Show git diff", parameters={
            "staged": {"type": "boolean", "default": False},
        }),
        git_diff,
    ))

    tools.append((
        ToolSchema("git.branch", "Show current git branch"),
        git_branch,
    ))

    tools.append((
        ToolSchema("git.log", "Show recent git log", parameters={
            "count": {"type": "integer", "default": 10},
        }),
        git_log,
    ))

    return tools
