"""
Red-team safety tests V2: Cover every bypass found during security audit.
All attacks MUST be blocked. If any test fails, a safety boundary has been breached.
"""


import pytest

pytestmark = [pytest.mark.unit]
import os
import tempfile
from pathlib import Path

from galaxy_merge.safety.governor import SafetyGovernor
from galaxy_merge.safety.command_policy import CommandPolicy
from galaxy_merge.safety.path_policy import PathPolicy
from galaxy_merge.safety.credential_policy import CredentialPolicy
from galaxy_merge.safety.self_protection import SelfProtectionPolicy
from galaxy_merge.safety.audit import SafetyAudit
from galaxy_merge.safety.sandbox import Sandbox


@pytest.fixture
def workroot(tmp_path):
    return tmp_path


@pytest.fixture
def gm_dir(workroot):
    d = workroot / ".gm"
    d.mkdir(parents=True, exist_ok=True)
    return d


@pytest.fixture
def audit(workroot):
    return SafetyAudit(workroot / "audit.jsonl")


@pytest.fixture
def gov(workroot, gm_dir, audit):
    return SafetyGovernor(workroot, gm_dir, audit)


@pytest.fixture
def policy(workroot):
    return CommandPolicy(workroot)


# =============================================================================
# CRIT-4: rm -rf variant bypasses (combined flags, --no-preserve-root, etc.)
# =============================================================================

class TestRmVariantBypasses:
    def test_block_rm_rfv_root(self, gov):
        assert gov.check_command("rm -rfv /")["decision"] == "block"

    def test_block_rm_rf_no_preserve_root(self, gov):
        assert gov.check_command("rm -rf --no-preserve-root /")["decision"] == "block"

    def test_block_rm_r_f_root(self, gov):
        assert gov.check_command("rm -r -f /")["decision"] == "block"

    def test_block_rm_rf_separate_flags(self, gov):
        assert gov.check_command("rm -r --force /")["decision"] == "block"

    def test_block_rm_recursive(self, gov):
        assert gov.check_command("rm --recursive --force /")["decision"] == "block"

    def test_block_bin_rm_rf(self, gov):
        assert gov.check_command("/bin/rm -rf /")["decision"] == "block"

    def test_block_usr_bin_rm_rf(self, gov):
        assert gov.check_command("/usr/bin/rm -rf /")["decision"] == "block"

    def test_block_rm_rf_etc_glob(self, gov):
        result = gov.check_command("rm -rf /etc/*")
        assert result["decision"] == "block"

    def test_block_rm_rf_etc_with_comment(self, gov):
        assert gov.check_command("rm -rf /etc ; echo done")["decision"] == "block"

    def test_block_rm_rf_var_log(self, gov):
        assert gov.check_command("rm -rfv /var/log")["decision"] == "block"

    def test_block_rm_rf_opt_app(self, gov):
        assert gov.check_command("rm -rf --interactive=never /opt/app")["decision"] == "block"

    def test_block_rm_r_etc(self, gov):
        assert gov.check_command("rm -r /etc")["decision"] == "block"

    def test_block_rm_rf_multiple_targets(self, gov):
        assert gov.check_command("rm -rf /etc /var/log")["decision"] == "block"

    def test_block_rm_rf_tilde(self, gov):
        assert gov.check_command("rm -rf ~")["decision"] == "block"

    def test_block_rm_rf_home(self, gov):
        assert gov.check_command("rm -rf /home")["decision"] == "block"


# =============================================================================
# CRIT-3: SUDO case bypass
# =============================================================================

class TestSudoCaseBypasses:
    def test_block_sudo_uppercase(self, gov):
        assert gov.check_command("SUDO rm -rf /")["decision"] == "block"

    def test_block_sudo_capitalized(self, gov):
        assert gov.check_command("Sudo rm -rf /")["decision"] == "block"

    def test_block_sudo_mixed_case(self, gov):
        assert gov.check_command("SuDo rm -rf /")["decision"] == "block"

    def test_block_pkexec_uppercase(self, gov):
        assert gov.check_command("PKEXEC rm -rf /")["decision"] == "block"


# =============================================================================
# CRIT-5: Full-path binary bypass
# =============================================================================

class TestFullPathBinaryBypasses:
    def test_block_usr_bin_git_push(self, gov):
        result = gov.check_command("/usr/bin/git push origin main")
        assert result["decision"] != "allow"

    def test_block_usr_bin_ssh(self, gov):
        result = gov.check_command("/usr/bin/ssh user@host")
        assert result["decision"] != "allow"

    def test_block_usr_bin_scp(self, gov):
        result = gov.check_command("/usr/bin/scp file user@host:/path")
        assert result["decision"] != "allow"

    def test_block_bin_ssh(self, gov):
        result = gov.check_command("/bin/ssh user@host")
        assert result["decision"] != "allow"

    def test_block_git_push_full_path(self, gov):
        result = gov.check_command("/usr/local/bin/git push origin main")
        assert result["decision"] != "allow"


# =============================================================================
# CRIT-6: dd variant bypass
# =============================================================================

class TestDdVariantBypasses:
    def test_block_dd_of_first(self, gov):
        assert gov.check_command("dd of=/etc/passwd if=/dev/zero")["decision"] == "block"

    def test_block_dd_to_shadow(self, gov):
        assert gov.check_command("dd if=/dev/random of=/etc/shadow")["decision"] == "block"

    def test_block_dd_to_sudoers(self, gov):
        assert gov.check_command("dd if=/dev/null of=/etc/sudoers")["decision"] == "block"

    def test_block_usr_bin_dd(self, gov):
        assert gov.check_command("/usr/bin/dd if=/dev/zero of=/etc/passwd")["decision"] == "block"

    def test_block_dd_to_boot(self, gov):
        assert gov.check_command("dd if=/dev/random of=/boot/evil.img")["decision"] == "block"

    def test_block_dd_block_size_variant(self, gov):
        assert gov.check_command("dd bs=4M if=/dev/zero of=/etc/cron.d/evil")["decision"] == "block"

    def test_block_dd_read_system_device_to_safe_output(self, gov):
        """dd if=/dev/sda of=/tmp/backup.img must block even when of= is safe.

        Reading raw system devices is itself dangerous regardless of the
        destination. The old check only inspected ``of=`` once a non-system
        ``of=`` was present, silently skipping the ``if=`` system check.
        """
        assert gov.check_command("dd if=/dev/sda of=/tmp/backup.img")["decision"] == "block"

    def test_block_dd_read_system_partition_to_safe_output(self, gov):
        assert gov.check_command("dd if=/dev/sda1 of=/tmp/x.img")["decision"] == "block"

    def test_block_dd_if_system_even_when_of_safe(self, gov):
        assert gov.check_command("dd if=/dev/sda of=./safe.bin")["decision"] == "block"


# =============================================================================
# CRIT-1: Readonly mode redirect/pipe bypass
# =============================================================================

class TestReadOnlyModeRedirectBypasses:
    def test_readonly_blocks_echo_redirect(self, workroot, gm_dir, audit):
        import galaxy_merge
        pkg_dir = Path(galaxy_merge.__file__).resolve().parent.parent
        ro_gov = SafetyGovernor(pkg_dir, pkg_dir / ".gm", audit)
        if ro_gov.is_readonly_mode:
            result = ro_gov.check_command("echo hello > /etc/passwd")
            assert result["decision"] == "block"

    def test_readonly_blocks_echo_append(self, workroot, gm_dir, audit):
        import galaxy_merge
        pkg_dir = Path(galaxy_merge.__file__).resolve().parent.parent
        ro_gov = SafetyGovernor(pkg_dir, pkg_dir / ".gm", audit)
        if ro_gov.is_readonly_mode:
            result = ro_gov.check_command("echo test >> /etc/shadow")
            assert result["decision"] == "block"

    def test_readonly_blocks_cat_redirect(self, workroot, gm_dir, audit):
        import galaxy_merge
        pkg_dir = Path(galaxy_merge.__file__).resolve().parent.parent
        ro_gov = SafetyGovernor(pkg_dir, pkg_dir / ".gm", audit)
        if ro_gov.is_readonly_mode:
            result = ro_gov.check_command("cat file > /etc/output")
            assert result["decision"] == "block"

    def test_readonly_blocks_pipe_anywhere(self, workroot, gm_dir, audit):
        import galaxy_merge
        pkg_dir = Path(galaxy_merge.__file__).resolve().parent.parent
        ro_gov = SafetyGovernor(pkg_dir, pkg_dir / ".gm", audit)
        if ro_gov.is_readonly_mode:
            result = ro_gov.check_command("cat file | grep test")
            assert result["decision"] == "block"


# =============================================================================
# MED-1: Python/Node code injection in safe list
# =============================================================================

class TestCodeInjectionBypasses:
    def test_block_python_os_system(self, gov):
        result = gov.check_command("python3 -c \"import os; os.system('rm -rf /')\"")
        assert result["decision"] == "block"

    def test_block_python_subprocess(self, gov):
        result = gov.check_command("python3 -c \"import subprocess; subprocess.run(['rm', '-rf', '/'])\"")
        assert result["decision"] == "block"

    def test_block_python_exec(self, gov):
        result = gov.check_command("python3 -c \"exec('import os; os.system(\\\"rm -rf /etc\\\")')\"")
        assert result["decision"] == "block"

    def test_block_node_child_process(self, gov):
        result = gov.check_command("node -e \"require('child_process').execSync('rm -rf /')\"")
        assert result["decision"] == "block"

    def test_block_node_spawn(self, gov):
        result = gov.check_command("node -e \"require('child_process').spawn('rm', ['-rf', '/'])\"")
        assert result["decision"] == "block"

    def test_block_python2_os_system(self, gov):
        result = gov.check_command("python2 -c \"import os; os.system('rm -rf /etc')\"")
        assert result["decision"] == "block"


# =============================================================================
# MED-2: Git hooks persistence
# =============================================================================

class TestGitHookWrites:
    def test_block_git_hooks_pre_commit(self, gov, workroot):
        assert gov.check_path_write(str(workroot / ".git" / "hooks" / "pre-commit"))["decision"] == "block"

    def test_block_git_hooks_post_commit(self, gov, workroot):
        assert gov.check_path_write(str(workroot / ".git" / "hooks" / "post-commit"))["decision"] == "block"

    def test_block_git_config_write(self, gov, workroot):
        assert gov.check_path_write(str(workroot / ".git" / "config"))["decision"] == "block"

    def test_block_git_hooks_applypatch_msg(self, gov, workroot):
        assert gov.check_path_write(str(workroot / ".git" / "hooks" / "applypatch-msg"))["decision"] == "block"


# =============================================================================
# MED-3: Credential read blocking
# =============================================================================

class TestCredentialReadBlocking:
    def test_block_read_env_file(self, tmp_path):
        policy = PathPolicy(tmp_path)
        result = policy.check_read(tmp_path / ".env")
        assert result["decision"] == "block"

    def test_block_read_credentials_json(self, tmp_path):
        policy = PathPolicy(tmp_path)
        result = policy.check_read(tmp_path / "credentials.json")
        assert result["decision"] == "block"

    def test_block_read_id_rsa(self, tmp_path):
        policy = PathPolicy(tmp_path)
        result = policy.check_read(tmp_path / ".ssh" / "id_rsa")
        assert result["decision"] == "block"

    def test_block_read_id_ed25519(self, tmp_path):
        policy = PathPolicy(tmp_path)
        result = policy.check_read(tmp_path / ".ssh" / "id_ed25519")
        assert result["decision"] == "block"

    def test_block_read_pem_key(self, tmp_path):
        policy = PathPolicy(tmp_path)
        result = policy.check_read(tmp_path / "server.key")
        assert result["decision"] == "block"

    def test_block_read_npmrc(self, tmp_path):
        policy = PathPolicy(tmp_path)
        result = policy.check_read(tmp_path / ".npmrc")
        assert result["decision"] == "block"

    def test_block_read_pypirc(self, tmp_path):
        policy = PathPolicy(tmp_path)
        result = policy.check_read(tmp_path / ".pypirc")
        assert result["decision"] == "block"

    def test_block_read_service_account_key(self, tmp_path):
        policy = PathPolicy(tmp_path)
        result = policy.check_read(tmp_path / "service-account-key.json")
        assert result["decision"] == "block"

    def test_block_read_token_json(self, tmp_path):
        policy = PathPolicy(tmp_path)
        result = policy.check_read(tmp_path / "token.json")
        assert result["decision"] == "block"

    def test_block_read_netrc(self, tmp_path):
        policy = PathPolicy(tmp_path)
        result = policy.check_read(tmp_path / ".netrc")
        assert result["decision"] == "block"

    def test_block_read_gitconfig(self, tmp_path):
        policy = PathPolicy(tmp_path)
        result = policy.check_read(tmp_path / ".gitconfig")
        assert result["decision"] == "block"

    def test_allow_read_git_dir_config(self, tmp_path):
        policy = PathPolicy(tmp_path)
        result = policy.check_read(tmp_path / ".git" / "config")
        assert result["decision"] == "allow"

    def test_block_read_docker_config(self, tmp_path):
        policy = PathPolicy(tmp_path)
        result = policy.check_read(tmp_path / ".docker" / "config.json")
        assert result["decision"] == "block"

    def test_allow_read_regular_file(self, tmp_path):
        policy = PathPolicy(tmp_path)
        regular = tmp_path / "src" / "main.py"
        result = policy.check_read(regular)
        assert result["decision"] == "allow"


# =============================================================================
# MED-5: trash command on system files
# =============================================================================

class TestTrashCommand:
    def test_block_trash_etc(self, gov):
        assert gov.check_command("trash /etc/passwd")["decision"] == "block"

    def test_block_trash_bin(self, gov):
        assert gov.check_command("trash /bin/sh")["decision"] == "block"

    def test_block_trash_usr(self, gov):
        assert gov.check_command("trash /usr/bin/python3")["decision"] == "block"

    def test_block_trash_ssh(self, gov):
        assert gov.check_command("trash ~/.ssh/authorized_keys")["decision"] == "block"

    def test_block_trash_root(self, gov):
        assert gov.check_command("trash /root/.bashrc")["decision"] == "block"


# =============================================================================
# Self-protection: inside-codebase detection + bypass attempts
# =============================================================================

class TestSelfProtectionAdvanced:
    def test_block_self_mod_write_governor(self, gov):
        import galaxy_merge
        pkg = Path(galaxy_merge.__file__).resolve().parent.parent
        result = gov.check_path_write(str(pkg / "galaxy_merge" / "safety" / "governor.py"))
        assert result["decision"] == "block"

    def test_block_self_mod_write_pyproject(self, gov):
        import galaxy_merge
        pkg = Path(galaxy_merge.__file__).resolve().parent.parent
        result = gov.check_path_write(str(pkg / "pyproject.toml"))
        assert result["decision"] == "block"

    def test_block_self_mod_mv_source(self, gov):
        result = gov.check_command("mv galaxy_merge/safety/governor.py /tmp/")
        assert result["decision"] == "block"

    def test_block_self_mod_rm_gm(self, gov):
        result = gov.check_command("rm -rf .gm/")
        assert result["decision"] == "block"

    def test_block_self_mod_rm_pyproject(self, gov):
        result = gov.check_command("rm pyproject.toml")
        assert result["decision"] == "block"


# =============================================================================
# Location classifier edge cases
# =============================================================================

class TestLocationClassifierEdgeCases:
    def test_block_git_push_force(self, gov):
        result = gov.check_command("git push --force origin main")
        assert result["decision"] != "allow"

    def test_block_git_push_force_with_lease(self, gov):
        result = gov.check_command("git push --force-with-lease origin main")
        assert result["decision"] != "allow"

    def test_block_scp_recursive(self, gov):
        result = gov.check_command("scp -r . user@host:/remote")
        assert result["decision"] != "allow"

    def test_block_rsync_delete(self, gov):
        result = gov.check_command("rsync -a --delete ./ user@host:/www")
        assert result["decision"] != "allow"

    def test_block_ansible(self, gov):
        result = gov.check_command("ansible-playbook -i prod deploy.yml")
        assert result["decision"] != "allow"

    def test_block_kubectl_apply(self, gov):
        result = gov.check_command("kubectl apply -f prod.yaml")
        assert result["decision"] != "allow"

    def test_block_terraform_apply(self, gov):
        result = gov.check_command("terraform apply -auto-approve")
        assert result["decision"] != "allow"

    def test_block_aws_s3_cp(self, gov):
        result = gov.check_command("aws s3 cp ./local s3://bucket/")
        assert result["decision"] != "allow"


# =============================================================================
# CRIT-2: allow_with_audit enforcement verification
# =============================================================================

class TestAllowWithAuditEnforcement:
    def test_allow_with_audit_not_equal_allow(self, gov):
        result = gov.check_command("git push origin main")
        assert result["decision"] == "allow_with_audit"
        assert result["decision"] != "allow"

    def test_allow_with_audit_not_equal_allow_ssh(self, gov):
        result = gov.check_command("ssh user@host command")
        assert result["decision"] == "allow_with_audit"
        assert result["decision"] != "allow"

    def test_allow_with_audit_not_equal_allow_scp(self, gov):
        result = gov.check_command("scp file user@host:/path")
        assert result["decision"] == "allow_with_audit"
        assert result["decision"] != "allow"


# =============================================================================
# Environment variable edge cases
# =============================================================================

class TestEnvVarEdgeCases:
    def test_redact_openai_env_ref(self, gov):
        text = "echo $OPENAI_API_KEY"
        redacted = gov.credential_policy.redact(text)
        assert "OPENAI_API_KEY" in redacted
        assert not redacted.endswith("$OPENAI_API_KEY")

    def test_redact_deepseek_env_ref(self, gov):
        text = "echo ${DEEPSEEK_API_KEY}"
        redacted = gov.credential_policy.redact(text)
        assert "DEEPSEEK_API_KEY" in redacted
        assert not redacted.endswith("${DEEPSEEK_API_KEY}")

    def test_redact_github_token_env(self, gov):
        text = "echo $GITHUB_TOKEN"
        redacted = gov.credential_policy.redact(text)
        assert "GITHUB_TOKEN" in redacted
        assert not redacted.endswith("$GITHUB_TOKEN")


# =============================================================================
# Audit trail completeness
# =============================================================================

class TestSafetyAuditCompleteness:
    def test_audit_logs_blocked_commands(self, gov, audit):
        gov.check_command("rm -rf /")
        recent = audit.recent(10)
        blocked = [r for r in recent if r["decision"] == "block"]
        assert len(blocked) >= 1

    def test_audit_logs_allow_with_audit(self, gov, audit):
        gov.check_command("git push origin main")
        recent = audit.recent(10)
        audited = [r for r in recent if r["decision"] == "allow_with_audit"]
        assert len(audited) >= 1

    def test_audit_log_has_timestamp(self, gov, audit):
        gov.check_command("rm -rf /etc")
        recent = audit.recent(5)
        assert "time" in recent[0]

    def test_audit_log_has_all_fields(self, gov, audit):
        gov.check_path_write("/etc/passwd")
        recent = audit.recent(5)
        entry = recent[0]
        assert all(k in entry for k in ("time", "type", "target", "decision", "reason"))


# =============================================================================
# Sandbox security enforcement
# =============================================================================

class TestSandboxAdvanced:
    def test_sandbox_no_shell_true(self, workroot):
        sandbox = Sandbox(workroot)
        result = sandbox.run("echo hello", env={"TEST_VAR": "test_value"})
        assert result["status"] == "completed"

    def test_sandbox_env_redaction(self, workroot):
        os.environ["ANTHROPIC_API_KEY"] = "sk-ant-test-key-12345"
        sandbox = Sandbox(workroot)
        result = sandbox.run("echo $ANTHROPIC_API_KEY")
        assert "sk-ant-test-key-12345" not in result.get("stdout", "")

    def test_sandbox_blocks_unbalanced_quotes(self, workroot):
        sandbox = Sandbox(workroot)
        result = sandbox.run("echo 'unbalanced")
        assert result["status"] == "error"

    def test_sandbox_timeout(self, workroot):
        sandbox = Sandbox(workroot)
        result = sandbox.run("sleep 10", timeout_seconds=0.5)
        assert result["status"] == "timeout"


# =============================================================================
# Symlink escape comprehensive
# =============================================================================

class TestSymlinkEscapes:
    def test_block_symlink_to_etc(self, gov, workroot):
        target = workroot / "evil_link"
        if not target.exists():
            target.symlink_to("/etc")
        assert gov.check_path_write(str(target / "passwd"))["decision"] == "block"

    def test_block_symlink_to_home_ssh(self, gov, workroot):
        target = workroot / "home_link"
        home = Path.home()
        if not target.exists():
            target.symlink_to(home)
        result = gov.check_path_write(str(target / ".ssh" / "authorized_keys"))
        assert result["decision"] == "block"

    def test_block_double_symlink(self, gov, workroot):
        mid = workroot / "mid_link"
        target = workroot / "double_link"
        if not mid.exists():
            mid.symlink_to("/")
        if not target.exists():
            target.symlink_to(mid)
        assert gov.check_path_write(str(target / "etc" / "passwd"))["decision"] == "block"

    def test_block_proc_cwd_escape(self, gov, workroot):
        import galaxy_merge
        pkg_dir = Path(galaxy_merge.__file__).resolve().parent.parent
        result = gov.check_path_write(str(workroot / ".." / ".." / ".." / pkg_dir.name / "galaxy_merge" / "safety" / "governor.py"))
        assert result["decision"] == "block"


# =============================================================================
# Path traversal edge cases
# =============================================================================

class TestPathTraversal:
    def test_block_absolute_etc_outside_workroot(self, gov, workroot):
        assert gov.check_path_write(str(workroot / ".." / ".." / "etc" / "passwd"))["decision"] == "block"

    def test_block_deeply_nested_traversal(self, gov, workroot):
        deep = workroot / "a" / "b" / "c" / ".." / ".." / ".." / ".." / ".." / "etc" / "passwd"
        assert gov.check_path_write(str(deep))["decision"] == "block"

    def test_block_traversal_with_symlink_component(self, gov, workroot):
        import galaxy_merge
        pkg_dir = Path(galaxy_merge.__file__).resolve().parent.parent
        deep = workroot / ".." / pkg_dir.name / "galaxy_merge" / "safety" / "governor.py"
        assert gov.check_path_write(str(deep))["decision"] == "block"


# =============================================================================
# Readonly mode comprehensive
# =============================================================================

class TestReadOnlyModeComprehensive:
    def test_readonly_blocks_git_commit(self, workroot, gm_dir, audit):
        import galaxy_merge
        pkg_dir = Path(galaxy_merge.__file__).resolve().parent.parent
        ro_gov = SafetyGovernor(pkg_dir, pkg_dir / ".gm", audit)
        if ro_gov.is_readonly_mode:
            result = ro_gov.check_command("git commit -m test")
            assert result["decision"] == "block"

    def test_readonly_blocks_git_tag(self, workroot, gm_dir, audit):
        import galaxy_merge
        pkg_dir = Path(galaxy_merge.__file__).resolve().parent.parent
        ro_gov = SafetyGovernor(pkg_dir, pkg_dir / ".gm", audit)
        if ro_gov.is_readonly_mode:
            result = ro_gov.check_command("git tag v1.0")
            assert result["decision"] == "block"

    def test_readonly_blocks_mkdir(self, workroot, gm_dir, audit):
        import galaxy_merge
        pkg_dir = Path(galaxy_merge.__file__).resolve().parent.parent
        ro_gov = SafetyGovernor(pkg_dir, pkg_dir / ".gm", audit)
        if ro_gov.is_readonly_mode:
            result = ro_gov.check_command("mkdir newdir")
            assert result["decision"] == "block"

    def test_readonly_allows_ls(self, workroot, gm_dir, audit):
        import galaxy_merge
        pkg_dir = Path(galaxy_merge.__file__).resolve().parent.parent
        ro_gov = SafetyGovernor(pkg_dir, pkg_dir / ".gm", audit)
        if ro_gov.is_readonly_mode:
            result = ro_gov.check_command("ls -la")
            assert result["decision"] == "allow"

    def test_readonly_blocks_git_status(self, workroot, gm_dir, audit):
        import galaxy_merge
        pkg_dir = Path(galaxy_merge.__file__).resolve().parent.parent
        ro_gov = SafetyGovernor(pkg_dir, pkg_dir / ".gm", audit)
        if ro_gov.is_readonly_mode:
            result = ro_gov.check_command("git status")
            assert result["decision"] == "block"

    def test_readonly_blocks_git_diff(self, workroot, gm_dir, audit):
        import galaxy_merge
        pkg_dir = Path(galaxy_merge.__file__).resolve().parent.parent
        ro_gov = SafetyGovernor(pkg_dir, pkg_dir / ".gm", audit)
        if ro_gov.is_readonly_mode:
            result = ro_gov.check_command("git diff")
            assert result["decision"] == "block"


# =============================================================================
# WorkRoot boundary enforcement
# =============================================================================

class TestWorkRootBoundary:
    def test_block_write_tmp(self, gov):
        assert gov.check_path_write("/tmp/outside.txt")["decision"] == "block"

    def test_block_write_mnt(self, gov):
        assert gov.check_path_write("/mnt/usb/file.txt")["decision"] == "block"

    def test_block_write_media(self, gov):
        assert gov.check_path_write("/media/usb/file.txt")["decision"] == "block"

    def test_block_write_proc(self, gov):
        assert gov.check_path_write("/proc/self/mem")["decision"] == "block"

    def test_block_write_sys(self, gov):
        assert gov.check_path_write("/sys/kernel/uevent_helper")["decision"] == "block"

    def test_block_write_dev(self, gov):
        assert gov.check_path_write("/dev/sda")["decision"] == "block"

    def test_allow_write_inside_workroot(self, gov, workroot):
        assert gov.check_path_write(str(workroot / "src" / "main.py"))["decision"] == "allow"

    def test_allow_write_gm_dir(self, gov, gm_dir):
        assert gov.check_path_write(str(gm_dir / "notes" / "user.md"))["decision"] == "allow"
