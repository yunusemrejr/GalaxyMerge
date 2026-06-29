"""Tests for secret-safe OpenCode provider export import."""

import json

import pytest

from galaxy_merge.core.opencode_import import (
    OPENCODE_EXPORT_ENV_VAR,
    import_opencode_provider_export,
    import_opencode_providers,
)

pytestmark = [pytest.mark.unit]


def test_import_opencode_provider_export_preserves_models_without_secrets(
    tmp_path,
) -> None:
    # Given: an OpenCode provider export with exact provider/model IDs.
    export_path = tmp_path / "opencode-export.json"
    export_path.write_text(
        json.dumps(
            {
                "providers": {
                    "streamlake": {
                        "name": "StreamLake KwaiKAT",
                        "npm": "@ai-sdk/openai-compatible",
                        "options": {
                            "baseURL": "https://streamlake.example.invalid/v1",
                            "apiKey": "{env:STREAMLAKE_API_KEY}",
                            "fallbackBaseURLs": [
                                "https://streamlake-fallback.example.invalid/v1"
                            ],
                        },
                        "models": {
                            "kat-coder-pro-v2": {
                                "limit": {"context": 256000, "output": 256000},
                                "reasoning": True,
                                "tool_call": True,
                            }
                        },
                    },
                    "nvidia-nim": {
                        "name": "NVIDIA NIM",
                        "npm": "@ai-sdk/openai-compatible",
                        "options": {
                            "baseURL": "https://nim.example.invalid/v1",
                            "apiKey": "literal-credential-must-not-persist",
                        },
                        "models": {
                            "nvidia/llama-3.3-nemotron-super-49b": {
                                "limit": {"context": 131072, "output": 32768},
                                "reasoning": True,
                                "tool_call": True,
                            }
                        },
                    },
                }
            }
        )
    )

    # When: the export is imported into local Galaxy Merge config files.
    changed = import_opencode_provider_export(tmp_path / "config", export_path)

    # Then: provider metadata and exact models are available without secrets.
    assert changed is True
    providers = json.loads((tmp_path / "config" / "providers.json").read_text())
    models = json.loads((tmp_path / "config" / "models.json").read_text())
    rendered = json.dumps({"providers": providers, "models": models})

    assert "literal-credential-must-not-persist" not in rendered
    assert providers["providers"]["streamlake"]["auth"] == {
        "type": "env",
        "env_var": "STREAMLAKE_API_KEY",
    }
    assert providers["providers"]["nvidia-nim"]["auth"] == {
        "type": "env",
        "env_var": "NVIDIA_API_KEY",
    }
    assert providers["providers"]["streamlake"]["fallback_base_urls"] == [
        "https://streamlake-fallback.example.invalid/v1"
    ]
    assert models["models"]["streamlake:kat-coder-pro-v2"]["model"] == (
        "kat-coder-pro-v2"
    )
    assert models["models"][
        "nvidia-nim:nvidia/llama-3.3-nemotron-super-49b"
    ]["provider"] == "nvidia-nim"
    assert "planner" in models["models"]["streamlake:kat-coder-pro-v2"]["roles"]
    assert "implementer" in models["models"]["streamlake:kat-coder-pro-v2"]["roles"]


def test_import_opencode_provider_export_is_idempotent(tmp_path) -> None:
    # Given: a minimal export and an empty Galaxy Merge config directory.
    export_path = tmp_path / "opencode-export.json"
    export_path.write_text(
        json.dumps(
            {
                "providers": {
                    "kimi": {
                        "options": {
                            "baseURL": "https://kimi.example.invalid/v1",
                            "apiKey": "{env:KIMI_API_KEY}",
                        },
                        "models": {
                            "kimi-k2.7-code": {
                                "limit": {"context": 256000, "output": 32768},
                                "reasoning": True,
                                "tool_call": True,
                            }
                        },
                    }
                }
            }
        )
    )
    config_dir = tmp_path / "config"

    # When: the same export is imported twice.
    first_changed = import_opencode_provider_export(config_dir, export_path)
    second_changed = import_opencode_provider_export(config_dir, export_path)

    # Then: the second run leaves existing config untouched.
    assert first_changed is True
    assert second_changed is False


def test_import_opencode_providers_uses_explicit_export_env_var(
    tmp_path, monkeypatch
) -> None:
    # Given: runtime is pointed at an OpenCode provider export.
    export_path = tmp_path / "opencode-export.json"
    export_path.write_text(
        json.dumps(
            {
                "providers": {
                    "stepfun-ai": {
                        "options": {
                            "baseURL": "https://stepfun.example.invalid/v1",
                            "apiKey": "{env:STEPFUN_API_KEY}",
                        },
                        "models": {
                            "step-3.7-flash": {
                                "limit": {"context": 256000, "output": 256000},
                                "reasoning": True,
                                "tool_call": True,
                            }
                        },
                    }
                }
            }
        )
    )
    config_dir = tmp_path / "config"
    monkeypatch.setenv(OPENCODE_EXPORT_ENV_VAR, str(export_path))

    # When: the ProviderRegistry compatibility hook imports OpenCode metadata.
    changed = import_opencode_providers(config_dir)

    # Then: exact provider/model IDs are written for registry loading.
    models = json.loads((config_dir / "models.json").read_text())
    assert changed is True
    assert models["models"]["stepfun-ai:step-3.7-flash"]["model"] == (
        "step-3.7-flash"
    )
