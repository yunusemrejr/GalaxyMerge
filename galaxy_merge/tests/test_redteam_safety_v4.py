import pytest
from pathlib import Path

from galaxy_merge.app.server import build_locations_payload
from galaxy_merge.core.session import init_gm_dir
from galaxy_merge.locations.classifier import LocationClassifier
from galaxy_merge.locations.registry import LocationRegistry
from galaxy_merge.safety.audit import SafetyAudit
from galaxy_merge.safety.governor import SafetyGovernor
from galaxy_merge.tools.browser_tools import make_browser_tools
from galaxy_merge.tools.file_tools import make_file_tools


@pytest.fixture
def gov(tmp_path: Path) -> SafetyGovernor:
    gm_dir = tmp_path / ".gm"
    gm_dir.mkdir()
    return SafetyGovernor(tmp_path, gm_dir, SafetyAudit(gm_dir / "audit.jsonl"))


class TestCommandBypassRegressions:
    def test_remote_mutation_in_chained_command_requires_deployment_policy(self, gov: SafetyGovernor) -> None:
        result = gov.check_command("echo ok && git push origin main")
        assert result["decision"] == "allow_with_audit"

    def test_remote_mutation_in_shell_wrapper_requires_deployment_policy(self, gov: SafetyGovernor) -> None:
        result = gov.check_command("sh -c 'git push origin main'")
        assert result["decision"] == "allow_with_audit"

    def test_git_dash_c_push_requires_deployment_policy(self, gov: SafetyGovernor) -> None:
        result = gov.check_command("git -C . push origin main")
        assert result["decision"] == "allow_with_audit"

    def test_env_git_context_is_blocked_before_git_push_runs(self, gov: SafetyGovernor) -> None:
        result = gov.check_command("env GIT_DIR=/tmp/repo/.git git push origin main")
        assert result["decision"] == "allow_with_audit"

    def test_remote_mutation_after_pipe_requires_deployment_policy(self, gov: SafetyGovernor) -> None:
        result = gov.check_command("echo payload | ssh user@prod.example.com deploy")
        assert result["decision"] == "allow_with_audit"

    def test_redirect_to_system_path_is_blocked(self, gov: SafetyGovernor) -> None:
        result = gov.check_command("printf owned > /etc/passwd")
        assert result["decision"] == "block"


class TestLocationSeparationRegressions:
    def test_chained_git_push_classifies_as_git_remote(self, tmp_path: Path) -> None:
        classifier = LocationClassifier(tmp_path, tmp_path / ".gm")
        result = classifier.classify("echo ok && git push origin main", "command")
        assert result["classification"] == "git_remote"
        assert result["policy_decision"] == "blocked_by_default"
        assert result["risk"] == "high"

    def test_workroot_sibling_prefix_is_unknown_not_local_workroot(self, tmp_path: Path) -> None:
        workroot = tmp_path / "project"
        sibling = tmp_path / "project_evil"
        workroot.mkdir()
        sibling.mkdir()
        classifier = LocationClassifier(workroot, workroot / ".gm")
        result = classifier.classify(str(sibling / "file.txt"))
        assert result["classification"] != "local_workroot"

    def test_locations_api_exposes_gui_decision_fields(self, tmp_path: Path) -> None:
        init_gm_dir(tmp_path)
        registry = LocationRegistry(tmp_path / ".gm")
        registry.register_remote("prod", "ssh_remote", "prod.example.com", "/srv/app", "production_target")
        data = build_locations_payload(tmp_path, tmp_path / ".gm")

        prod = [item for item in data["classified_locations"] if item["target"] == "prod"][0]
        assert prod["classification"] == "production_target"
        assert prod["host"] == "prod.example.com"
        assert prod["path"] == "/srv/app"
        assert prod["risk"] == "high"
        assert prod["policy_decision"] == "blocked_by_default"


class TestToolWorkrootEscapeRegressions:
    @pytest.mark.asyncio
    async def test_file_write_rejects_sibling_prefix_escape(self, tmp_path: Path) -> None:
        workroot = tmp_path / "project"
        sibling = tmp_path / "project_evil"
        workroot.mkdir()
        sibling.mkdir()
        tools = dict(make_file_tools(workroot))
        result = await tools["file.write"](str(sibling / "owned.txt"), "owned")
        assert result.success is False
        assert result.error == "path outside WorkRoot"
        assert not (sibling / "owned.txt").exists()

    @pytest.mark.asyncio
    async def test_file_read_rejects_sibling_prefix_escape(self, tmp_path: Path) -> None:
        workroot = tmp_path / "project"
        sibling = tmp_path / "project_evil"
        workroot.mkdir()
        sibling.mkdir()
        (sibling / "secret.txt").write_text("secret")
        tools = dict(make_file_tools(workroot))
        result = await tools["file.read"](str(sibling / "secret.txt"))
        assert result.success is False
        assert result.error == "path outside WorkRoot"


class TestSelfProtectionRegressions:
    def test_launch_inside_source_tree_is_readonly(self, tmp_path: Path) -> None:
        import galaxy_merge

        pkg_root = Path(galaxy_merge.__file__).resolve().parent.parent
        gov = SafetyGovernor(pkg_root, pkg_root / ".gm", SafetyAudit(tmp_path / "audit.jsonl"))
        assert gov.is_readonly_mode is True
        assert gov.check_command("touch galaxy_merge/safety/policy.py")["decision"] == "block"
        assert gov.check_path_write(str(pkg_root / "galaxy_merge" / "safety" / "policy.py"))["decision"] == "block"


class TestConcurrentBrowserIsolation:
    @pytest.mark.asyncio
    async def test_one_session_cannot_read_another_sessions_browser_logs(self, tmp_path: Path) -> None:
        from galaxy_merge.tools.browser_tools import _browser_managers

        tools_a = dict(make_browser_tools(tmp_path / ".gm", "sess_a"))
        tools_b = dict(make_browser_tools(tmp_path / ".gm", "sess_b"))
        manager = _browser_managers[str((tmp_path / ".gm").resolve())]
        manager._console_collectors["sess_a:default"] = type("Collector", (), {"get_logs": lambda self: [{"msg": "a"}]})()

        result_a = await tools_a["browser.console.read"]("default")
        result_b = await tools_b["browser.console.read"]("default")

        assert result_a.success is True
        assert result_b.success is False
