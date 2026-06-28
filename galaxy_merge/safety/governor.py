import re
from pathlib import Path
from typing import Any

from galaxy_merge.safety.path_policy import PathPolicy
from galaxy_merge.safety.command_policy import CommandPolicy
from galaxy_merge.safety.self_protection import SelfProtectionPolicy
from galaxy_merge.safety.credential_policy import CredentialPolicy
from galaxy_merge.safety.audit import SafetyAudit


class SafetyGovernor:
    def __init__(self, workroot: Path, gm_dir: Path, audit: SafetyAudit):
        self.workroot = workroot
        self.gm_dir = gm_dir
        self.audit = audit
        self.path_policy = PathPolicy(workroot)
        self.command_policy = CommandPolicy(workroot)
        self.self_protection = SelfProtectionPolicy(workroot, gm_dir)
        self.credential_policy = CredentialPolicy(workroot)

    @property
    def is_readonly_mode(self) -> bool:
        return self.self_protection.is_inside_galaxy_merge_codebase()

    def check_path_write(self, target_path: str) -> dict[str, Any]:
        path = Path(target_path).resolve()
        sp_result = self.self_protection.check_path(path)
        if sp_result["decision"] != "allow":
            self.audit.log("path_write", target_path, sp_result)
            return sp_result
        cp_result = self.credential_policy.check_path(path)
        if cp_result["decision"] != "allow":
            self.audit.log("path_write", target_path, cp_result)
            return cp_result
        pp_result = self.path_policy.check_write(path)
        self.audit.log("path_write", target_path, pp_result)
        return pp_result

    def check_path_read(self, target_path: str) -> dict[str, Any]:
        path = Path(target_path).resolve()
        cp_result = self.credential_policy.check_path(path)
        if cp_result["decision"] != "allow":
            return cp_result
        return {"decision": "allow", "reason": "read path permitted"}

    def check_command(self, command: str) -> dict[str, Any]:
        if self.is_readonly_mode:
            first_word = command.strip().split()[0] if command.strip() else ""
            mutation_indicators = (
                "rm",
                "mv",
                "cp",
                "chmod",
                "chown",
                "dd",
                "mkfs",
                "sudo",
                "git",
                "trash",
                "install",
                "ln",
                "touch",
                "mkdir",
            )
            for indicator in mutation_indicators:
                if first_word == indicator or command.strip().startswith(indicator):
                    return {
                        "decision": "block",
                        "reason": "read-only mode: mutations disabled",
                    }

            redirect_pipe_pattern = re.compile(r"(?<!\$)[>|]")
            if redirect_pipe_pattern.search(command):
                return {
                    "decision": "block",
                    "reason": "read-only mode: redirects and pipes disabled",
                }

        sp_result = self.self_protection.check_command(command)
        if sp_result["decision"] != "allow":
            self.audit.log("command", command, sp_result)
            return sp_result
        cp_result = self.command_policy.check(command)
        self.audit.log("command", command, cp_result)
        return cp_result

    def check_credential_exposure(self, text: str) -> list[dict[str, Any]]:
        return self.credential_policy.scan_text(text)
