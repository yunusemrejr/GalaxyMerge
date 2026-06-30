"""Unit tests for core config loading and validation."""

import json

import pytest

from galaxy_merge.core.config import load_json, save_json, load_app_config, AppConfig

pytestmark = [pytest.mark.unit]


class TestLoadJson:
    def test_load_json_missing_file(self, tmp_path):
        result = load_json(tmp_path / "nonexistent.json")
        assert result == {}

    def test_load_json_valid(self, tmp_path):
        data = {"key": "value", "number": 42}
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps(data))
        result = load_json(config_path)
        assert result == data


class TestSaveJson:
    def test_save_json_creates_file(self, tmp_path):
        data = {"test": "data"}
        output_path = tmp_path / "output.json"
        save_json(output_path, data)
        assert output_path.exists()
        assert json.loads(output_path.read_text()) == data

    def test_save_json_overwrites(self, tmp_path):
        output_path = tmp_path / "output.json"
        save_json(output_path, {"old": "data"})
        save_json(output_path, {"new": "data"})
        assert json.loads(output_path.read_text()) == {"new": "data"}


class TestAppConfig:
    def test_load_app_config_creates_default(self, tmp_path, monkeypatch):
        # Override the config dir to tmp_path
        from galaxy_merge.core import config as config_module

        original_dir = config_module.APP_CONFIG_DIR
        config_module.APP_CONFIG_DIR = tmp_path / ".config"
        try:
            config = load_app_config()
            assert isinstance(config, AppConfig)
            assert config.schema_version == 1
        finally:
            config_module.APP_CONFIG_DIR = original_dir

    def test_app_config_defaults(self, tmp_path, monkeypatch):
        from galaxy_merge.core import config as config_module

        original_dir = config_module.APP_CONFIG_DIR
        config_module.APP_CONFIG_DIR = tmp_path / ".config"
        try:
            config = load_app_config()
            assert config.schema_version == 1
            assert config.install_dir == ""
        finally:
            config_module.APP_CONFIG_DIR = original_dir


class TestOfflineFallback:
    """Verify the offline_mock fallback activates when no real providers are usable."""

    def _make_all_unavailable_config(self, tmp_path):
        """Create a config where ALL providers lack API keys."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        providers_json = {
            "providers": {
                "openai": {
                    "enabled": True,
                    "type": "openai_compatible",
                    "base_url": "https://api.openai.com/v1",
                    "auth": {"type": "env", "env_var": "OPENAI_API_KEY"},
                    "timeout_seconds": 90,
                },
                "ollama_local": {
                    "enabled": True,
                    "type": "ollama",
                    "base_url": "http://127.0.0.1:11434",
                    "auth": {"type": "none"},
                    "timeout_seconds": 180,
                },
            }
        }
        (config_dir / "providers.json").write_text(json.dumps(providers_json))

        models_json = {
            "models": {
                "openai:gpt-4": {
                    "provider": "openai",
                    "model": "gpt-4",
                    "enabled": True,
                    "context_window": 128000,
                    "strengths": ["planning", "implementation"],
                    "roles": [
                        "planner",
                        "scout",
                        "implementer",
                        "reviewer",
                        "skeptic",
                        "cheap_verifier",
                        "synthesizer",
                    ],
                },
            }
        }
        (config_dir / "models.json").write_text(json.dumps(models_json))
        return config_dir

    def test_offline_mock_injected_when_no_keys(self, tmp_path, monkeypatch):
        """When no API keys are set, offline_mock must be injected as fallback."""
        # Ensure no API keys are in the environment
        for key in ["OPENAI_API_KEY", "DEEPSEEK_API_KEY", "ANTHROPIC_API_KEY"]:
            monkeypatch.delenv(key, raising=False)

        from galaxy_merge.providers.registry import ProviderRegistry

        config_dir = self._make_all_unavailable_config(tmp_path)
        reg = ProviderRegistry(config_dir)
        reg.load()

        # The offline_mock should be present
        assert "offline_mock" in reg._providers
        offline = reg.get("offline_mock")
        assert offline is not None
        assert offline.available is True

    def test_all_roles_covered_without_keys(self, tmp_path, monkeypatch):
        """All 7 council roles must have a model even with zero API keys."""
        for key in ["OPENAI_API_KEY", "DEEPSEEK_API_KEY", "ANTHROPIC_API_KEY"]:
            monkeypatch.delenv(key, raising=False)

        from galaxy_merge.providers.registry import ProviderRegistry

        config_dir = self._make_all_unavailable_config(tmp_path)
        reg = ProviderRegistry(config_dir)
        reg.load()

        roles = [
            "planner",
            "scout",
            "implementer",
            "reviewer",
            "skeptic",
            "cheap_verifier",
            "synthesizer",
        ]
        for role in roles:
            result = reg.select_best_model(role)
            assert result is not None, f"Role '{role}' has no eligible model"
            provider_id, model, _ = result
            assert provider_id == "offline_mock", (
                f"Role '{role}' should fall back to offline_mock, got '{provider_id}'"
            )

    def test_offline_mock_not_used_when_real_available(self, tmp_path, monkeypatch):
        """When a real provider IS available, offline_mock should NOT be selected."""
        from galaxy_merge.providers.registry import ProviderRegistry

        config_dir = tmp_path / "config"
        config_dir.mkdir()
        # Single provider WITH key
        providers_json = {
            "providers": {
                "openai": {
                    "enabled": True,
                    "type": "openai_compatible",
                    "base_url": "https://api.openai.com/v1",
                    "auth": {"type": "env", "env_var": "OPENAI_API_KEY"},
                    "timeout_seconds": 90,
                },
            }
        }
        (config_dir / "providers.json").write_text(json.dumps(providers_json))
        models_json = {
            "models": {
                "openai:gpt-4": {
                    "provider": "openai",
                    "model": "gpt-4",
                    "enabled": True,
                    "context_window": 128000,
                    "strengths": ["planning"],
                    "roles": ["planner", "scout", "implementer", "reviewer", "skeptic", "cheap_verifier", "synthesizer"],
                },
            }
        }
        (config_dir / "models.json").write_text(json.dumps(models_json))

        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-fake-key")
        reg = ProviderRegistry(config_dir)
        reg.load()

        # Real provider should be selected, not offline_mock
        for role in ["planner", "scout", "implementer"]:
            result = reg.select_best_model(role)
            assert result is not None
            provider_id, _, _ = result
            assert provider_id == "openai", (
                f"Role '{role}' should use real provider, got '{provider_id}'"
            )
