# Runtime Flow

## Startup Sequence

1. `gm` CLI parses args (`--version`, `--doctor`, `--no-browser`, `--port`, `--project`, `--resume`)
2. `Launcher.run()` loads app config from `~/.config/galaxy-merge/config.json`
3. `detect_workroot(cwd)` scans upward for `.git`, `package.json`, `pyproject.toml`, etc.
4. Self-codebase check: if WorkRoot is inside Galaxy Merge source tree → read-only mode
5. `init_gm_dir(workroot)` creates `.gm/` directory structure (25+ subdirectories, 15+ files)
6. `upgrade_concurrency(gm_dir)` patches shared classes with lock-safe versions
7. `cleanup_stale_sessions(gm_dir)` removes sessions with no heartbeat in 300s
8. `validate_gm_structure(gm_dir)` checks all required dirs/files exist
9. `Session(workroot)` created, state saved, marked running
10. `write_heartbeat()` starts (every 3s in background thread)
11. `start_server(session)` binds a TCP socket, creates FastAPI app, starts Uvicorn
12. `ProviderRegistry` loaded from `config_templates/providers.json` and `models.json`
13. Boot log printed to stderr (version, workroot, session ID, GUI URL, provider stats)
14. Browser opened (unless `--no-browser`)
15. Signal handlers installed (SIGINT, SIGTERM)
16. `server.serve()` blocks until shutdown

## Goal Execution Pipeline

```
User enters goal in GUI
        │
        ▼
POST /api/goal {"goal": "..."}
        │
        ▼
Orchestrator.execute_goal(goal)
        │
        ├─► GoalEngine.parse(goal) → task_type, mentioned_files, scope
        ├─► MemoryRetriever.get_context_for_goal(goal) → notes, memory context
        ├─► WorkspaceIndexer.refresh() → file tree, changed files
        ├─► Planner.create_plan(parsed) → steps, completion_criteria
        ├─► SkillRegistry.search(goal) → matched skills
        │
        ▼
FusionRouter.create_council(task_type, goal)
        │
        ├─► Council.execute() → parallel role execution
        │   ├─► planner role → plan with steps, criteria, risks
        │   ├─► scout role → files found, architecture summary
        │   ├─► implementer role → changes with diffs
        │   ├─► reviewer role → findings, risks, approval
        │   ├─► skeptic role → blockers, missing evidence
        │   └─► cheap_verifier role → syntax check, quick findings
        │
        ▼
Synthesizer.fuse(council_results)
        │
        ├─► Deduplicate findings
        ├─► Score by evidence rank (direct_file_content > test_output > ... > unsupported_assumption)
        ├─► Resolve contradictions
        ├─► Build execution plan
        │
        ▼
Execute plan through ToolKernel
        │
        ├─► For each change: SafetyGovernor.check_path_write() → allow/block
        ├─► Inject expected_hash for conflict detection
        ├─► tool_kernel.execute(tool_name, params) → ToolResult
        │
        ▼
Verification (_verify)
        │
        ├─► Check plan is non-empty
        ├─► Check for fusion/schema errors
        ├─► Python: py_compile check
        ├─► JS/TS: node --check
        │
        ▼
review_fusion_result(fused) → approved/rejected
        │
        ├─► If passed: session.mark_completed(), promote to memory
        └─► If failed: session status = "failed_safe"
```

## Shutdown Sequence

1. Signal received (SIGINT/SIGTERM) or KeyboardInterrupt
2. `_shutdown()` called (idempotent)
3. Heartbeat thread stopped
4. Session state updated:
   - Signal → `mark_stopped("stopped_by_signal")`
   - Exception → `mark_crashed(reason)`
   - Normal → `mark_completed()`
5. Event logged (`session_stopped` / `session_crashed` / `session_completed`)
6. Server socket closed
7. Process exits
