"""Secret-safe import of OpenCode provider metadata."""

import json
import logging
import os
from pathlib import Path
from typing import Final

from galaxy_merge.core.locks import atomic_write

logger = logging.getLogger("galaxy_merge.config")

OPENCODE_CONFIG_PATH: Final = Path.home() / ".config" / "opencode" / "opencode.jsonc"
OPENCODE_EXPORT_ENV_VAR: Final = "GALAXY_MERGE_OPENCODE_EXPORT"

DEFAULT_PROVIDER_ENV_VARS: Final[dict[str, str]] = {
    "deepseek": "DEEPSEEK_API_KEY",
    "kimi": "KIMI_API_KEY",
    "minimax": "MINIMAX_API_KEY",
    "nvidia-nim": "NVIDIA_API_KEY",
    "ollama-cloud": "OLLAMA_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "stepfun-ai": "STEPFUN_API_KEY",
    "streamlake": "STREAMLAKE_API_KEY",
}


def import_opencode_providers(gm_config_dir: Path) -> bool:
    """Import available OpenCode metadata into ignored Galaxy Merge configs."""
    for export_path in _candidate_export_paths():
        if import_opencode_provider_export(gm_config_dir, export_path):
            return True

    if not OPENCODE_CONFIG_PATH.exists():
        return False

    data = _load_json_file(OPENCODE_CONFIG_PATH)
    providers = _dict_value(data, "provider")
    if not providers:
        return False

    return _write_provider_config(gm_config_dir, providers)


def import_opencode_provider_export(gm_config_dir: Path, export_path: Path) -> bool:
    """Import a provider-config export without persisting literal credentials."""
    data = _load_json_file(export_path)
    providers = _dict_value(data, "providers")
    if not providers:
        return False
    return _write_provider_config(gm_config_dir, providers)


def _candidate_export_paths() -> list[Path]:
    explicit = os.environ.get(OPENCODE_EXPORT_ENV_VAR, "").strip()
    return [Path(explicit).expanduser()] if explicit else []


def _load_json_file(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to parse OpenCode provider metadata at %s: %s", path, exc)
        return {}


def _write_provider_config(
    gm_config_dir: Path, opencode_providers: dict[str, object]
) -> bool:
    gm_providers_path = gm_config_dir / "providers.json"
    gm_models_path = gm_config_dir / "models.json"
    existing_providers = _load_json_file(gm_providers_path)
    existing_models = _load_json_file(gm_models_path)
    providers = _ensure_dict(existing_providers, "providers")
    models = _ensure_dict(existing_models, "models")

    changed = False
    for provider_id, provider_value in opencode_providers.items():
        provider_config = _object_value(provider_value)
        provider_entry = _build_provider_entry(provider_id, provider_config)
        if provider_entry is None:
            continue

        if provider_id not in providers:
            providers[provider_id] = provider_entry
            changed = True

        for model_id, model_entry in _build_model_entries(provider_id, provider_config):
            model_key = f"{provider_id}:{model_id}"
            if model_key in models:
                continue
            models[model_key] = model_entry
            changed = True

    if not changed:
        return False

    existing_providers.setdefault("schema_version", 1)
    existing_models.setdefault("schema_version", 1)
    _save_json(gm_providers_path, existing_providers)
    _save_json(gm_models_path, existing_models)
    logger.info("Imported OpenCode provider metadata into Galaxy Merge config")
    return True


def _build_provider_entry(
    provider_id: str, provider_config: dict[str, object]
) -> dict[str, object] | None:
    options = _dict_value(provider_config, "options")
    base_url = _string_value(options, "baseURL").rstrip("/")
    if not base_url:
        base_url = _string_value(provider_config, "baseURL").rstrip("/")
    if not base_url:
        return None

    auth_env_var = _extract_env_var(_string_value(options, "apiKey"))
    if not auth_env_var:
        auth_env_var = DEFAULT_PROVIDER_ENV_VARS.get(provider_id, "")

    entry: dict[str, object] = {
        "enabled": True,
        "type": "openai_compatible",
        "base_url": base_url,
        "auth": {"type": "env", "env_var": auth_env_var}
        if auth_env_var
        else {"type": "none"},
        "timeout_seconds": 120,
    }

    fallback_urls = _string_list_value(options, "fallbackBaseURLs")
    if fallback_urls:
        entry["fallback_base_urls"] = fallback_urls
    return entry


def _build_model_entries(
    provider_id: str, provider_config: dict[str, object]
) -> list[tuple[str, dict[str, object]]]:
    model_configs = _dict_value(provider_config, "models")
    entries: list[tuple[str, dict[str, object]]] = []
    for model_id, model_value in model_configs.items():
        model_config = _object_value(model_value)
        limit = _dict_value(model_config, "limit")
        context_window = _int_value(limit, "context", 128000)
        output_limit = _int_value(limit, "output", 32768)
        reasoning = _bool_value(model_config, "reasoning")
        tool_calling = _bool_value(model_config, "tool_call")
        strengths = _strengths_for_model(model_id, reasoning, tool_calling)
        entries.append(
            (
                model_id,
                {
                    "provider": provider_id,
                    "model": model_id,
                    "enabled": True,
                    "context_window": context_window,
                    "output_limit": output_limit,
                    "strengths": strengths,
                    "cost_tier": _cost_tier_for_model(provider_id, model_id),
                    "latency_tier": _latency_tier_for_model(model_id),
                    "roles": _roles_for_strengths(strengths),
                },
            )
        )
    return entries


def _strengths_for_model(
    model_id: str, reasoning: bool, tool_calling: bool
) -> list[str]:
    strengths: list[str] = []
    if reasoning:
        strengths.extend(["reasoning", "planning", "review"])
    if tool_calling:
        strengths.extend(["tool_calling", "implementation", "synthesis"])
    if "flash" in model_id.lower() or "highspeed" in model_id.lower():
        strengths.append("fast_scan")
    return list(dict.fromkeys(strengths or ["implementation"]))


def _roles_for_strengths(strengths: list[str]) -> list[str]:
    roles: list[str] = []
    if "planning" in strengths or "reasoning" in strengths:
        roles.extend(["planner", "skeptic"])
    if "review" in strengths or "reasoning" in strengths:
        roles.append("reviewer")
    if "tool_calling" in strengths or "implementation" in strengths:
        roles.extend(["implementer", "synthesizer"])
    roles.extend(["scout", "cheap_verifier"])
    return list(dict.fromkeys(roles))


def _cost_tier_for_model(provider_id: str, model_id: str) -> str:
    lowered = f"{provider_id}/{model_id}".lower()
    if "ultra" in lowered or "sonnet" in lowered or "gemini" in lowered:
        return "high"
    if "reasoner" in lowered or "pro" in lowered or "m3" in lowered:
        return "medium"
    return "low"


def _latency_tier_for_model(model_id: str) -> str:
    lowered = model_id.lower()
    if "flash" in lowered or "highspeed" in lowered:
        return "fast"
    if "ultra" in lowered or "reasoner" in lowered:
        return "slow"
    return "medium"


def _extract_env_var(value: str) -> str:
    if value.startswith("{env:") and value.endswith("}"):
        return value[5:-1].strip()
    return ""


def _save_json(path: Path, data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, json.dumps(data, indent=2, default=str))


def _ensure_dict(data: dict[str, object], key: str) -> dict[str, object]:
    value = data.get(key)
    if isinstance(value, dict):
        return value
    data[key] = {}
    result = data[key]
    return result if isinstance(result, dict) else {}


def _dict_value(data: dict[str, object], key: str) -> dict[str, object]:
    value = data.get(key)
    return value if isinstance(value, dict) else {}


def _object_value(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _string_value(data: dict[str, object], key: str) -> str:
    value = data.get(key)
    return value if isinstance(value, str) else ""


def _string_list_value(data: dict[str, object], key: str) -> list[str]:
    value = data.get(key)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _int_value(data: dict[str, object], key: str, default: int) -> int:
    value = data.get(key)
    return value if isinstance(value, int) else default


def _bool_value(data: dict[str, object], key: str) -> bool:
    value = data.get(key)
    return value if isinstance(value, bool) else False
