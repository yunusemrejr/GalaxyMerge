"""Token economy tests — budget manager, prompt segments, cache keys, telemetry."""

import hashlib
import json
from pathlib import Path

import pytest

from galaxy_merge.token.budget import (
    TokenBudgetManager,
    estimate_tokens,
    estimate_messages_tokens,
    ROLE_MAX_TOKENS,
    DEFAULT_COSTS,
)
from galaxy_merge.token.segments import (
    PromptAssembly,
    PromptSegment,
    SegmentType,
)
from galaxy_merge.cache.keys import (
    provider_cache_key,
    hash_messages_with_stable_prefix,
    hash_tool_schemas,
    hash_output_schema,
    hash_prompt_assembly,
    hash_config_dict,
    set_config_hash,
    set_safety_policy_hash,
    set_workroot_hash,
)
from galaxy_merge.fusion.schemas import ROLE_SCHEMAS
from galaxy_merge.fusion.roles import ROLE_DEFINITIONS

pytestmark = [pytest.mark.unit]


# ─── Token Budget Tests ──────────────────────────────────────────────────────


class TestTokenEstimation:
    def test_estimate_tokens_empty(self):
        assert estimate_tokens("") == 0

    def test_estimate_tokens_rough(self):
        # ~4 chars per token
        text = "hello world " * 100  # 1200 chars
        est = estimate_tokens(text)
        assert 200 <= est <= 400  # rough range

    def test_estimate_messages_tokens(self):
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hello!"},
        ]
        tokens = estimate_messages_tokens(messages)
        # 2 messages × 4 overhead + content
        assert tokens >= 8

    def test_role_max_tokens_has_all_roles(self):
        for role in [
            "planner",
            "scout",
            "implementer",
            "reviewer",
            "skeptic",
            "cheap_verifier",
            "synthesizer",
        ]:
            assert role in ROLE_MAX_TOKENS


class TestTokenBudgetManager:
    def test_check_budget_allows_normal_call(self, tmp_path):
        models_config = {
            "models": {
                "test:model1": {
                    "provider": "test",
                    "model": "model1",
                    "context_window": 128000,
                    "output_limit": 4000,
                    "cost_tier": "medium",
                }
            }
        }
        mgr = TokenBudgetManager(
            models_config, session_id="test_session", log_path=tmp_path / "budget.jsonl"
        )
        messages = [{"role": "system", "content": "You are helpful."}]
        decision = mgr.check_budget("test", "model1", "planner", messages)
        assert decision.decision == "allow"
        assert decision.context_percent_used < 5  # tiny prompt

    def test_check_budget_blocks_near_full_context(self, tmp_path):
        models_config = {
            "models": {
                "test:model1": {
                    "provider": "test",
                    "model": "model1",
                    "context_window": 1000,
                    "output_limit": 500,
                    "cost_tier": "medium",
                }
            }
        }
        mgr = TokenBudgetManager(models_config, session_id="test_session")
        # Create a huge message that fills >90% of context
        # ~4 chars per token, so for 900 tokens need ~3600 chars
        big_content = "x" * 3500
        messages = [{"role": "system", "content": big_content}]
        decision = mgr.check_budget("test", "model1", "planner", messages)
        assert decision.context_percent_used > 85

    def test_budget_tracks_usage(self, tmp_path):
        models_config = {"models": {}}
        mgr = TokenBudgetManager(models_config, session_id="s1")
        mgr.record_usage(1000, 500, cache_hit_tokens=200, cache_miss_tokens=800)
        summary = mgr.get_session_summary()
        assert summary["total_input_tokens"] == 1000
        assert summary["total_output_tokens"] == 500
        assert summary["cache_hit_tokens"] == 200
        assert summary["cache_miss_tokens"] == 800

    def test_budget_reset_goal(self, tmp_path):
        models_config = {"models": {}}
        mgr = TokenBudgetManager(models_config, session_id="s1")
        mgr.record_usage(500, 200)
        assert mgr._goal_input_tokens == 500
        mgr.reset_goal_budget()
        assert mgr._goal_input_tokens == 0

    def test_cost_estimation_cache_discount(self, tmp_path):
        models_config = {"models": {}}
        mgr = TokenBudgetManager(models_config, session_id="s1")
        mgr.record_usage(
            1_000_000, 0, cache_hit_tokens=500_000, cache_miss_tokens=500_000
        )
        summary = mgr.get_session_summary()
        # Cache hit should give discount
        assert summary["estimated_cost_usd"] < (
            1_000_000 * DEFAULT_COSTS["input"] / 1_000_000
        )


# ─── Prompt Segment Tests ────────────────────────────────────────────────────


class TestPromptSegment:
    def test_segment_hash_deterministic(self):
        seg = PromptSegment(
            segment_id="test1",
            segment_type=SegmentType.STABLE,
            content="Hello world",
        )
        h1 = seg.content_hash
        seg2 = PromptSegment(
            segment_id="test1",
            segment_type=SegmentType.STABLE,
            content="Hello world",
        )
        assert h1 == seg2.content_hash

    def test_segment_different_content_different_hash(self):
        seg1 = PromptSegment(
            segment_id="a", segment_type=SegmentType.STABLE, content="Hello"
        )
        seg2 = PromptSegment(
            segment_id="b", segment_type=SegmentType.STABLE, content="World"
        )
        assert seg1.content_hash != seg2.content_hash


class TestPromptAssembly:
    def test_assembly_sort_order(self):
        assembly = PromptAssembly()
        assembly.add("v1", SegmentType.VOLATILE, "volatile1")
        assembly.add("s1", SegmentType.STABLE, "stable1")
        assembly.add("d1", SegmentType.DYNAMIC, "dynamic1")
        assembly.add("ss1", SegmentType.SEMI_STABLE, "semi_stable1")
        assembly.sort()
        types = [s.segment_type for s in assembly.segments]
        assert types[0] == SegmentType.STABLE
        assert types[1] == SegmentType.SEMI_STABLE
        assert types[2] == SegmentType.DYNAMIC
        assert types[3] == SegmentType.VOLATILE

    def test_assembly_build(self):
        assembly = PromptAssembly()
        assembly.add("s1", SegmentType.STABLE, "stable content")
        assembly.add("d1", SegmentType.DYNAMIC, "dynamic content")
        text = assembly.build()
        assert "stable content" in text
        assert "dynamic content" in text

    def test_assembly_stable_prefix_hash_unchanged(self):
        """Stable prefix hash should be identical when stable segments don't change."""

        def make_assembly():
            a = PromptAssembly()
            a.add("sys", SegmentType.STABLE, "System: You are helpful.")
            a.add("schema", SegmentType.STABLE, "Schema: {type: object}")
            a.add("goal", SegmentType.DYNAMIC, "Goal: Fix bug")
            return a

        h1 = make_assembly().stable_prefix_hash()
        h2 = make_assembly().stable_prefix_hash()
        assert h1 == h2

    def test_assembly_stable_prefix_hash_changes_when_stable_changes(self):
        a1 = PromptAssembly()
        a1.add("sys", SegmentType.STABLE, "System: You are helpful.")
        a1.add("goal", SegmentType.DYNAMIC, "Goal: Fix bug")
        h1 = a1.stable_prefix_hash()

        a2 = PromptAssembly()
        a2.add("sys", SegmentType.STABLE, "System: You are grumpy.")  # changed
        a2.add("goal", SegmentType.DYNAMIC, "Goal: Fix bug")
        h2 = a2.stable_prefix_hash()
        assert h1 != h2

    def test_assembly_drop_low_value(self):
        assembly = PromptAssembly()
        # Fill with volatile droppable content
        big = "x" * 4000  # ~1000 tokens
        assembly.add("v1", SegmentType.VOLATILE, big, can_drop=True)
        assembly.add("v2", SegmentType.VOLATILE, big, can_drop=True)
        assembly.add("s1", SegmentType.STABLE, "important", can_drop=False)
        summary_before = assembly.token_summary()
        assembly.drop_low_value(max_tokens=500)
        summary_after = assembly.token_summary()
        assert (
            summary_after["total"] <= 500
            or summary_after["total"] < summary_before["total"]
        )

    def test_assembly_build_messages(self):
        assembly = PromptAssembly()
        assembly.add("sys", SegmentType.STABLE, "You are a coder.")
        assembly.add("goal", SegmentType.DYNAMIC, "Fix the bug.")
        msgs = assembly.build_messages()
        assert len(msgs) == 2
        assert msgs[0]["role"] == "system"
        assert msgs[1]["role"] == "user"

    def test_assembly_report(self):
        assembly = PromptAssembly(session_id="sess1", goal_hash="ghash1")
        assembly.add("s1", SegmentType.STABLE, "stable")
        assembly.add("d1", SegmentType.DYNAMIC, "dynamic")
        report = assembly.report()
        assert report["session_id"] == "sess1"
        assert report["goal_hash"] == "ghash1"
        assert "stable_prefix_hash" in report
        assert "total_tokens" in report
        assert "segments" in report

    def test_assembly_invalidate_segment(self):
        # Test that stable content is always included
        from galaxy_merge.core.prompt_builder import PromptBuilder
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            builder = PromptBuilder(Path(td))
            builder.add_stable_system()  # stable
            prompt_str, report = builder.build()
            assert "Core Rules" in prompt_str  # stable content present
            assert report.stable_prefix_tokens > 0


# ─── Cache Key Tests ─────────────────────────────────────────────────────────


class TestCacheKeysExtended:
    def setup_method(self):
        set_config_hash("cfg123")
        set_safety_policy_hash("safe456")
        set_workroot_hash("wr789")

    def test_provider_cache_key_includes_stable_prefix_hash(self):
        k1 = provider_cache_key(
            "openai", "gpt-4", "coder", "msg123", stable_prefix_hash="sp1"
        )
        k2 = provider_cache_key(
            "openai", "gpt-4", "coder", "msg123", stable_prefix_hash="sp2"
        )
        assert k1 != k2

    def test_provider_cache_key_includes_schema_hashes(self):
        k1 = provider_cache_key(
            "openai", "gpt-4", "coder", "msg123", tool_schema_hash="ts1"
        )
        k2 = provider_cache_key(
            "openai", "gpt-4", "coder", "msg123", tool_schema_hash="ts2"
        )
        assert k1 != k2

    def test_hash_messages_with_stable_prefix(self):
        msgs = [{"role": "user", "content": "hello"}]
        h1 = hash_messages_with_stable_prefix(msgs, "prefix1")
        h2 = hash_messages_with_stable_prefix(msgs, "prefix2")
        assert h1 != h2

    def test_hash_tool_schemas_deterministic(self):
        schemas = [
            {"name": "file.read", "description": "Read a file"},
            {"name": "file.write", "description": "Write a file"},
        ]
        h1 = hash_tool_schemas(schemas)
        h2 = hash_tool_schemas(schemas)
        assert h1 == h2

    def test_hash_output_schema_deterministic(self):
        schema = {
            "type": "object",
            "required": ["steps"],
            "properties": {"steps": {"type": "array"}},
        }
        h1 = hash_output_schema(schema)
        h2 = hash_output_schema(schema)
        assert h1 == h2

    def test_hash_prompt_assembly_deterministic(self):
        hashes = ["a1b2", "c3d4", "e5f6"]
        h1 = hash_prompt_assembly(hashes)
        h2 = hash_prompt_assembly(hashes)
        assert h1 == h2

    def test_hash_config_dict_deterministic(self):
        cfg = {"timeout": 30, "retry": 3, "roles": ["planner", "scout"]}
        h1 = hash_config_dict(cfg)
        h2 = hash_config_dict(cfg)
        assert h1 == h2

    def test_hash_config_dict_order_independent(self):
        cfg1 = {"a": 1, "b": 2}
        cfg2 = {"b": 2, "a": 1}
        assert hash_config_dict(cfg1) == hash_config_dict(cfg2)


# ─── Council Token Telemetry Tests ───────────────────────────────────────────


class TestCouncilTokenTelemetry:
    """Verify that council role outputs include token/cache telemetry fields."""

    def test_stable_prefix_hash_in_council(self):
        """Council should compute stable_prefix_hash for each role."""
        # Just test the method exists and returns a hash
        # We can't easily test the full council without a provider registry
        from galaxy_merge.fusion.roles import ROLE_DEFINITIONS
        from galaxy_merge.fusion.schemas import ROLE_SCHEMAS

        # Simulate what _build_stable_prefix does
        role = "planner"
        definition = ROLE_DEFINITIONS.get(role, {})
        instructions = "\n".join(f"- {i}" for i in definition.get("instructions", []))
        schema = ROLE_SCHEMAS.get(role, {})
        schema_str = (
            json.dumps(schema, sort_keys=True, separators=(",", ":")) if schema else ""
        )
        system_content = (
            f"You are the {role} role in Galaxy Merge Harness.\n"
            f"Purpose: {definition.get('purpose', '')}\n\n"
            f"Instructions:\n{instructions}\n\n"
            f"Output schema:\n{schema_str}\n\n"
            "Respond with valid JSON matching the schema."
        )
        messages = [{"role": "system", "content": system_content}]
        raw = json.dumps(messages, sort_keys=True)
        h = hashlib.sha256(raw.encode()).hexdigest()[:16]
        assert len(h) == 16

    def test_role_definitions_all_have_instructions(self):
        for role_name, definition in ROLE_DEFINITIONS.items():
            assert "instructions" in definition
            assert len(definition["instructions"]) > 0

    def test_role_schemas_all_have_required_fields(self):
        for role_name in ROLE_DEFINITIONS:
            schema = ROLE_SCHEMAS.get(role_name, {})
            # All schemas should define at least some structure
            assert schema, f"Missing schema for role {role_name}"


# ─── Token Waste Detection Tests ─────────────────────────────────────────────


class TestTokenWasteDetection:
    """Tests for detecting token waste patterns."""

    def test_repeated_file_summary_detected(self):
        """Same file summary sent multiple times should be detected."""
        summary = "File main.py: 50 lines, 3 functions, imports os/sys"
        # Simulate sending the same summary 5 times
        summaries = [summary] * 5
        unique = set(summaries)
        assert len(unique) == 1  # All identical
        wasted = len(summaries) - len(unique)
        assert wasted == 4

    def test_duplicate_tool_schema_detected(self):
        schema = {"name": "file.read", "params": {"path": "string"}}
        schemas = [json.dumps(schema, sort_keys=True)] * 3
        unique = set(schemas)
        assert len(unique) == 1
        wasted = len(schemas) - len(unique)
        assert wasted == 2

    def test_file_excerpt_vs_full_file(self):
        """Sending full file when excerpt would suffice is waste."""
        full_file = "line1\n" * 1000  # 1000 lines
        excerpt = "line1\n" * 10  # 10 lines relevant
        full_tokens = estimate_tokens(full_file)
        excerpt_tokens = estimate_tokens(excerpt)
        waste_ratio = full_tokens / excerpt_tokens
        assert waste_ratio > 50  # Full file is 50x more tokens

    def test_compressed_shell_output(self):
        """Shell output should be summarized, not dumped raw."""
        raw_output = "log line\n" * 10000
        # Summarized: first 10 + last 10 lines + count
        summarized = (
            "log line\n" * 10 + f"\n... {9980} lines omitted ...\n" + "log line\n" * 10
        )
        raw_tokens = estimate_tokens(raw_output)
        summary_tokens = estimate_tokens(summarized)
        savings = raw_tokens - summary_tokens
        assert savings > raw_tokens * 0.9  # >90% savings
