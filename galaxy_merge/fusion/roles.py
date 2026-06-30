from typing import Any

ROLE_DEFINITIONS: dict[str, dict[str, Any]] = {
    "cheap_verifier": {
        "purpose": "Quickly verify syntax and basic correctness",
        "output_schema": "cheap_verifier_result",
        "instructions": [
            "Check syntax of changed files.",
            "Look for obvious errors.",
            "Provide brief summary.",
            "Do not deep-dive — keep it fast.",
            "MUST return a JSON object with 'findings' (array of objects) and 'syntax_ok' (boolean) — both are required.",
        ],
    },
    "planner": {
        "purpose": "Create a minimal safe execution plan",
        "output_schema": "planner_result",
        "instructions": [
            "Identify relevant files.",
            "Define completion criteria.",
            "Avoid overengineering.",
            "Prefer minimal reversible changes.",
        ],
    },
    "scout": {
        "purpose": "Inspect workspace evidence quickly",
        "output_schema": "scout_result",
        "instructions": [
            "Find relevant files and symbols.",
            "Summarize architecture.",
            "Report uncertainty.",
            "MUST return a JSON object with 'files_found' (array of file path strings) — this field is required.",
        ],
    },
    "implementer": {
        "purpose": "Produce patch candidates",
        "output_schema": "implementation_result",
        "instructions": [
            "Use minimal changes.",
            "Do not rewrite unrelated code.",
            "Include patch rationale.",
        ],
    },
    "reviewer": {
        "purpose": "Find bugs and risks in the proposed change",
        "output_schema": "review_result",
        "instructions": [
            "Look for regressions.",
            "Check edge cases.",
            "Challenge assumptions.",
            "MUST return a JSON object with 'findings' (array of finding objects) and 'approved' (boolean) — both are required.",
        ],
    },
    "skeptic": {
        "purpose": "Argue why the goal may not be complete",
        "output_schema": "skeptic_result",
        "instructions": [
            "Find remaining blockers.",
            "Inspect verification evidence.",
            "Reject weak completion claims.",
        ],
    },
    "synthesizer": {
        "purpose": "Fuse council outputs into one coherent action",
        "output_schema": "fusion_result",
        "instructions": [
            "Extract useful parts from all roles.",
            "Resolve contradictions.",
            "Prefer evidence-backed claims.",
            "Produce final plan or patch decision.",
        ],
    },
}
