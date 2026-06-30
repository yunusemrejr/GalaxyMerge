"""Unit tests for PromptBuilder — segment-based prompt construction."""

import json
import pytest

from galaxy_merge.core.prompt_builder import (
    PromptBuilder,
    PromptSegment,
    PromptAssemblyReport,
    build_stable_prefix,
)

pytestmark = [pytest.mark.unit]


class TestPromptSegment:
    def test_auto_computes_content_hash(self):
        seg = PromptSegment(
            segment_id="test", segment_type="stable", content="hello world"
        )
        assert seg.content_hash != ""
        assert len(seg.content_hash) == 16

    def test_auto_computes_token_estimate(self):
        seg = PromptSegment(
            segment_id="test",
            segment_type="stable",
            content="a" * 100,
        )
        assert seg.token_estimate == 25  # 100 // 4

    def test_uses_provided_hash(self):
        seg = PromptSegment(
            segment_id="test",
            segment_type="stable",
            content="hello",
            content_hash="custom_hash",
        )
        assert seg.content_hash == "custom_hash"

    def test_segment_types(self):
        for stype in ("stable", "semi_stable", "dynamic", "volatile"):
            seg = PromptSegment(
                segment_id=f"test_{stype}", segment_type=stype, content="x"
            )
            assert seg.segment_type == stype


class TestPromptBuilder:
    def test_build_returns_string_and_report(self, tmp_path):
        builder = PromptBuilder(tmp_path, "test_provider", "test_model")
        builder.add_stable_system()
        prompt_str, report = builder.build()
        assert isinstance(prompt_str, str)
        assert isinstance(report, PromptAssemblyReport)

    def test_build_produces_valid_json_messages(self, tmp_path):
        builder = PromptBuilder(tmp_path)
        builder.add_stable_system()
        builder.add_safety_summary()
        prompt_str, _ = builder.build()
        messages = json.loads(prompt_str)
        assert isinstance(messages, list)
        assert any(m["role"] == "system" for m in messages)

    def test_stable_segments_come_before_dynamic(self, tmp_path):
        builder = PromptBuilder(tmp_path)
        builder.add_goal("fix the bug", ["bug is fixed"])
        builder.add_stable_system()
        prompt_str, _ = builder.build()
        messages = json.loads(prompt_str)
        # System message (stable) should come before user message (dynamic)
        system_idx = next(
            i for i, m in enumerate(messages) if m["role"] == "system"
        )
        user_idx = next(
            i for i, m in enumerate(messages) if m["role"] == "user"
        )
        assert system_idx < user_idx

    def test_report_tracks_token_counts(self, tmp_path):
        builder = PromptBuilder(tmp_path, "p", "m")
        builder.add_stable_system()
        builder.add_goal("test goal", [])
        _, report = builder.build()
        assert report.total_estimated_input_tokens > 0
        assert report.stable_prefix_tokens > 0
        assert report.segment_count >= 2

    def test_report_tracks_segment_ids(self, tmp_path):
        builder = PromptBuilder(tmp_path)
        builder.add_stable_system()
        builder.add_safety_summary()
        _, report = builder.build()
        assert "system_core" in report.reused_segment_ids
        assert "safety_summary" in report.reused_segment_ids

    def test_add_tool_schemas(self, tmp_path):
        builder = PromptBuilder(tmp_path)
        builder.add_tool_schemas(
            [
                {"name": "file.read", "description": "Read a file", "mutates": False},
                {"name": "file.write", "description": "Write a file", "mutates": True},
            ]
        )
        prompt_str, _ = builder.build()
        messages = json.loads(prompt_str)
        content = messages[0]["content"]
        assert "file.read" in content
        assert "file.write" in content

    def test_add_role_instructions(self, tmp_path):
        builder = PromptBuilder(tmp_path)
        builder.add_role_instructions(
            "planner",
            {
                "purpose": "Create plans",
                "instructions": ["Be minimal", "Avoid overengineering"],
            },
            {"type": "object", "properties": {"steps": {"type": "array"}}},
        )
        prompt_str, _ = builder.build()
        messages = json.loads(prompt_str)
        content = messages[0]["content"]
        assert "planner" in content
        assert "Be minimal" in content

    def test_add_project_identity(self, tmp_path):
        builder = PromptBuilder(tmp_path)
        builder.add_project_identity("/tmp/test", "TestProject", ["python", "fastapi"])
        prompt_str, _ = builder.build()
        messages = json.loads(prompt_str)
        content = messages[0]["content"]
        assert "TestProject" in content
        assert "python" in content

    def test_add_goal(self, tmp_path):
        builder = PromptBuilder(tmp_path)
        builder.add_goal("fix the login", ["login works", "tests pass"])
        prompt_str, _ = builder.build()
        messages = json.loads(prompt_str)
        content = messages[-1]["content"]
        assert "fix the login" in content
        assert "login works" in content

    def test_add_file_evidence(self, tmp_path):
        builder = PromptBuilder(tmp_path)
        builder.add_file_evidence("src/main.py", "print('hello')")
        prompt_str, _ = builder.build()
        messages = json.loads(prompt_str)
        content = messages[-1]["content"]
        assert "src/main.py" in content
        assert "print('hello')" in content

    def test_add_tool_results(self, tmp_path):
        builder = PromptBuilder(tmp_path)
        builder.add_tool_results(
            [{"tool": "file.write", "status": "success", "data": {"path": "test.py"}}]
        )
        prompt_str, _ = builder.build()
        messages = json.loads(prompt_str)
        content = messages[-1]["content"]
        assert "file.write" in content

    def test_reset_clears_segments(self, tmp_path):
        builder = PromptBuilder(tmp_path)
        builder.add_stable_system()
        builder.reset()
        prompt_str, _ = builder.build()
        messages = json.loads(prompt_str)
        assert len(messages) == 0 or all(m["content"] == "" for m in messages)

    def test_get_messages_returns_list(self, tmp_path):
        builder = PromptBuilder(tmp_path)
        builder.add_stable_system()
        messages = builder.get_messages()
        assert isinstance(messages, list)
        assert len(messages) > 0

    def test_builder_chaining(self, tmp_path):
        builder = PromptBuilder(tmp_path)
        result = (
            builder.add_stable_system()
            .add_safety_summary()
            .add_goal("test", [])
            .add_question("what should I do?")
        )
        assert result is builder


class TestBuildStablePrefix:
    def test_returns_messages_list(self):
        tool_schemas = [
            {"name": "test.tool", "description": "A tool", "mutates": False}
        ]
        role_def = {
            "purpose": "Test",
            "instructions": ["Do something"],
        }
        output_schema = {"type": "object", "properties": {}}
        messages = build_stable_prefix(
            tool_schemas, "planner", role_def, output_schema
        )
        assert isinstance(messages, list)
        assert len(messages) > 0
        assert messages[0]["role"] == "system"
