from typing import Any


def review_fusion_result(result: dict[str, Any]) -> dict[str, Any]:
    issues = []

    if result.get("errors"):
        issues.append(f"Errors present: {len(result['errors'])}")

    if result.get("contradictions_resolved"):
        issues.append(f"Contradictions: {len(result['contradictions_resolved'])}")

    if not result.get("plan"):
        issues.append("No plan produced")

    if result.get("risks"):
        high_risks = [r for r in result["risks"] if "security" in r.lower() or "data" in r.lower()]
        if high_risks:
            issues.append(f"High-risk items: {len(high_risks)}")

    return {
        "approved": len(issues) == 0,
        "issues": issues,
        "changes_proposed": result.get("changes_proposed", 0),
    }
