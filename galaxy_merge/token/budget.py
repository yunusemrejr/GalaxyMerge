"""Token Budget Manager — central token/cost accounting for every provider call.

Every provider/model/role call must go through this module before execution.
Tracks estimated input/output tokens, context percent used, cacheable prefix,
expected cost, and budget decisions.

No secrets are stored in budget records.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from galaxy_merge.core.locks import atomic_append


@dataclass
class TokenBudgetDecision:
    """Record of a token budget decision for one provider call."""

    provider_id: str
    model_id: str
    role: str
    session_id: str
    goal_hash: str
    prompt_hash: str
    stable_prefix_hash: str
    total_estimated_input_tokens: int
    estimated_output_tokens: int
    estimated_total_tokens: int
    context_window: int
    context_percent_used: float
    budget_remaining: float
    cacheable_prefix_tokens: int
    non_cacheable_tokens: int
    estimated_cost_cache_miss: float
    estimated_cost_cache_hit: float
    decision: str  # allow, allow_with_audit, block, downgrade, compact_first
    reason: str
    retrieved_narrower: bool = False
    summarized_stale: bool = False
    compressed_tool_results: bool = False
    replaced_with_hashes: bool = False
    dropped_low_value: bool = False
    downgraded_model: bool = False
    split_task: bool = False
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "role": self.role,
            "session_id": self.session_id,
            "goal_hash": self.goal_hash,
            "prompt_hash": self.prompt_hash,
            "stable_prefix_hash": self.stable_prefix_hash,
            "total_estimated_input_tokens": self.total_estimated_input_tokens,
            "estimated_output_tokens": self.estimated_output_tokens,
            "estimated_total_tokens": self.estimated_total_tokens,
            "context_window": self.context_window,
            "context_percent_used": round(self.context_percent_used, 2),
            "budget_remaining": round(self.budget_remaining, 4),
            "cacheable_prefix_tokens": self.cacheable_prefix_tokens,
            "non_cacheable_tokens": self.non_cacheable_tokens,
            "estimated_cost_cache_miss": round(self.estimated_cost_cache_miss, 6),
            "estimated_cost_cache_hit": round(self.estimated_cost_cache_hit, 6),
            "decision": self.decision,
            "reason": self.reason,
            "retrieved_narrower": self.retrieved_narrower,
            "summarized_stale": self.summarized_stale,
            "compressed_tool_results": self.compressed_tool_results,
            "replaced_with_hashes": self.replaced_with_hashes,
            "dropped_low_value": self.dropped_low_value,
            "downgraded_model": self.downgraded_model,
            "split_task": self.split_task,
            "timestamp": self.timestamp,
        }


# Role-specific max token budgets (defaults, overridable via models.json)
ROLE_MAX_TOKENS: dict[str, int] = {
    "planner": 8000,
    "scout": 16000,
    "implementer": 12000,
    "reviewer": 16000,
    "skeptic": 16000,
    "cheap_verifier": 4000,
    "synthesizer": 12000,
}

# Default cost per 1M tokens (USD) — fallback when not configured
DEFAULT_COSTS: dict[str, float] = {
    "input": 0.50,
    "output": 1.50,
    "cached_input": 0.10,  # DeepSeek-style cached input discount
}


def estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token for English code/text."""
    if not text:
        return 0
    return max(1, len(text) // 4)


def estimate_messages_tokens(messages: list[dict[str, str]]) -> int:
    """Estimate total tokens in a message list."""
    total = 0
    for msg in messages:
        total += estimate_tokens(msg.get("content", ""))
        # Overhead per message (~3-5 tokens for role markers)
        total += 4
    return total


class TokenBudgetManager:
    """Central token budget manager for provider calls."""

    def __init__(
        self,
        models_config: dict[str, Any],
        session_id: str = "",
        log_path: Path | None = None,
    ):
        """
        Args:
            models_config: Parsed models.json config dict.
            session_id: Current session ID for logging.
            log_path: Path to write budget decision JSONL records.
        """
        self.models_config = models_config
        self.session_id = session_id
        self.log_path = log_path
        # Per-session token tracking
        self._session_input_tokens: int = 0
        self._session_output_tokens: int = 0
        self._session_cache_hit_tokens: int = 0
        self._session_cache_miss_tokens: int = 0
        self._goal_input_tokens: int = 0

    def get_model_config(self, provider_id: str, model_id: str) -> dict[str, Any]:
        """Look up model config from models.json."""
        models = self.models_config.get("models", {})
        for key, cfg in models.items():
            if cfg.get("provider") == provider_id and cfg.get("model") == model_id:
                return cfg
        return {}

    def check_budget(
        self,
        provider_id: str,
        model_id: str,
        role: str,
        messages: list[dict[str, str]],
        stable_prefix_tokens: int = 0,
        goal_hash: str = "",
        prompt_hash: str = "",
        stable_prefix_hash: str = "",
    ) -> TokenBudgetDecision:
        """Evaluate token budget for a provider call.

        Returns a TokenBudgetDecision with the recommendation.
        """
        model_cfg = self.get_model_config(provider_id, model_id)
        context_window = model_cfg.get("context_window", 128000)
        output_limit = model_cfg.get("output_limit", 4000)
        cost_tier = model_cfg.get("cost_tier", "medium")
        supports_prefix_cache = model_cfg.get("cache_behavior", {}).get(
            "supports_prefix_cache", False
        )

        # Estimate tokens
        input_tokens = estimate_messages_tokens(messages)
        output_tokens = min(output_limit, max(256, input_tokens // 4))
        total_tokens = input_tokens + output_tokens

        # Context usage
        context_percent = (total_tokens / context_window) * 100 if context_window else 0

        # Cacheable prefix
        cacheable_tokens = stable_prefix_tokens if supports_prefix_cache else 0
        non_cacheable = input_tokens - cacheable_tokens

        # Cost estimation
        cost_miss = self._estimate_cost(
            input_tokens, output_tokens, cost_tier, cache_hit=False
        )
        cost_hit = self._estimate_cost(
            input_tokens, output_tokens, cost_tier, cache_hit=True
        )

        # Budget remaining (0.0–1.0)
        role_max = ROLE_MAX_TOKENS.get(role, 8000)
        budget_remaining = (
            max(0.0, 1.0 - (self._goal_input_tokens / role_max)) if role_max else 1.0
        )

        # Decision logic
        decision, reason = self._make_decision(
            context_percent, budget_remaining, input_tokens, role_max, cost_miss
        )

        return TokenBudgetDecision(
            provider_id=provider_id,
            model_id=model_id,
            role=role,
            session_id=self.session_id,
            goal_hash=goal_hash,
            prompt_hash=prompt_hash,
            stable_prefix_hash=stable_prefix_hash,
            total_estimated_input_tokens=input_tokens,
            estimated_output_tokens=output_tokens,
            estimated_total_tokens=total_tokens,
            context_window=context_window,
            context_percent_used=context_percent,
            budget_remaining=budget_remaining,
            cacheable_prefix_tokens=cacheable_tokens,
            non_cacheable_tokens=non_cacheable,
            estimated_cost_cache_miss=cost_miss,
            estimated_cost_cache_hit=cost_hit,
            decision=decision,
            reason=reason,
        )

    def _estimate_cost(
        self, input_tokens: int, output_tokens: int, cost_tier: str, cache_hit: bool
    ) -> float:
        """Estimate USD cost for a call."""
        # Tier-based multipliers
        tier_mult = {"free": 0.0, "local": 0.0, "low": 0.5, "medium": 1.0, "high": 3.0}
        mult = tier_mult.get(cost_tier, 1.0)
        input_rate = DEFAULT_COSTS["input"] * mult
        output_rate = DEFAULT_COSTS["output"] * mult
        if cache_hit:
            input_rate = DEFAULT_COSTS["cached_input"] * mult
        return (input_tokens * input_rate + output_tokens * output_rate) / 1_000_000

    def _make_decision(
        self,
        context_percent: float,
        budget_remaining: float,
        input_tokens: int,
        role_max: int,
        cost: float,
    ) -> tuple[str, str]:
        """Make budget decision based on constraints."""
        reasons = []

        if context_percent > 90:
            return "block", f"context window nearly full ({context_percent:.1f}%)"

        if context_percent > 80:
            reasons.append(f"high context usage ({context_percent:.1f}%)")
            if budget_remaining < 0.2:
                return "compact_first", "; ".join(reasons + ["budget nearly exhausted"])

        if budget_remaining < 0.1:
            return (
                "block",
                f"role token budget exhausted ({budget_remaining:.1%} remaining)",
            )

        if budget_remaining < 0.3:
            reasons.append(f"low budget remaining ({budget_remaining:.1%})")
            return "allow_with_audit", "; ".join(reasons)

        if input_tokens > role_max * 1.5:
            reasons.append(f"input exceeds role max ({input_tokens} > {role_max})")
            return "compact_first", "; ".join(reasons)

        return "allow", "; ".join(reasons) if reasons else "within budget"

    def record_usage(
        self,
        input_tokens: int,
        output_tokens: int,
        cache_hit_tokens: int = 0,
        cache_miss_tokens: int = 0,
    ) -> None:
        """Track token usage for the current session/goal."""
        self._session_input_tokens += input_tokens
        self._session_output_tokens += output_tokens
        self._session_cache_hit_tokens += cache_hit_tokens
        self._session_cache_miss_tokens += cache_miss_tokens
        self._goal_input_tokens += input_tokens

    def log_decision(self, decision: TokenBudgetDecision) -> None:
        """Write budget decision to JSONL log."""
        if self.log_path:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            atomic_append(self.log_path, json.dumps(decision.to_dict(), default=str))

    def get_session_summary(self) -> dict[str, Any]:
        """Return current session token summary."""
        return {
            "session_id": self.session_id,
            "total_input_tokens": self._session_input_tokens,
            "total_output_tokens": self._session_output_tokens,
            "cache_hit_tokens": self._session_cache_hit_tokens,
            "cache_miss_tokens": self._session_cache_miss_tokens,
            "estimated_cost_usd": self._estimate_session_cost(),
        }

    def _estimate_session_cost(self) -> float:
        """Rough session cost estimate."""
        # Use medium tier as default
        input_cost = self._session_input_tokens * DEFAULT_COSTS["input"] / 1_000_000
        output_cost = self._session_output_tokens * DEFAULT_COSTS["output"] / 1_000_000
        cache_discount = (
            self._session_cache_hit_tokens
            * (DEFAULT_COSTS["input"] - DEFAULT_COSTS["cached_input"])
            / 1_000_000
        )
        return max(0.0, input_cost + output_cost - cache_discount)

    def reset_goal_budget(self) -> None:
        """Reset per-goal token tracking (call when starting a new goal)."""
        self._goal_input_tokens = 0
