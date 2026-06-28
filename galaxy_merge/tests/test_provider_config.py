"""Unit tests for core config loading and validation."""

import json
import pytest
from pathlib import Path
from galaxy_merge.core.config import load_json, save_json, load_app_config, save_app_config, AppConfig


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
