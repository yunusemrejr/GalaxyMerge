

import pytest

pytestmark = [pytest.mark.unit]

from galaxy_merge.fusion.synthesizer import Synthesizer
from galaxy_merge.fusion.scoring import score_finding, rank_findings, has_high_severity_blockers
from galaxy_merge.fusion.reviewer import review_fusion_result
from galaxy_merge.core.goal import GoalEngine


class TestSynthesizer:
    def test_fuse_empty(self):
        syn = Synthesizer()
        result = syn.fuse({})
        assert result["changes_proposed"] == 0
        assert result["plan"] == []

    def test_fuse_with_implementer(self):
        syn = Synthesizer()
        results = {
            "implementer": [{
                "role": "implementer",
                "parsed": {
                    "changes": [
                        {"file": "src/main.py", "action": "edit", "diff": "- old\n+ new", "rationale": "fix bug"}
                    ]
                }
            }]
        }
        result = syn.fuse(results)
        assert result["changes_proposed"] == 1
        assert len(result["plan"]) == 1

    def test_deduplicate(self):
        syn = Synthesizer()
        findings = [
            {"evidence": "same", "source": "reviewer"},
            {"evidence": "same", "source": "planner"},
            {"evidence": "different", "source": "reviewer"},
        ]
        deduped = syn._deduplicate(findings)
        assert len(deduped) == 2


class TestScoring:
    def test_score_finding(self):
        high = score_finding({"evidence": "direct file content", "source": "reviewer"})
        low = score_finding({"source": "planner"})
        assert high > low

    def test_rank_findings(self):
        findings = [
            {"evidence": "direct", "source": "reviewer"},
            {"source": "planner"},
        ]
        ranked = rank_findings(findings)
        assert ranked[0]["source"] == "reviewer"

    def test_high_severity_blockers(self):
        findings = [{"type": "bug", "severity": "high"}]
        assert has_high_severity_blockers(findings) is True


class TestReviewer:
    def test_approve_clean_result(self):
        result = {
            "errors": [],
            "contradictions_resolved": [],
            "plan": [{"tool": "file.write"}],
            "risks": [],
            "changes_proposed": 1,
        }
        review = review_fusion_result(result)
        assert review["approved"] is True

    def test_reject_with_errors(self):
        result = {
            "errors": ["provider failed"],
            "contradictions_resolved": [],
            "plan": [],
            "risks": [],
            "changes_proposed": 0,
        }
        review = review_fusion_result(result)
        assert review["approved"] is False


class TestGoalEngine:
    def test_parse_bug_fix(self):
        engine = GoalEngine()
        result = engine.parse("fix the login crash")
        assert result["task_type"] == "bug_fix"

    def test_parse_feature(self):
        engine = GoalEngine()
        result = engine.parse("add a new user dashboard")
        assert result["task_type"] == "feature"

    def test_parse_small_edit(self):
        engine = GoalEngine()
        result = engine.parse("update the readme")
        assert result["task_type"] == "small_edit"

    def test_parse_refactor(self):
        engine = GoalEngine()
        result = engine.parse("refactor the auth module")
        assert result["task_type"] == "large_refactor"
