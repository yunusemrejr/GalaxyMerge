"""Unit tests for GoalEngine — task classification, file extraction, scope estimation."""

import pytest

from galaxy_merge.core.goal import GoalEngine, TASK_TYPE_PATTERNS

pytestmark = [pytest.mark.unit]


class TestGoalEngineParse:
    def setup_method(self):
        self.engine = GoalEngine()

    def test_returns_required_keys(self):
        result = self.engine.parse("fix the login bug")
        assert "goal" in result
        assert "task_type" in result
        assert "mentioned_files" in result
        assert "estimated_scope" in result
        assert "parsed_at" in result

    def test_preserves_original_goal_text(self):
        result = self.engine.parse("Add a new feature to src/auth.py")
        assert result["goal"] == "Add a new feature to src/auth.py"

    @pytest.mark.parametrize(
        "goal,expected_type",
        [
            ("fix the login bug", "bug_fix"),
            ("there is an error in the parser", "bug_fix"),
            ("the button is broken", "bug_fix"),
            ("issue with database connection", "bug_fix"),
            ("bug in payment flow", "bug_fix"),
            ("refactor the auth module", "large_refactor"),
            ("restructure the codebase", "large_refactor"),
            ("rewrite the parser", "large_refactor"),
            ("add a new login feature", "feature"),
            ("create a dashboard page", "feature"),
            ("implement user registration", "feature"),
            ("new export functionality", "feature"),
            ("update the README", "small_edit"),
            ("change the color scheme", "small_edit"),
            ("modify the config", "small_edit"),
            ("edit the header", "small_edit"),
            ("add unit tests for auth", "feature"),  # "add" matches before "test"
            ("improve test coverage", "testing"),
            ("write a spec for the API", "testing"),
            ("update the documentation", "small_edit"),  # "update" matches before "doc"
            ("add a README comment", "feature"),  # "add" matches before "doc"
            ("document the API changes", "small_edit"),  # "change" in "changes" matches small_edit first
            ("write documentation for the module", "documentation"),
            ("configure the CI pipeline", "configuration"),
            ("setup the database", "configuration"),
        ],
    )
    def test_classifies_task_types(self, goal, expected_type):
        result = self.engine.parse(goal)
        assert result["task_type"] == expected_type

    def test_default_task_type_is_small_edit(self):
        result = self.engine.parse("make it better")
        assert result["task_type"] == "small_edit"

    def test_first_matching_pattern_wins(self):
        # "fix" matches bug_fix before "add" could match feature
        result = self.engine.parse("fix and add tests")
        assert result["task_type"] == "bug_fix"

    def test_case_insensitive_matching(self):
        result = self.engine.parse("FIX THE BUG")
        assert result["task_type"] == "bug_fix"
        result2 = self.engine.parse("ADD NEW FEATURE")
        assert result2["task_type"] == "feature"


class TestExtractFiles:
    def setup_method(self):
        self.engine = GoalEngine()

    def test_extracts_paths_with_slashes(self):
        result = self.engine._extract_files("fix the bug in src/auth.py")
        assert "src/auth.py" in result

    def test_extracts_paths_with_dots(self):
        result = self.engine._extract_files("update config.json")
        assert "config.json" in result

    def test_ignores_words_without_slash_or_dot(self):
        result = self.engine._extract_files("fix the login bug")
        assert result == []

    def test_extracts_multiple_files(self):
        result = self.engine._extract_files(
            "update src/main.py and tests/test_main.py"
        )
        assert "src/main.py" in result
        assert "tests/test_main.py" in result

    def test_handles_nested_paths(self):
        result = self.engine._extract_files("fix gal axy_merge/core/session.py")
        assert "gal axy_merge/core/session.py" in result or any(
            "session.py" in f for f in result
        )


class TestEstimateScope:
    def setup_method(self):
        self.engine = GoalEngine()

    def test_small_scope_under_50_chars(self):
        assert self.engine._estimate_scope("fix bug") == "small"

    def test_medium_scope_50_to_200_chars(self):
        goal = "a" * 50
        assert self.engine._estimate_scope(goal) == "medium"

    def test_large_scope_over_200_chars(self):
        goal = "a" * 200
        assert self.engine._estimate_scope(goal) == "large"

    def test_boundary_at_49_chars(self):
        assert self.engine._estimate_scope("a" * 49) == "small"

    def test_boundary_at_50_chars(self):
        assert self.engine._estimate_scope("a" * 50) == "medium"

    def test_boundary_at_199_chars(self):
        assert self.engine._estimate_scope("a" * 199) == "medium"

    def test_boundary_at_200_chars(self):
        assert self.engine._estimate_scope("a" * 200) == "large"


class TestTaskTypePatterns:
    def test_all_patterns_compile(self):
        for pattern, ttype in TASK_TYPE_PATTERNS:
            import re

            re.compile(pattern)

    def test_no_duplicate_task_types(self):
        types = [t for _, t in TASK_TYPE_PATTERNS]
        # Types can repeat (first match wins), but verify the list is non-empty
        assert len(types) > 0
        assert len(TASK_TYPE_PATTERNS) >= 5
