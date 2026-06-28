import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from galaxy_merge.core.locks import atomic_write

logger = logging.getLogger("galaxy_merge.config")

APP_CONFIG_DIR = Path.home() / ".config" / "galaxy-merge"
APP_DATA_DIR = Path.home() / ".local" / "share" / "galaxy-merge"
OPENCODE_CONFIG_PATH = Path.home() / ".config" / "opencode" / "opencode.jsonc"


class AppConfig(BaseModel):
    schema_version: int = 1
    install_dir: str = ""
    default_port: int = 0
    no_browser: bool = False


def load_app_config() -> AppConfig:
    path = APP_CONFIG_DIR / "config.json"
    if path.exists():
        data = json.loads(path.read_text())
        return AppConfig(**data)
    return AppConfig()


def save_app_config(config: AppConfig) -> None:
    APP_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    path = APP_CONFIG_DIR / "config.json"
    atomic_write(path, config.model_dump_json(indent=2))


def load_json(path: Path) -> dict[str, Any]:
    if path.exists():
        return json.loads(path.read_text())
    return {}


def save_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, json.dumps(data, indent=2, default=str))


def compute_config_hash(config_dir: Path) -> str:
    parts = []
    for name in (
        "providers.json",
        "models.json",
        "fusion.json",
        "routing.json",
        "safety.json",
    ):
        p = config_dir / name
        if p.exists():
            parts.append(p.read_text())
    raw = "".join(parts)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


OPENCODE_TIER_MAP = {
    "input": "low",
    "output": "low",
}

GM_COST_TIER_MAP: dict[str, str] = {}
GM_LATENCY_TIER_MAP: dict[str, str] = {}
GM_ROLE_MAP: dict[str, list[str]] = {}


def import_opencode_providers(gm_config_dir: Path) -> bool:
    """Import OpenCode provider/model config into Galaxy Merge format.
    Returns True if new providers were written.
    """
    if not OPENCODE_CONFIG_PATH.exists():
        return False

    try:
        raw = OPENCODE_CONFIG_PATH.read_text()
        oc_config = json.loads(raw)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(
            "Failed to parse OpenCode config at %s: %s", OPENCODE_CONFIG_PATH, e
        )
        return False

    oc_providers = oc_config.get("provider", {})
    if not oc_providers:
        return False

    gm_providers_path = gm_config_dir / "providers.json"
    gm_models_path = gm_config_dir / "models.json"

    existing_providers: dict[str, Any] = load_json(gm_providers_path)
    existing_models: dict[str, Any] = load_json(gm_models_path)

    changed = False

    for oc_name, oc_cfg in oc_providers.items():
        gm_name = oc_name.replace("-", "_")
        if gm_name in (
            existing_providers.get("providers", {})
            if existing_providers.get("providers")
            else {}
        ):
            continue

        options = oc_cfg.get("options", {})
        base_url = options.get("baseURL", "").rstrip("/")
        if not base_url:
            continue

        auth_env_var = ""
        api_key_setting = options.get("apiKey", "")
        if api_key_setting.startswith("{env:"):
            auth_env_var = api_key_setting[5:-1]

        provider_entry = {
            "enabled": True,
            "type": "openai_compatible",
            "base_url": base_url,
            "auth": {"type": "env", "env_var": auth_env_var}
            if auth_env_var
            else {"type": "none"},
            "timeout_seconds": 120,
        }

        if "providers" not in existing_providers:
            existing_providers["providers"] = {}
        existing_providers["providers"][gm_name] = provider_entry
        changed = True

        oc_models = oc_cfg.get("models", {})
        for oc_model_name, oc_model_cfg in oc_models.items():
            gm_model_id = oc_model_name.replace(":", "-").replace("/", "-")
            model_key = f"{gm_name}:{gm_model_id}"

            if model_key in (
                existing_models.get("models", {})
                if existing_models.get("models")
                else {}
            ):
                continue

            limits = oc_model_cfg.get("limit", {})
            context_window = limits.get("context", 128000)
            output_limit = limits.get("output", 32768)

            role_qualities: list[str] = []
            if oc_model_cfg.get("reasoning"):
                role_qualities.extend(["reasoning", "planning", "review"])
            if oc_model_cfg.get("tool_call"):
                role_qualities.append("tool_calling")
            strengths = role_qualities if role_qualities else ["implementation"]

            gm_roles: list[str] = []
            if any(s in strengths for s in ("planning", "reasoning")):
                gm_roles.append("planner")
            if "tool_calling" in strengths or "implementation" in strengths:
                gm_roles.append("implementer")
            if "review" in strengths or "reasoning" in strengths:
                gm_roles.append("reviewer")
            if any(s in strengths for s in ("reasoning", "planning")):
                gm_roles.append("skeptic")
            if "tool_calling" in strengths or "implementation" in strengths:
                gm_roles.append("synthesizer")
            gm_roles.append("scout")
            gm_roles.append("cheap_verifier")

            cost_tier = "low"
            latency_tier = "fast"
            context_window_val = limits.get("context", 0)
            if context_window_val and context_window_val >= 1000000:
                latency_tier = "fast"
            if oc_model_name.startswith(
                ("deepseek-reasoner", "nemotron-3-ultra", "nemotron-3-super")
            ):
                cost_tier = "medium" if "deepseek" in oc_model_name else "high"
                latency_tier = "slow" if "ultra" in oc_model_name else "medium"

            model_entry = {
                "provider": gm_name,
                "model": oc_model_name,
                "enabled": True,
                "context_window": context_window,
                "output_limit": output_limit,
                "strengths": strengths,
                "cost_tier": cost_tier,
                "latency_tier": latency_tier,
                "roles": gm_roles,
            }

            if "models" not in existing_models:
                existing_models["models"] = {}
            existing_models["models"][model_key] = model_entry
            changed = True

    if changed:
        existing_providers.setdefault("schema_version", 1)
        existing_models.setdefault("schema_version", 1)
        save_json(gm_providers_path, existing_providers)
        save_json(gm_models_path, existing_models)
        logger.info(
            "Imported %d OpenCode providers into Galaxy Merge config",
            len(existing_providers.get("providers", {})),
        )

    return changed
