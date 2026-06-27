import os
import shlex
import subprocess
from pathlib import Path
from typing import Any

from galaxy_merge.safety.credential_policy import CredentialPolicy


class Sandbox:
    def __init__(self, workroot: Path):
        self.workroot = workroot.resolve()
        self.credential_policy = CredentialPolicy(workroot)

    def run(
        self,
        command: str,
        cwd: Path | None = None,
        timeout_seconds: int = 60,
        env: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        import re
        SHELL_META = re.compile(r'[;|&$`(){}<>]')
        has_meta = bool(SHELL_META.search(command))

        cwd = cwd or self.workroot

        try:
            args = shlex.split(command)
        except ValueError:
            return {
                "status": "error",
                "stdout": "",
                "stderr": "Unbalanced quotes in command",
                "exit_code": -1,
            }

        safe_env = os.environ.copy()
        if env:
            safe_env.update(env)

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

        try:
            result = subprocess.run(
                args,
                cwd=str(cwd),
                timeout=timeout_seconds,
                capture_output=True,
                text=True,
                env=safe_env,
            )
        except subprocess.TimeoutExpired:
            return {
                "status": "timeout",
                "stdout": "",
                "stderr": f"Command timed out after {timeout_seconds}s",
                "exit_code": -1,
            }
        except FileNotFoundError as e:
            return {
                "status": "error",
                "stdout": "",
                "stderr": f"Command not found: {e}",
                "exit_code": -1,
            }
        except Exception as e:
            return {
                "status": "error",
                "stdout": "",
                "stderr": str(e),
                "exit_code": -1,
            }

        stdout = result.stdout or ""
        stderr = result.stderr or ""

        stdout = self.credential_policy.redact(stdout)
        stderr = self.credential_policy.redact(stderr)

        MAX_OUTPUT = 100_000
        if len(stdout) > MAX_OUTPUT:
            stdout = stdout[:MAX_OUTPUT] + f"\n... (truncated, {len(stdout)} total chars)"

        return {
            "status": "completed",
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": result.returncode,
        }
