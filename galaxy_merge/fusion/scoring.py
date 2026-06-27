from typing import Any


def score_finding(finding: dict[str, Any]) -> float:
    evidence = finding.get("evidence", "")
    source = finding.get("source", "")

    if evidence and source == "reviewer":
        return 0.9
    if evidence:
        return 0.8
    if source == "planner":
        return 0.6
    return 0.3


def rank_findings(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(findings, key=score_finding, reverse=True)


def has_high_severity_blockers(findings: list[dict[str, Any]]) -> bool:
    for f in findings:
        if f.get("severity") == "high" and f.get("type") == "bug":
            return True
    return False
