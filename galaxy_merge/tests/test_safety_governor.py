"""Unit tests for Safety Governor policies.

Tests the actual public API of the safety modules.
"""

import pytest
from pathlib import Path
from galaxy_merge.safety.path_policy import PathPolicy
from galaxy_merge.safety.command_policy import CommandPolicy, BLOCKED_COMMANDS
from galaxy_merge.safety.credential_policy import CredentialPolicy
from galaxy_merge.safety.governor import SafetyGovernor
from galaxy_merge.safety.audit import SafetyAudit


class TestPathPolicy:
    def test_check_write_blocks_system_roots(self, tmp_path):
        policy = PathPolicy(tmp_path)
        result = policy.check_write(Path("/etc/passwd"))
        assert result["decision"] == "block"

    def test_check_write_blocks_home_secrets(self, tmp_path):
        policy = PathPolicy(tmp_path)
        home = Path.home()
        result = policy.check_write(home / ".ssh" / "id_rsa")
        assert result["decision"] == "block"

    def test_check_write_allows_project_files(self, tmp_path):
        policy = PathPolicy(tmp_path)
        test_file = tmp_path / "src" / "main.py"
        test_file.parent.mkdir()
        test_file.write_text("print('hello')")
        result = policy.check_write(test_file)
        assert result["decision"] == "allow"

    def test_check_read_allows_project_files(self, tmp_path):
        policy = PathPolicy(tmp_path)
        test_file = tmp_path / "src" / "main.py"
        test_file.parent.mkdir()
        test_file.write_text("print('hello')")
        result = policy.check_read(test_file)
        assert result["decision"] == "allow"


class TestCommandPolicy:
    def test_check_blocks_sudo_commands(self, tmp_path):
        policy = CommandPolicy(tmp_path)
        assert policy.check("sudo rm -rf /")["decision"] == "block"
        assert policy.check("sudo mv /etc /tmp")["decision"] == "block"

    def test_check_blocks_chmod_777(self, tmp_path):
        policy = CommandPolicy(tmp_path)
        assert policy.check("chmod -R 777 /")["decision"] == "block"

    def test_check_allows_safe_commands(self, tmp_path):
        policy = CommandPolicy(tmp_path)
        assert policy.check("ls -la")["decision"] == "allow"
        assert policy.check("cat file.txt")["decision"] == "allow"
        assert policy.check("git status")["decision"] == "allow"

    def test_blocked_commands_list_not_empty(self):
        assert len(BLOCKED_COMMANDS) > 0
        assert "sudo rm" in BLOCKED_COMMANDS
        assert "chmod -R 777" in BLOCKED_COMMANDS


class TestCredentialPolicy:
    def test_preserves_normal_text(self, tmp_path):
        policy = CredentialPolicy(tmp_path)
        text = "This is a normal sentence with no secrets."
        redacted = policy.redact(text)
        assert redacted == text


class TestSafetyGovernor:
    def test_governor_initializes(self, tmp_path):
        audit = SafetyAudit(tmp_path / ".gm")
        governor = SafetyGovernor(tmp_path, tmp_path / ".gm", audit)
        assert governor is not None

    def test_governor_check_path_write(self, tmp_path):
        audit = SafetyAudit(tmp_path / ".gm")
        governor = SafetyGovernor(tmp_path, tmp_path / ".gm", audit)
        test_file = tmp_path / "test.txt"
        test_file.write_text("test")
        result = governor.check_path_write(str(test_file))
        assert isinstance(result, dict)
        assert "decision" in result

    def test_governor_check_command(self, tmp_path):
        audit = SafetyAudit(tmp_path / ".gm")
        governor = SafetyGovernor(tmp_path, tmp_path / ".gm", audit)
        result = governor.check_command("ls -la")
        assert isinstance(result, dict)
        assert "decision" in result

    def test_governor_is_readonly_mode(self, tmp_path):
        audit = SafetyAudit(tmp_path / ".gm")
        governor = SafetyGovernor(tmp_path, tmp_path / ".gm", audit)
        # is_readonly_mode is a property, not a method
        assert isinstance(governor.is_readonly_mode, bool)
