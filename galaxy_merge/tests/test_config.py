import json
import pytest
from pathlib import Path

from galaxy_merge.core.config import load_json, save_json


class TestConfig:
    def test_load_json_missing(self, tmp_path):
        result = load_json(tmp_path / "nonexistent.json")
        assert result == {}

    def test_save_and_load_json(self, tmp_path):
        data = {"key": "value", "num": 42}
        path = tmp_path / "test.json"
        save_json(path, data)
        loaded = load_json(path)
        assert loaded["key"] == "value"
        assert loaded["num"] == 42

    def test_providers_config(self, tmp_path):
        config = {
            "providers": {
                "test": {
                    "enabled": True,
                    "type": "openai_compatible",
                    "base_url": "http://test:8000",
                    "auth": {"type": "none"},
                    "timeout_seconds": 30,
                }
            }
        }
        path = tmp_path / "providers.json"
        save_json(path, config)
        loaded = load_json(path)
        assert loaded["providers"]["test"]["base_url"] == "http://test:8000"
