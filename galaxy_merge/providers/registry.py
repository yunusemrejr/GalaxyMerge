import json
import logging
from pathlib import Path
from typing import Any

from galaxy_merge.providers.base import ProviderBase
from galaxy_merge.providers.local_ollama import OllamaProvider
from galaxy_merge.providers.mock import MockProvider, OfflineMockProvider
from galaxy_merge.providers.openai_compat import OpenAICompatibleProvider
from galaxy_merge.safety.credential_policy import redact_text

logger = logging.getLogger("galaxy_merge.providers")


class ConfigError(Exception):
    def __init__(self, message: str, path: str = ""):
        self.path = path
        super().__init__(message)


def validate_providers_config(data: dict[str, Any]) -> list[str]:
    errors = []
    providers = data.get("providers", {})
    if not isinstance(providers, dict):
        return ["'providers' must be an object"]
    for pid, cfg in providers.items():
        if not isinstance(cfg, dict):
            errors.append(f"provider '{pid}' must be an object")
            continue
        if not cfg.get("type"):
            errors.append(f"provider '{pid}' missing 'type'")
        if not cfg.get("base_url"):
            errors.append(f"provider '{pid}' missing 'base_url'")
        auth = cfg.get("auth", {})
        if not isinstance(auth, dict):
            errors.append(f"provider '{pid}'.auth must be an object")
        elif auth.get("type") == "env" and not auth.get("env_var"):
            errors.append(f"provider '{pid}' has auth type 'env' but no 'env_var'")
    return errors


def validate_models_config(data: dict[str, Any], provider_ids: set[str]) -> list[str]:
    errors = []
    models = data.get("models", {})
    if not isinstance(models, dict):
        return ["'models' must be an object"]
    for mid, cfg in models.items():
        if not isinstance(cfg, dict):
            errors.append(f"model '{mid}' must be an object")
            continue
        if cfg.get("enabled") is False:
            continue
        if not cfg.get("provider"):
            errors.append(f"model '{mid}' missing 'provider' field")
        elif cfg["provider"] not in provider_ids:
            errors.append(
                f"model '{mid}' references unknown/disabled provider '{cfg.get('provider')}'"
            )
        if not cfg.get("model"):
            errors.append(f"model '{mid}' missing 'model' field (API model name)")
        if not cfg.get("roles"):
            errors.append(f"model '{mid}' missing 'roles' array")
        if cfg.get("roles") and not isinstance(cfg["roles"], list):
            errors.append(f"model '{mid}'.roles must be an array")
    return errors


def validate_fusion_config(data: dict[str, Any]) -> list[str]:
    errors = []
    councils = data.get("councils", {})
    if not isinstance(councils, dict):
        return ["'councils' must be an object"]
    for cname, cfg in councils.items():
        if not isinstance(cfg, dict):
            errors.append(f"council '{cname}' must be an object")
            continue
        roles = cfg.get("roles", {})
        if not isinstance(roles, dict):
            errors.append(f"council '{cname}'.roles must be an object")
            continue
        for rname, rcfg in roles.items():
            if not isinstance(rcfg, dict):
                errors.append(f"council '{cname}'.roles.'{rname}' must be an object")
                continue
            if rcfg.get("required", True) and not rcfg.get("model_selector"):
                errors.append(
                    f"council '{cname}'.roles.'{rname}' required but missing 'model_selector'"
                )
    return errors


def validate_routing_config(data: dict[str, Any], council_names: set[str]) -> list[str]:
    errors = []
    rules = data.get("routing_rules", [])
    if not isinstance(rules, list):
        return ["'routing_rules' must be an array"]
    for i, rule in enumerate(rules):
        if not isinstance(rule, dict):
            errors.append(f"routing_rules[{i}] must be an object")
            continue
        match = rule.get("match", {})
        if not isinstance(match, dict):
            errors.append(f"routing_rules[{i}].match must be an object")
        if not match.get("task_type"):
            errors.append(f"routing_rules[{i}] missing match.task_type")
        council_name = rule.get("council", "")
        if council_name and council_name not in council_names:
            errors.append(
                f"routing_rules[{i}] references unknown council '{council_name}'"
            )
    fallback = data.get("fallback", {})
    fallback_council = fallback.get("council", "")
    if fallback_council and fallback_council not in council_names:
        errors.append(f"fallback council '{fallback_council}' not found in councils")
    return errors


def _score_model(
    model_config: dict[str, Any],
    role: str,
    cost_policy: str,
    prefer_strengths: list[str] | None = None,
) -> float:
    score = 0.0
    strengths = model_config.get("strengths", [])
    preferred = prefer_strengths or []
    for s in preferred:
        if s in strengths:
            score += 3.0

    cost_tier = model_config.get("cost_tier", "medium")
    if cost_policy == "cheap" and cost_tier == "local":
        score += 2.0
    elif cost_policy == "cheap" and cost_tier == "low":
        score += 1.5
    elif cost_policy == "quality" and cost_tier in ("high", "medium"):
        score += 1.0
    elif cost_policy == "balanced":
        score += 0.5

    latency_tier = model_config.get("latency_tier", "medium")
    if latency_tier == "fast":
        score += 0.5
    elif latency_tier == "slow":
        score -= 0.5

    cache_behavior = model_config.get("cache_behavior", {})
    if cache_behavior.get("supports_prefix_cache"):
        score += 1.0

    context_window = model_config.get("context_window", 0)
    if context_window >= 128000:
        score += 1.0
    elif context_window >= 32000:
        score += 0.5

    return score


def _minimum_context_window(role: str) -> int:
    role_min = {
        "planner": 16000,
        "scout": 8000,
        "implementer": 16000,
        "reviewer": 32000,
        "skeptic": 32000,
        "synthesizer": 16000,
        "cheap_verifier": 4000,
    }
    return role_min.get(role, 4000)


class ProviderRegistry:
    def __init__(self, config_dir: Path, event_log=None, session_id: str = ""):
        self.config_dir = config_dir
        self._providers: dict[str, ProviderBase] = {}
        self._models: dict[str, dict[str, Any]] = {}
        self._provider_health: dict[str, bool] = {}
        self._load_errors: list[str] = []
        self._event_log = event_log
        self._session_id = session_id

    def load(self) -> None:
        # ── Lazy imports: avoid loading httpx at module level ──────

        self._providers.clear()
        self._models.clear()
        self._load_errors.clear()

        providers_path = self.config_dir / "providers.json"
        models_path = self.config_dir / "models.json"

        first_read: dict[str, Any] = {}
        if providers_path.exists():
            try:
                first_read = json.loads(providers_path.read_text())
            except json.JSONDecodeError:
                pass

        existing_providers = first_read.get("providers", {}) or {}
        has_mock = any(v.get("type") == "mock" for v in existing_providers.values())

        if not existing_providers and not has_mock:
            from galaxy_merge.core.config import import_opencode_providers

            import_opencode_providers(self.config_dir)

        from galaxy_merge.core.config import compute_config_hash

        config_hash = compute_config_hash(self.config_dir)
        from galaxy_merge.cache.keys import set_config_hash

        set_config_hash(config_hash)

        providers_config: dict[str, Any] = {}
        if providers_path.exists():
            try:
                providers_config = json.loads(providers_path.read_text())
                self._load_errors.extend(
                    f"providers.json: {e}"
                    for e in validate_providers_config(providers_config)
                )
            except json.JSONDecodeError as e:
                self._load_errors.append(f"providers.json: invalid JSON — {e}")
        else:
            self._load_errors.append("providers.json not found")

        provider_ids = set()
        available_count = 0
        unavailable_count = 0
        for provider_id, config in providers_config.get("providers", {}).items():
            if not config.get("enabled", True):
                continue
            provider = self._create_provider(provider_id, config)
            if provider:
                self._providers[provider_id] = provider
                provider_ids.add(provider_id)
                if provider.available:
                    available_count += 1
                else:
                    unavailable_count += 1
                    logger.warning(
                        "Provider '%s' unavailable: %s",
                        provider_id,
                        provider.warning or "no reason given",
                    )
            else:
                self._load_errors.append(
                    f"provider '{provider_id}': unknown type '{config.get('type')}'"
                )

        logger.info(
            "Loaded %d providers (%d available, %d unavailable)",
            len(self._providers),
            available_count,
            unavailable_count,
        )

        if models_path.exists():
            try:
                models_data = json.loads(models_path.read_text())
                self._load_errors.extend(
                    f"models.json: {e}"
                    for e in validate_models_config(models_data, provider_ids)
                )
                for mid, cfg in models_data.get("models", {}).items():
                    if cfg.get("enabled") is False:
                        continue
                    if cfg.get("provider") in self._providers:
                        self._models[mid] = cfg
                    else:
                        logger.debug(
                            "Model '%s' skipped: provider '%s' not loaded",
                            mid,
                            cfg.get("provider"),
                        )
            except json.JSONDecodeError as e:
                self._load_errors.append(f"models.json: invalid JSON — {e}")
        else:
            self._load_errors.append("models.json not found")

        logger.info("Loaded %d models", len(self._models))

        self._inject_offline_fallback()

    def _inject_offline_fallback(self) -> None:
        """Ensure offline_mock is always available as a lowest-priority fallback.

        The offline mock provides deterministic, schema-conformant responses for
        every council role without any network calls. It is injected unconditionally
        so that the council can always produce a usable plan even when:
          - All configured providers lack API keys
          - All configured providers are down or unreachable
          - Only ollama-type providers exist but the server isn't running

        Real providers are always preferred because _score_model() gives the
        offline mock a low score (no strengths, small context window), so it only
        gets selected when no real provider is healthy.
        """
        if "offline_mock" in self._providers:
            return

        offline = OfflineMockProvider()
        self._providers["offline_mock"] = offline
        self._models["offline_mock:offline-mock"] = {
            "provider": "offline_mock",
            "model": "offline-mock",
            "enabled": True,
            "context_window": 32000,
            "output_limit": 4096,
            "strengths": ["offline_fallback"],
            "cost_tier": "local",
            "latency_tier": "fast",
            "roles": [
                "planner",
                "scout",
                "implementer",
                "reviewer",
                "cheap_verifier",
                "skeptic",
                "synthesizer",
            ],
        }
        logger.info(
            "Injected offline_mock fallback provider (always available as last resort)"
        )

    def _create_provider(
        self, provider_id: str, config: dict[str, Any]
    ) -> ProviderBase | None:
        ptype = config.get("type", "")
        if ptype == "openai_compatible":
            return OpenAICompatibleProvider(provider_id, config)
        elif ptype == "ollama":
            return OllamaProvider(provider_id, config)
        elif ptype == "mock":
            return MockProvider(provider_id, config)
        return None

    def get(self, provider_id: str) -> ProviderBase | None:
        return self._providers.get(provider_id)

    def get_model(self, model_key: str) -> dict[str, Any] | None:
        return self._models.get(model_key)

    def available_providers(self) -> list[dict[str, Any]]:
        return [p.to_dict() for p in self._providers.values()]

    def load_errors(self) -> list[str]:
        return list(self._load_errors)

    def select_best_model(
        self,
        role: str,
        cost_policy: str = "balanced",
        prefer_strengths: list[str] | None = None,
    ) -> tuple[str, str, dict[str, Any]] | None:
        candidates = self.get_models_for_role(role)
        if not candidates:
            logger.warning(
                "No models configured for role '%s' — "
                "check models.json has entries with roles=['%s']",
                role,
                role,
            )
            return None

        min_window = _minimum_context_window(role)
        scored = []
        offline_candidates = []  # offline_mock goes here as last resort
        skipped: list[tuple[str, str]] = []
        for provider_id, model, model_config in candidates:
            provider = self._providers.get(provider_id)
            if not provider:
                skipped.append((model, f"provider '{provider_id}' not registered"))
                continue
            if not provider.available:
                skipped.append(
                    (model, f"provider '{provider_id}' not available: {provider.warning}")
                )
                continue
            cw = model_config.get("context_window", 0)
            if cw and cw < min_window:
                skipped.append(
                    (model, f"context_window {cw} < minimum {min_window}")
                )
                continue
            score = _score_model(model_config, role, cost_policy, prefer_strengths)
            # Separate offline_mock from real providers so it's only
            # selected when nothing else is available.
            if provider_id == "offline_mock":
                offline_candidates.append((score, provider_id, model, model_config))
            else:
                scored.append((score, provider_id, model, model_config))

        if scored:
            scored.sort(key=lambda x: x[0], reverse=True)
            _, provider_id, model, model_config = scored[0]
            logger.debug(
                "Selected model '%s' (provider=%s) for role '%s' (score=%.1f, %d candidates)",
                model,
                provider_id,
                role,
                scored[0][0],
                len(scored),
            )
            return (provider_id, model, model_config)

        # No real provider available — fall back to offline_mock if present
        if offline_candidates:
            offline_candidates.sort(key=lambda x: x[0], reverse=True)
            _, provider_id, model, model_config = offline_candidates[0]
            logger.warning(
                "Role '%s' falling back to offline_mock — no real provider available",
                role,
            )
            return (provider_id, model, model_config)

        logger.warning(
            "No eligible model for role '%s' — %d candidate(s) skipped: %s",
            role,
            len(skipped),
            skipped,
        )
        return None

    def get_models_for_role(self, role: str) -> list[tuple[str, str, dict[str, Any]]]:
        candidates = []
        for model_key, model_config in self._models.items():
            roles = model_config.get("roles", [])
            if role in roles:
                provider_id = model_config.get("provider", "")
                if provider_id in self._providers:
                    candidates.append(
                        (provider_id, model_config["model"], model_config)
                    )
        return candidates

    def mark_unhealthy(
        self,
        provider_id: str,
        model: str = "",
        role: str = "",
        error: str = "",
        attempt: int = 0,
        duration_ms: int = 0,
        retry_count: int = 0,
        fallback_decision: str = "",
    ) -> None:
        provider = self._providers.get(provider_id)
        if provider:
            redacted_error = redact_text(error)
            provider._healthy = False
            provider._available = False
            provider._warning = redacted_error or "provider marked unhealthy"
            if self._event_log:
                self._event_log.emit(
                    "provider_failed",
                    session_id=self._session_id,
                    provider_id=provider_id,
                    model=model,
                    role=role,
                    error=redacted_error,
                    error_type=_classify_provider_error(redacted_error),
                    duration_ms=duration_ms,
                    attempt=attempt,
                    retry_count=retry_count,
                    fallback_decision=fallback_decision,
                )
            logger.warning("Provider %s marked unhealthy", provider_id)


def _classify_provider_error(error: str) -> str:
    lower = error.lower()
    if "401" in lower or "unauthorized" in lower or "api_key" in lower:
        return "auth"
    if "429" in lower or "rate limit" in lower:
        return "rate_limit"
    if "timeout" in lower or "timed out" in lower:
        return "timeout"
    if "500" in lower or "internal server" in lower:
        return "server_error"
    if "context" in lower:
        return "context_limit"
    if "json" in lower or "schema" in lower:
        return "invalid_response"
    if "disconnect" in lower or "connection closed" in lower:
        return "stream_disconnect"
    return "provider_error"
