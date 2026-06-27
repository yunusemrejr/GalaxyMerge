from typing import Any

PLANNER_RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "goal_understanding": {"type": "string"},
        "relevant_files": {"type": "array", "items": {"type": "string"}},
        "steps": {"type": "array", "items": {"type": "string"}},
        "completion_criteria": {"type": "array", "items": {"type": "string"}},
        "risks": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["steps", "completion_criteria"],
}

SCOUT_RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "files_found": {"type": "array", "items": {"type": "string"}},
        "architecture_summary": {"type": "string"},
        "uncertainties": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["files_found"],
}

IMPLEMENTATION_RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "changes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "file": {"type": "string"},
                    "action": {"type": "string", "enum": ["edit", "create", "delete"]},
                    "diff": {"type": "string"},
                    "rationale": {"type": "string"},
                },
            },
        },
    },
    "required": ["changes"],
}

REVIEW_RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string"},
                    "file": {"type": "string"},
                    "evidence": {"type": "string"},
                    "severity": {"type": "string"},
                    "recommendation": {"type": "string"},
                },
            },
        },
        "risks": {"type": "array", "items": {"type": "string"}},
        "approved": {"type": "boolean"},
    },
    "required": ["findings", "approved"],
}

SKEPTIC_RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "blockers": {"type": "array", "items": {"type": "string"}},
        "missing_evidence": {"type": "array", "items": {"type": "string"}},
        "completion_claim_valid": {"type": "boolean"},
    },
    "required": ["completion_claim_valid"],
}

CHEAP_VERIFIER_RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string"},
                    "file": {"type": "string"},
                    "evidence": {"type": "string"},
                    "severity": {"type": "string"},
                },
            },
        },
        "syntax_ok": {"type": "boolean"},
        "summary": {"type": "string"},
    },
    "required": ["findings", "syntax_ok"],
}

FUSION_RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "plan": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "tool": {"type": "string"},
                    "params": {"type": "object"},
                    "rationale": {"type": "string"},
                },
            },
        },
        "summary": {"type": "string"},
        "contradictions_resolved": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["plan", "summary"],
}

ROLE_SCHEMAS: dict[str, dict[str, Any]] = {
    "planner": PLANNER_RESULT_SCHEMA,
    "scout": SCOUT_RESULT_SCHEMA,
    "implementer": IMPLEMENTATION_RESULT_SCHEMA,
    "reviewer": REVIEW_RESULT_SCHEMA,
    "cheap_verifier": CHEAP_VERIFIER_RESULT_SCHEMA,
    "skeptic": SKEPTIC_RESULT_SCHEMA,
    "synthesizer": FUSION_RESULT_SCHEMA,
}
