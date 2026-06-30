# Logging and Errors

## Event Logging

`EventLog` (`core/events.py`) writes JSONL to `sessions/<session_id>/events.jsonl`.

### Event Types

| Event | When | Key Fields |
|-------|------|------------|
| `session_started` | Orchestrator initialized | session_id |
| `workroot_detected` | WorkRoot analyzed | session_id, workroot |
| `goal_received` | Goal submitted | session_id, goal |
| `goal_parsed` | Goal classified | session_id, task_type |
| `skill_selected` | Skills matched | session_id, skills[] |
| `council_started` | Council execution begins | session_id, task_type |
| `provider_called` | LLM call made | session_id, role, provider_id, model, attempt |
| `role_fallback` | Provider fallback | session_id, role, from_provider, to_provider |
| `role_execution_failed` | Role failed | session_id, role, error, error_type |
| `council_completed` | Council done | session_id, roles[] |
| `council_quorum_failed` | Quorum not met | session_id, succeeded, required |
| `fusion_started` | Fusion begins | session_id |
| `fusion_completed` | Fusion done | session_id, changes_proposed |
| `tool_call_started` | Tool execution begins | session_id, tool |
| `tool_call_completed` | Tool succeeded | session_id, tool, duration_ms |
| `tool_call_blocked` | Tool blocked by safety | session_id, tool, reason |
| `tool_blocked` | Tool blocked | session_id, tool, reason |
| `tool_failed` | Tool error | session_id, tool, error |
| `verification_started` | Verification begins | session_id |
| `verification_completed` | Verification done | session_id, passed |
| `completion_accepted` | Goal completed | session_id |
| `completion_rejected` | Goal failed | session_id |
| `session_completed` | Session completed | session_id, workroot |
| `session_stopped` | Session stopped | session_id |
| `session_crashed` | Session crashed | session_id, error |
| `note_loaded` | Notes loaded for goal | session_id, notes_count |
| `provider_failed` | Provider marked unhealthy | session_id, provider_id, error, error_type |

## Error Classes (`core/errors.py`)

```
GalaxyMergeError (base)
├── SafetyBlocked(decision)    — safety policy blocked an action
├── ToolError                  — tool execution failure
├── ProviderError              — provider call failure
├── SessionError               — session state error
└── ConfigError                — configuration error
```

## Safety Audit

`SafetyAudit` (`safety/audit.py`) logs blocked actions to `.gm/safety/blocked_actions.jsonl`:
```json
{"time": "...", "action_type": "path_write", "target": "...", "decision": {"decision": "block", "reason": "..."}}
```

## Logging Configuration

- Python `logging` module used with logger name `galaxy_merge.*`
- Server uvicorn log level: `warning`
- No file-based logging config — terminal is the log surface
- Project log file at `.gm/logs/project.log` (if created)
