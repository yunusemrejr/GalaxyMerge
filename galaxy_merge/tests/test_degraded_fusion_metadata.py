from galaxy_merge.fusion.synthesizer import Synthesizer


def test_fusion_reports_full_confidence_when_all_required_perspectives_succeed() -> None:
    # Given: every core council perspective returns a valid parsed result.
    results = {
        "planner": [{"parsed": {"steps": ["inspect"], "completion_criteria": ["tests pass"]}}],
        "implementer": [{"parsed": {"changes": [{"file": "app.py", "diff": "print('ok')"}]}}],
        "reviewer": [{"parsed": {
            "findings": [{"type": "note", "evidence": "test_output"}],
            "risks": [],
            "approved": True,
        }}],
        "skeptic": [{"parsed": {"completion_claim_valid": True}}],
    }

    # When: the fusion result is synthesized.
    fused = Synthesizer().fuse(results)

    # Then: no degradation metadata is reported.
    assert fused["completion_confidence"] == 1.0
    assert fused["missing_perspectives"] == []


def test_fusion_reduces_confidence_and_marks_missing_perspectives_when_roles_fail() -> None:
    # Given: reviewer and skeptic fail while other roles still produce usable data.
    results = {
        "planner": [{"parsed": {"steps": ["inspect"], "completion_criteria": ["tests pass"]}}],
        "implementer": [{"parsed": {"changes": [{"file": "app.py", "diff": "print('ok')"}]}}],
        "reviewer": [{"error": "provider failed: HTTP 500"}],
        "skeptic": [{"error": "provider failed: all providers unhealthy"}],
    }

    # When: fusion continues in degraded mode.
    fused = Synthesizer().fuse(results)

    # Then: confidence is reduced and the missing perspectives are explicit.
    assert fused["completion_confidence"] < 1.0
    assert fused["completion_confidence"] <= 0.5
    assert fused["council_degraded"] is True
    assert fused["missing_perspectives"] == ["reviewer", "skeptic"]
    assert "Missing perspectives: reviewer, skeptic" in fused["summary"]
