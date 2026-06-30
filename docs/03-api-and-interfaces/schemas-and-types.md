# Schemas and Types

## Pydantic Models (`core/runtime_models.py`)

### SessionState
```python
session_id: str
workroot: str
created_at: datetime
updated_at: datetime
status: str = "running"
goal: str = ""
active: bool = True
error: str | None = None
crash_count: int = 0
```

### GoalState
```python
goal_id: str
session_id: str
text: str
parsed: dict | None = None
status: Literal["queued", "understanding", "planning", "executing", "testing", "complete", "failed"]
created_at: datetime
updated_at: datetime
```

### ToolCall
```python
call_id: str
session_id: str
tool: str
params: dict
status: Literal["requested", "running", "success", "blocked", "failed"]
started_at: datetime | None
finished_at: datetime | None
error: str | None
duration_ms: int | None
```

### SafetyDecision
```python
decision: Literal["allow", "block", "warn"]
action: str
reason: str
path: str | None
```

### LocationClassification
```python
target: str
classification: str  # "workroot", "galaxy_merge_app_codebase", "system", "user_home"
risk: Literal["low", "medium", "high"]
policy_decision: str
```

## Tool Types (`tools/schemas.py`)

### ToolSchema
```python
name: str
description: str
mutates: bool = False
requires_safety: bool = True
parameters: dict = {}
```

### ToolResult
```python
success: bool
data: Any = None
error: str | None = None
blocked: bool = False
```

## Fusion Schemas (`fusion/schemas.py`)

Each council role has a JSON Schema for output validation:

- **planner**: `goal_understanding`, `relevant_files[]`, `steps[]`, `completion_criteria[]`, `risks[]`
- **scout**: `files_found[]`, `architecture_summary`, `uncertainties[]`
- **implementer**: `changes[{file, action, diff, rationale}]`
- **reviewer**: `findings[{type, file, evidence, severity, recommendation}]`, `risks[]`, `approved`
- **skeptic**: `blockers[]`, `missing_evidence[]`, `completion_claim_valid`
- **cheap_verifier**: `findings[{type, file, evidence, severity}]`, `syntax_ok`, `summary`
- **synthesizer**: `plan[{tool, params, rationale}]`, `summary`, `contradictions_resolved[]`

## Evidence Ranking

From `fusion/synthesizer.py`:
```python
EVIDENCE_RANKING = [
    "direct_file_content",   # confidence: 0.9
    "test_output",           # confidence: 0.8
    "build_output",          # confidence: 0.8
    "git_diff",              # confidence: 0.8
    "tool_logs",             # confidence: 0.9
    "multiple_model_findings", # confidence: 0.7
    "single_model_claim",    # confidence: 0.4
    "unsupported_assumption" # confidence: 0.3
]
```
