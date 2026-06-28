import asyncio
import hashlib
import json
import logging
import time
from typing import Any

from galaxy_merge.providers.registry import ProviderRegistry
from galaxy_merge.fusion.schemas import ROLE_SCHEMAS
from galaxy_merge.fusion.roles import ROLE_DEFINITIONS
from galaxy_merge.fusion.synthesizer import repair_malformed
from galaxy_merge.safety.credential_policy import redact_text
from galaxy_merge.token.segments import PromptAssembly, SegmentType

logger = logging.getLogger("galaxy_merge.fusion.council")


class Council:
    def __init__(
        self,
        providers: ProviderRegistry,
        config: dict[str, Any],
        goal: str,
        event_log=None,
        session_id: str = "",
    ):
        self.providers = providers
        self.config = config
        self.goal = goal
        self.max_parallel = config.get("max_parallel_calls", 4)
        self.timeout = config.get("timeout_seconds", 180)
        self.event_log = event_log
        self.session_id = session_id
        self._results: dict[str, list[dict[str, Any]]] = {}
        # Track degraded state per role
        self._degraded_roles: list[str] = []
        self._failed_roles: list[str] = []

    async def execute(self) -> dict[str, Any]:
        roles_config = self.config.get("roles", {})
        tasks = []

        for role_name, role_config in roles_config.items():
            if not role_config.get("required", True):
                continue
            count = role_config.get("count", 1)
            for _ in range(count):
                tasks.append(self._execute_role_with_fallback(role_name, role_config))

        sem = asyncio.Semaphore(self.max_parallel)

        async def _limited(task):
            async with sem:
                return await task

        results = await asyncio.gather(
            *[_limited(t) for t in tasks], return_exceptions=True
        )

        role_names = []
        for role_name, role_config in roles_config.items():
            if not role_config.get("required", True):
                continue
            for _ in range(role_config.get("count", 1)):
                role_names.append(role_name)

        for i, role_name in enumerate(role_names):
            result = results[i] if i < len(results) else None
            if isinstance(result, Exception):
                self._results.setdefault(role_name, []).append({"error": str(result)})
                self._degraded_roles.append(role_name)
                self._failed_roles.append(role_name)
            elif result:
                if "error" in result:
                    self._degraded_roles.append(role_name)
                    self._failed_roles.append(role_name)
                self._results.setdefault(role_name, []).append(result)

        # Enforce minimum quorum
        quorum = self.config.get("minimum_quorum", 0)
        if quorum > 0:
            successful_roles = [
                r
                for r in self._results.keys()
                if any("error" not in rr for rr in self._results[r])
            ]
            if len(successful_roles) < quorum:
                logger.warning(
                    "Council quorum not met: %d/%d roles succeeded (quorum=%d)",
                    len(successful_roles),
                    len(roles_config),
                    quorum,
                )
                if self.event_log:
                    self.event_log.emit(
                        "council_quorum_failed",
                        session_id=self.session_id,
                        succeeded=len(successful_roles),
                        required=quorum,
                    )

        return self._results

    async def _execute_role_with_fallback(
        self, role_name: str, role_config: dict[str, Any]
    ) -> dict[str, Any]:
        selector = role_config.get("model_selector", {})
        cost_policy = selector.get("cost_policy", "balanced")
        prefer_strengths = selector.get("prefer_strengths", None)

        best = self.providers.select_best_model(
            role_name, cost_policy, prefer_strengths
        )
        if not best:
            candidates = self.providers.get_models_for_role(role_name)
            if candidates:
                best = candidates[0]
            else:
                return {"role": role_name, "error": "no eligible models found"}

        provider_id, model, model_config = best
        errors = []

        max_retries = self.config.get("retry_count", 3)
        start = time.monotonic()
        # Track per-provider retry attempts
        provider_retry_count: dict[str, int] = {}
        tried_providers: set[str] = set()

        while True:
            provider = self.providers.get(provider_id)
            if not provider:
                return {"role": role_name, "error": "provider not available"}

            if not provider.healthy:
                next_best = self._find_fallback(
                    role_name, provider_id, cost_policy, exclude=tried_providers
                )
                if next_best:
                    provider_id, model, _ = next_best
                    provider = self.providers.get(provider_id)
                else:
                    self._emit_provider_failed(
                        role_name,
                        provider_id,
                        model,
                        "no healthy provider available",
                        provider_retry_count.get(provider_id, 0),
                        start,
                    )
                    return {"role": role_name, "error": "no healthy provider available"}

            # Build prompt using segment assembly for cache-friendly ordering
            assembly = self._build_assembly(role_name)
            messages = assembly.build_messages()
            stable_prefix_hash = assembly.stable_prefix_hash()
            prompt_hash = assembly.full_prompt_hash()

            per_role_timeout = self.config.get("per_role_timeout", self.timeout)
            total_attempts = sum(provider_retry_count.values())
            if self.event_log:
                self.event_log.emit(
                    "provider_called",
                    session_id=self.session_id,
                    role=role_name,
                    provider_id=provider_id,
                    provider=provider_id,
                    model=model,
                    attempt=total_attempts + 1,
                    timeout_seconds=per_role_timeout,
                )
            try:
                # Pass extra_body for cache-aware providers (DeepSeek, etc.)
                extra_body: dict[str, Any] = {}
                if stable_prefix_hash and getattr(
                    provider, "supports_prefix_cache", False
                ):
                    extra_body["metadata"] = {"stable_prefix_hash": stable_prefix_hash}
                if extra_body:
                    result = await asyncio.wait_for(
                        provider.chat_completion(
                            messages, model, temperature=0.3, extra_body=extra_body
                        ),
                        timeout=per_role_timeout,
                    )
                else:
                    result = await asyncio.wait_for(
                        provider.chat_completion(messages, model, temperature=0.3),
                        timeout=per_role_timeout,
                    )
            except asyncio.TimeoutError:
                result = {
                    "success": False,
                    "error": f"request timed out after {per_role_timeout}s",
                }

            if result.get("success"):
                content = result["content"]
                repaired = repair_malformed(content)
                try:
                    parsed = json.loads(repaired)
                except json.JSONDecodeError:
                    parsed = {"raw": content}

                # Validate output against schema
                schema = ROLE_SCHEMAS.get(role_name, {})
                required_fields = schema.get("required", [])
                missing_fields = [
                    f for f in required_fields if f not in parsed or not parsed.get(f)
                ]
                if missing_fields:
                    provider_retry_count[provider_id] = (
                        provider_retry_count.get(provider_id, 0) + 1
                    )
                    errors.append(
                        f"attempt {total_attempts + 1}: missing required fields {missing_fields}"
                    )
                    self._emit_provider_failed(
                        role_name,
                        provider_id,
                        model,
                        f"schema validation: missing {missing_fields}",
                        provider_retry_count[provider_id],
                        start,
                    )
                    next_best = self._find_fallback(
                        role_name, provider_id, cost_policy, exclude=tried_providers
                    )
                    if next_best:
                        provider_id, model, _ = next_best
                        backoff = self.config.get("retry_backoff", 1.0) * (
                            2 ** (provider_retry_count.get(provider_id, 0))
                        )
                        capped_backoff = min(
                            backoff, self.config.get("retry_backoff_max", 30.0)
                        )
                        await asyncio.sleep(capped_backoff)
                        continue
                    break

                return {
                    "role": role_name,
                    "content": content,
                    "parsed": parsed,
                    "model": result.get("model", model),
                    "provider": provider_id,
                    "attempt": total_attempts + 1,
                    "usage": result.get("usage", {}),
                    "cache_hit_tokens": result.get("cache_hit_tokens", 0),
                    "cache_miss_tokens": result.get("cache_miss_tokens", 0),
                    "stable_prefix_hash": stable_prefix_hash,
                    "prompt_hash": prompt_hash,
                }
            else:
                error_msg = result.get("error", "unknown")
                provider_retry_count[provider_id] = (
                    provider_retry_count.get(provider_id, 0) + 1
                )
                errors.append(f"attempt {total_attempts + 1}: {error_msg}")
                self._emit_provider_failed(
                    role_name,
                    provider_id,
                    model,
                    error_msg,
                    provider_retry_count[provider_id],
                    start,
                )
                # Mark unhealthy to prevent cycling back to failed providers
                self.providers.mark_unhealthy(
                    provider_id,
                    model=model,
                    role=role_name,
                    error=error_msg,
                    attempt=provider_retry_count[provider_id],
                    duration_ms=self._elapsed_ms(start),
                    retry_count=max_retries,
                    fallback_decision="pending",
                )
                tried_providers.add(provider_id)

                # First, try retrying the same provider if under max_retries
                if provider_retry_count[provider_id] < max_retries:
                    backoff = self.config.get("retry_backoff", 1.0) * (
                        2 ** (provider_retry_count[provider_id] - 1)
                    )
                    capped_backoff = min(
                        backoff, self.config.get("retry_backoff_max", 30.0)
                    )
                    logger.info(
                        "Role %s retrying %s (attempt %d)",
                        role_name,
                        provider_id,
                        provider_retry_count[provider_id] + 1,
                    )
                    await asyncio.sleep(capped_backoff)
                    continue

                # Provider exhausted its retries, try fallback to a new provider
                next_best = self._find_fallback(
                    role_name, provider_id, cost_policy, exclude=tried_providers
                )
                if next_best:
                    provider_id, model, _ = next_best
                    logger.info("Role %s falling back to %s", role_name, provider_id)
                    await asyncio.sleep(self.config.get("retry_backoff", 1.0))
                    continue
                else:
                    break

        self._emit_provider_failed(
            role_name, provider_id, model, "; ".join(errors), max_retries, start
        )
        return {"role": role_name, "error": "; ".join(errors)}

    def _find_fallback(
        self,
        role_name: str,
        failed_provider: str,
        cost_policy: str,
        exclude: set[str] | None = None,
    ) -> tuple[str, str, dict[str, Any]] | None:
        candidates = self.providers.get_models_for_role(role_name)
        tried = {failed_provider}
        if exclude:
            tried.update(exclude)
        for provider_id, model, model_config in candidates:
            if provider_id in tried:
                continue
            provider = self.providers.get(provider_id)
            if provider:
                tried.add(provider_id)
                if provider.healthy:
                    logger.info(
                        "Fallback for %s: %s -> %s (%s)",
                        role_name,
                        failed_provider,
                        provider_id,
                        model,
                    )
                    if self.event_log:
                        self.event_log.emit(
                            "role_fallback",
                            session_id=self.session_id,
                            role=role_name,
                            from_provider=failed_provider,
                            to_provider=provider_id,
                            model=model,
                            fallback_decision="selected",
                            retry_count=self.config.get("retry_count", 3),
                        )
                    return (provider_id, model, model_config)
        return None

    def _emit_provider_failed(
        self,
        role: str,
        provider_id: str,
        model: str,
        error: str,
        attempt: int,
        start: float,
    ):
        if role not in self._degraded_roles:
            self._degraded_roles.append(role)
        redacted_error = redact_text(error)
        if self.event_log:
            self.event_log.emit(
                "role_execution_failed",
                session_id=self.session_id,
                role=role,
                provider_id=provider_id,
                provider=provider_id,
                model=model,
                error=redacted_error,
                error_type=self._classify_error(redacted_error),
                duration_ms=self._elapsed_ms(start),
                attempt=attempt,
                retry_count=self.config.get("retry_count", 3),
                fallback_decision="pending"
                if attempt < self.config.get("retry_count", 3)
                else "exhausted",
            )
        logger.warning(
            "Role %s on provider %s failed (attempt %d): %s",
            role,
            provider_id,
            attempt,
            redacted_error,
        )

    def _elapsed_ms(self, start: float) -> int:
        return int((time.monotonic() - start) * 1000)

    def _classify_error(self, error: str) -> str:
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
        if "schema validation" in lower or "json" in lower:
            return "invalid_response"
        if "disconnect" in lower or "connection closed" in lower:
            return "stream_disconnect"
        return "provider_error"

    def get_degraded_roles(self) -> list[str]:
        return list(self._degraded_roles)

    def get_failed_roles(self) -> list[str]:
        return list(self._failed_roles)

    def _build_stable_prefix(self, role: str) -> list[dict[str, str]]:
        """Build a deterministic, cache-friendly stable prefix for a role.

        The content is constructed with canonical JSON serialization and
        stable ordering so that repeated calls produce byte-identical
        prefixes when inputs have not changed.
        """
        definition = ROLE_DEFINITIONS.get(role, {})
        instructions = "\n".join(f"- {i}" for i in definition.get("instructions", []))
        schema = ROLE_SCHEMAS.get(role, {})
        # Canonical JSON: sort_keys, no extra whitespace
        schema_str = (
            json.dumps(schema, sort_keys=True, separators=(",", ":")) if schema else ""
        )
        # Stable system prompt template — never change whitespace here
        system_content = (
            f"You are the {role} role in Galaxy Merge Harness.\n"
            f"Purpose: {definition.get('purpose', '')}\n\n"
            f"Instructions:\n{instructions}\n\n"
            f"Output schema:\n{schema_str}\n\n"
            "Respond with valid JSON matching the schema."
        )
        return [{"role": "system", "content": system_content}]

    def _stable_prefix_hash(self, role: str) -> str:
        """Deterministic hash of the stable prefix for cache tracking."""
        messages = self._build_stable_prefix(role)
        raw = json.dumps(messages, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def _build_assembly(self, role: str) -> PromptAssembly:
        """Build a PromptAssembly for a role call with proper segment ordering."""
        assembly = PromptAssembly(session_id=self.session_id, goal_hash="")
        # Stable prefix: role definition + output schema
        stable_msgs = self._build_stable_prefix(role)
        stable_content = stable_msgs[0]["content"] if stable_msgs else ""
        assembly.add(
            segment_id=f"role_definition_{role}",
            segment_type=SegmentType.STABLE,
            content=stable_content,
            source=f"ROLE_DEFINITIONS[{role}]",
            provider_cache_relevant=True,
            required_for_completion=True,
        )
        # Dynamic: the goal
        assembly.add(
            segment_id="goal",
            segment_type=SegmentType.DYNAMIC,
            content=f"Goal: {self.goal}",
            source="council.goal",
            provider_cache_relevant=False,
            required_for_completion=True,
        )
        return assembly

    def _build_role_prompt(self, role: str) -> str:
        return self._build_stable_prefix(role)[0]["content"]
