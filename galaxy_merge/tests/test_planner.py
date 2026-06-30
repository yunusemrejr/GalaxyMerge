"""Unit tests for Planner — plan generation by task type."""

import pytest

from galaxy_merge.core.planner import Planner

pytestmark = [pytest.mark.unit]


class TestPlanner:
    def setup_method(self):
        self.planner = Planner()

    def test_returns_required_keys(self):
        plan = self.planner.create_plan({"task_type": "small_edit", "goal": "fix it"})
        assert "goal" in plan
        assert "task_type" in plan
        assert "steps" in plan
        assert "relevant_files" in plan
        assert "completion_criteria" in plan

    @pytest.mark.parametrize(
        "task_type,min_steps,min_criteria",
        [
            ("bug_fix", 4, 2),
            ("feature", 5, 2),
            ("large_refactor", 4, 2),
            ("small_edit", 3, 1),
            ("testing", 3, 1),
            ("documentation", 3, 1),
            ("configuration", 3, 1),
        ],
    )
    def test_plan_has_steps_and_criteria(self, task_type, min_steps, min_criteria):
        plan = self.planner.create_plan({"task_type": task_type, "goal": "test"})
        assert len(plan["steps"]) >= min_steps
        assert len(plan["completion_criteria"]) >= min_criteria

    def test_bug_fix_plan(self):
        plan = self.planner.create_plan(
            {"task_type": "bug_fix", "goal": "fix login bug"}
        )
        assert any("fix" in s.lower() for s in plan["steps"])
        assert any("test" in c.lower() for c in plan["completion_criteria"])

    def test_feature_plan(self):
        plan = self.planner.create_plan(
            {"task_type": "feature", "goal": "add dashboard"}
        )
        assert any("implement" in s.lower() for s in plan["steps"])
        assert any("test" in c.lower() for c in plan["completion_criteria"])

    def test_refactor_plan(self):
        plan = self.planner.create_plan(
            {"task_type": "large_refactor", "goal": "refactor auth"}
        )
        assert any("architecture" in s.lower() for s in plan["steps"])
        assert any("regression" in c.lower() or "pass" in c.lower() for c in plan["completion_criteria"])

    def test_unknown_type_gets_default_plan(self):
        plan = self.planner.create_plan(
            {"task_type": "unknown_type", "goal": "do something"}
        )
        assert len(plan["steps"]) >= 1
        assert plan["task_type"] == "unknown_type"

    def test_preserves_relevant_files(self):
        plan = self.planner.create_plan(
            {
                "task_type": "bug_fix",
                "goal": "fix it",
                "mentioned_files": ["src/auth.py", "tests/test_auth.py"],
            }
        )
        assert "src/auth.py" in plan["relevant_files"]
        assert "tests/test_auth.py" in plan["relevant_files"]

    def test_preserves_goal_text(self):
        plan = self.planner.create_plan(
            {"task_type": "small_edit", "goal": "update the header color"}
        )
        assert plan["goal"] == "update the header color"

    def test_missing_task_type_defaults_to_small_edit(self):
        plan = self.planner.create_plan({"goal": "do stuff"})
        assert plan["task_type"] == "small_edit"
        assert len(plan["steps"]) >= 1
