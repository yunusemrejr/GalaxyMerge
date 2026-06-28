from pathlib import Path
from typing import Any

from galaxy_merge.tools.schemas import ToolSchema, ToolResult
from galaxy_merge.safety.sandbox import Sandbox
from galaxy_merge.safety.governor import SafetyGovernor
from galaxy_merge.locations.classifier import LocationClassifier
from galaxy_merge.locations.deployment_policy import DeploymentPolicy


def make_shell_tools(
    workroot: Path,
    safety: SafetyGovernor,
    sandbox: Sandbox,
    location_classifier: LocationClassifier | None = None,
    deployment_policy: DeploymentPolicy | None = None,
) -> list[tuple[ToolSchema, Any]]:
    tools = []

    async def shell_run(
        command: str,
        cwd: str | None = None,
        timeout: int = 60,
    ) -> ToolResult:
        safety_result = safety.check_command(command)
        if safety_result["decision"] == "block":
            return ToolResult(
                success=False,
                error=f"safety blocked: {safety_result['reason']}",
                blocked=True,
            )

        if safety_result["decision"] == "allow_with_audit":
            if deployment_policy and location_classifier:
                cls = location_classifier.classify(command, "command")
                policy_result = deployment_policy.check(cls["classification"], command)
                if policy_result["decision"] != "allow":
                    return ToolResult(
                        success=False,
                        error=f"remote mutation blocked by deployment policy: {policy_result['reason']}",
                        blocked=True,
                    )
            else:
                return ToolResult(
                    success=False,
                    error=f"remote mutation blocked (no deployment policy configured): {safety_result['reason']}",
                    blocked=True,
                )

        cmd_cwd = (workroot / cwd).resolve() if cwd else workroot
        result = sandbox.run(command, cwd=cmd_cwd, timeout_seconds=timeout)

        return ToolResult(
            success=result["exit_code"] == 0,
            data={
                "stdout": result["stdout"],
                "stderr": result["stderr"],
                "exit_code": result["exit_code"],
                "status": result["status"],
            },
        )

    tools.append(
        (
            ToolSchema(
                "shell.run",
                "Run a shell command in a sandboxed environment",
                mutates=True,
                requires_safety=True,
                parameters={
                    "command": {"type": "string", "required": True},
                    "cwd": {"type": "string", "default": None},
                    "timeout": {"type": "integer", "default": 60},
                },
            ),
            shell_run,
        )
    )

    return tools
