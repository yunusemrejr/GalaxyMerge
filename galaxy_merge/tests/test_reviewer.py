"""Unit tests for FusionReviewer — review_fusion_result."""

import pytest

from galaxy_merge.fusion.reviewer import review_fusion_result

pytestmark = [pytest.mark.unit]


class TestReviewFusionResult:
    def test_approves_clean_result(self):
        result = {
            "errors": [],
            "contradictions_resolved": [],
            "plan": [{"tool": "file.write", "params": {"path": "a.py"}}],
            "risks": [],
            "changes_proposed": 1,
        }
        review = review_fusion_result(result)
        assert review["approved"] is True
        assert review["issues"] == []

    def test_rejects_when_errors_present(self):
        result = {
            "errors": ["provider timeout"],
            "contradictions_resolved": [],
            "plan": [{"tool": "file.write"}],
            "risks": [],
        }
        review = review_fusion_result(result)
        assert review["approved"] is False
        assert any("Errors present" in i for i in review["issues"])

    def test_rejects_when_no_plan(self):
        result = {
            "errors": [],
            "contradictions_resolved": [],
            "plan": [],
            "risks": [],
        }
        review = review_fusion_result(result)
        assert review["approved"] is False
        assert any("No plan" in i for i in review["issues"])

    def test_rejects_when_contradictions_present(self):
        result = {
            "errors": [],
            "contradictions_resolved": ["conflict A vs B"],
            "plan": [{"tool": "file.write"}],
            "risks": [],
        }
        review = review_fusion_result(result)
        assert review["approved"] is False
        assert any("Contradictions" in i for i in review["issues"])

    def test_rejects_high_risk_security(self):
        result = {
            "errors": [],
            "contradictions_resolved": [],
            "plan": [{"tool": "file.write"}],
            "risks": ["security vulnerability in auth"],
        }
        review = review_fusion_result(result)
        assert review["approved"] is False
        assert any("High-risk" in i for i in review["issues"])

    def test_rejects_high_risk_data(self):
        result = {
            "errors": [],
            "contradictions_resolved": [],
            "plan": [{"tool": "file.write"}],
            "risks": ["data loss possible"],
        }
        review = review_fusion_result(result)
        assert review["approved"] is False

    def test_ignores_low_risks(self):
        result = {
            "errors": [],
            "contradictions_resolved": [],
            "plan": [{"tool": "file.write"}],
            "risks": ["style inconsistency"],
        }
        review = review_fusion_result(result)
        assert review["approved"] is True

    def test_tracks_changes_proposed(self):
        result = {
            "errors": [],
            "contradictions_resolved": [],
            "plan": [{"tool": "file.write"}],
            "risks": [],
            "changes_proposed": 5,
        }
        review = review_fusion_result(result)
        assert review["changes_proposed"] == 5

    def test_handles_missing_keys_gracefully(self):
        result = {}
        review = review_fusion_result(result)
        assert review["approved"] is False
        assert any("No plan" in i for i in review["issues"])

    def test_multiple_issues_accumulate(self):
        result = {
            "errors": ["e1", "e2"],
            "contradictions_resolved": ["c1"],
            "plan": [],
            "risks": ["security risk"],
        }
        review = review_fusion_result(result)
        assert review["approved"] is False
        assert len(review["issues"]) >= 3
