import pytest

from galaxy_merge.locations.classifier import LocationClassifier
from galaxy_merge.locations.deployment_policy import DeploymentPolicy
from galaxy_merge.locations.registry import LocationRegistry

pytestmark = [pytest.mark.unit]


class TestLocationClassifier:
    def test_classify_workroot(self, tmp_path):
        classifier = LocationClassifier(tmp_path, tmp_path / ".gm")
        result = classifier.classify(str(tmp_path / "src" / "main.py"))
        assert result["classification"] == "local_workroot"

    def test_classify_gm_state(self, tmp_path):
        gm_dir = tmp_path / ".gm"
        gm_dir.mkdir()
        classifier = LocationClassifier(tmp_path, gm_dir)
        result = classifier.classify(str(gm_dir / "project.json"))
        assert result["classification"] == "local_gm_project_state"

    def test_classify_system_path(self, tmp_path):
        classifier = LocationClassifier(tmp_path, tmp_path / ".gm")
        result = classifier.classify("/etc/passwd")
        assert result["classification"] == "local_system"

    def test_classify_remote_command(self, tmp_path):
        classifier = LocationClassifier(tmp_path, tmp_path / ".gm")
        result = classifier.classify("git push origin main", "command")
        assert result["is_remote"] is True
        assert result["classification"] == "git_remote"

    def test_classify_ssh_command(self, tmp_path):
        classifier = LocationClassifier(tmp_path, tmp_path / ".gm")
        result = classifier.classify("ssh user@host", "command")
        assert result["is_remote"] is True

    def test_classify_local_command(self, tmp_path):
        classifier = LocationClassifier(tmp_path, tmp_path / ".gm")
        result = classifier.classify("ls -la", "command")
        assert result["is_remote"] is False

    def test_install_dir_classification(self, tmp_path):
        classifier = LocationClassifier(
            tmp_path / "project", tmp_path / "project" / ".gm", tmp_path / "project"
        )
        classifier.install_dir = tmp_path / "project"
        result = classifier.classify(
            str(tmp_path / "project" / "galaxy_merge" / "__init__.py")
        )
        assert result["classification"] == "galaxy_merge_app_codebase"


class TestLocationRegistry:
    def test_init_and_to_dict(self, tmp_path):
        gm = tmp_path / ".gm"
        gm.mkdir(parents=True)
        registry = LocationRegistry(gm)
        registry.init_from_project(tmp_path, gm)
        d = registry.to_dict()
        assert d["workroot"] == str(tmp_path)

    def test_register_remote(self, tmp_path):
        gm = tmp_path / ".gm"
        gm.mkdir(parents=True)
        registry = LocationRegistry(gm)
        registry.register_remote(
            "prod", "ftp_remote", "example.com", "/www", "production_target"
        )
        d = registry.to_dict()
        assert len(d["remote_targets"]) == 1
        assert d["remote_targets"][0]["id"] == "prod"
        assert d["remote_targets"][0]["write_policy"] == "blocked_by_default"


class TestDeploymentPolicy:
    def test_block_remote_by_default(self, tmp_path):
        gm = tmp_path / ".gm"
        gm.mkdir(parents=True)
        policy = DeploymentPolicy(gm)
        result = policy.check("production_target", "ssh deploy")
        assert result["decision"] == "block"

    def test_allow_local(self, tmp_path):
        gm = tmp_path / ".gm"
        gm.mkdir(parents=True)
        policy = DeploymentPolicy(gm)
        result = policy.check("local_workroot", "ls -la")
        assert result["decision"] == "allow"

    def test_custom_rule(self, tmp_path):
        gm = tmp_path / ".gm"
        gm.mkdir(parents=True)
        policy = DeploymentPolicy(gm)
        policy.add_rule("allow git push", "git_remote", ["git push"], "allow")
        result = policy.check("git_remote", "git push origin main")
        assert result["decision"] == "allow"
