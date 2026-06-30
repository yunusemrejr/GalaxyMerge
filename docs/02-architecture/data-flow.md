# Data Flow

## Goal Execution Data Flow

```
User Input (browser GUI)
    │
    ▼
POST /api/goal {"goal": "fix the login bug"}
    │
    ▼
GoalEngine.parse(goal)
    ├─► task_type: "bug_fix"
    ├─► mentioned_files: ["src/auth.py"]
    └─► estimated_scope: "small"
    │
    ▼
MemoryRetriever.get_context_for_goal(goal)
    ├─► notes: from .gm/notes/index.json
    ├─► project_memory: from .gm/memory/*.jsonl
    └─► session_memory: from session transcript
    │
    ▼
FusionRouter.create_council("bug_fix", goal)
    ├─► Selects council config from fusion.json based on routing.json rules
    └─► Creates Council with provider registry
    │
    ▼
Council.execute() — parallel async LLM calls
    ├─► planner: {steps, completion_criteria, risks}
    ├─► scout: {files_found, architecture_summary}
    ├─► implementer: {changes: [{file, action, diff}]}
    ├─► reviewer: {findings, risks, approved}
    └─► skeptic: {blockers, completion_claim_valid}
    │
    ▼
Synthesizer.fuse(council_results)
    ├─► Deduplicates findings
    ├─► Scores by evidence rank
    ├─► Resolves contradictions
    └─► Builds execution plan: [{tool, params, rationale}]
    │
    ▼
ToolKernel.execute(plan)
    ├─► SafetyGovernor.check_path_write(path) → allow/block
    ├─► hash-based conflict detection (expected_hash injection)
    └─► Tool handler executes (file.write, shell.run, etc.)
    │
    ▼
Verification
    ├─► py_compile / node --check for syntax
    └─► Checks plan non-empty, no fusion errors
    │
    ▼
review_fusion_result(fused) → approved: bool
    │
    ▼
Session state → "complete" or "failed_safe"
```

## Event Data Flow

All system events flow through `EventLog.emit()` → JSONL append to:
- `sessions/<session_id>/events.jsonl` (per-session)

Events are broadcast to WebSocket clients in real-time and queryable via `GET /api/events`.

## State Data Flow

```
Session state
    ├─► .gm/sessions/<id>/state.json        (session status, goal, timestamps)
    ├─► .gm/sessions/<id>/goal.json          (parsed goal data)
    ├─► .gm/sessions/<id>/events.jsonl       (all events)
    ├─► .gm/sessions/<id>/transcript.jsonl   (session memory entries)
    ├─► .gm/sessions/<id>/council.jsonl      (council execution logs)
    ├─► .gm/sessions/<id>/tool_calls.jsonl   (tool call records)
    ├─► .gm/sessions/<id>/safety.jsonl       (safety decisions)
    └─► .gm/sessions/<id>/final.md           (completion summary)

Project state
    ├─► .gm/project.json                     (project identity, config)
    ├─► .gm/notes/index.json                 (notes index)
    ├─► .gm/memory/*.jsonl                   (facts, failures, fixes, lessons)
    ├─► .gm/sessions/registry.jsonl          (session registry)
    └─► .gm/sessions/ports.json              (session→port mapping)
```

## Cache Data Flow

Cache entries are stored as JSON files in `.gm/cache/` subdirectories:
- `provider/` — provider response cache
- `fusion/` — fusion result cache
- `file_summaries/` — file summary cache
- `skill_matches/` — skill match cache
- `command_results/` — command result cache
- `web_search/` — web search cache
- `browser_pages/` — browser page cache
- `github_scans/` — GitHub scan cache

Each cache entry includes `_expires` (unix timestamp) and `_created` fields for TTL enforcement.

## Redaction Data Flow

All outputs (API responses, event logs, error messages) pass through `CredentialPolicy.redact()` which scans for:
- API key patterns (sk-*, sk-ant-*, ghp_*, etc.)
- Bearer tokens
- Base64-encoded credentials
- Environment variable values from known secret vars

Redaction happens at:
- Event log emission
- API response serialization (`_redact_nested`)
- Provider error messages
- Tool result data
