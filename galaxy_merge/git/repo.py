import subprocess
from pathlib import Path
from typing import Any

from galaxy_merge.safety.credential_policy import CredentialPolicy


class GitRepo:
    def __init__(self, workroot: Path):
        self.workroot = workroot.resolve()
        self._git_dir = self.workroot / ".git"
        self._credential_policy = CredentialPolicy(workroot)

    @property
    def is_repo(self) -> bool:
        return self._git_dir.exists()

    def _run(self, args: list[str]) -> dict[str, Any]:
        try:
            result = subprocess.run(
                ["git"] + args,
                cwd=str(self.workroot),
                capture_output=True,
                text=True,
                timeout=30,
            )
            return {
                "stdout": self._credential_policy.redact(result.stdout),
                "stderr": self._credential_policy.redact(result.stderr),
                "exit_code": result.returncode,
            }
        except FileNotFoundError:
            return {"stdout": "", "stderr": "git not found", "exit_code": -1}
        except subprocess.TimeoutExpired:
            return {"stdout": "", "stderr": "timeout", "exit_code": -1}
        except Exception as e:
            return {"stdout": "", "stderr": str(e), "exit_code": -1}

    def status(self) -> dict[str, Any]:
        return self._run(["status", "--short"])

    def diff(self, staged: bool = False) -> dict[str, Any]:
        args = ["diff"]
        if staged:
            args.append("--staged")
        return self._run(args)

    def current_branch(self) -> str:
        result = self._run(["branch", "--show-current"])
        return result.get("stdout", "").strip()

    def log(self, count: int = 10) -> list[str]:
        result = self._run(
            [
                "log",
                f"--max-count={count}",
                "--oneline",
                "--decorate",
            ]
        )
        return result.get("stdout", "").splitlines() if result.get("stdout") else []

    def is_clean(self) -> bool:
        result = self.status()
        return len(result.get("stdout", "").strip()) == 0
