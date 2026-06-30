from typing import Any


def review_fusion_result(result: dict[str, Any]) -> dict[str, Any]:
    issues = []

    has_plan = bool(result.get("plan"))
    errors = result.get("errors", [])
    has_errors = bool(errors)

    if not has_plan:
        issues.append("No plan produced")

    if errors:
        issues.append(f"Errors present: {len(errors)}")

    contradictions = result.get("contradictions_resolved", [])
    has_contradictions = bool(contradictions)

    if contradictions:
        issues.append(f"Contradictions: {len(contradictions)}")

    high_risk = False
    if result.get("risks"):
        high_risks = [
            r
            for r in result["risks"]
            if "security" in r.lower() or "data loss" in r.lower()
        ]
        if high_risks:
            issues.append(f"High-risk items: {len(high_risks)}")
            high_risk = True

    approved = has_plan and not has_errors and not has_contradictions and not high_risk

    return {
        "approved": approved,
        "issues": issues,
        "degraded": has_errors,
        "changes_proposed": result.get("changes_proposed", 0),
    }
