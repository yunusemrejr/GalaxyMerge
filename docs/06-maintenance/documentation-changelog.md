# Documentation Changelog

## 2026-06-29 — Initial Documentation Created

### Files Created
- `docs/README.md` — Documentation index and table of contents
- `docs/00-index.md` — Navigation index for all docs
- `docs/01-project-overview.md` — Project purpose, tech stack, design decisions
- `docs/02-architecture/README.md` — Layer model and key relationships
- `docs/02-architecture/runtime-flow.md` — Startup, goal execution, shutdown sequences
- `docs/02-architecture/module-map.md` — Complete directory and module map
- `docs/02-architecture/dependency-map.md` — External dependencies and their roles
- `docs/02-architecture/data-flow.md` — Goal, event, state, cache, redaction data flows
- `docs/02-architecture/process-lifecycle.md` — Session states, heartbeat, crash recovery
- `docs/03-api-and-interfaces/README.md` — API overview
- `docs/03-api-and-interfaces/cli.md` — CLI commands and flags
- `docs/03-api-and-interfaces/routes.md` — All HTTP API routes
- `docs/03-api-and-interfaces/websocket.md` — WebSocket event streaming
- `docs/03-api-and-interfaces/schemas-and-types.md` — Data types and JSON schemas
- `docs/04-implementation/README.md` — Implementation overview
- `docs/04-implementation/configuration.md` — Config files, env vars, templates
- `docs/04-implementation/persistence-and-state.md` — .gm/ directory structure
- `docs/04-implementation/safety-model.md` — Safety Governor and all policies
- `docs/04-implementation/council-and-fusion.md` — Multi-model council system
- `docs/04-implementation/logging-and-errors.md` — Event logging, error classes
- `docs/04-implementation/security-boundaries.md` — Trust boundaries, secrets handling
- `docs/04-implementation/concurrency.md` — File locking, session isolation
- `docs/05-operations/build-and-run.md` — Install, run, build commands
- `docs/05-operations/testing-and-verification.md` — Test suite, smoke tests, CI
- `docs/05-operations/deployment.md` — Distribution model
- `docs/05-operations/troubleshooting.md` — Common issues and fixes
- `docs/06-maintenance/known-issues.md` — Known bugs and limitations
- `docs/06-maintenance/unfinished-work.md` — Partial implementations
- `docs/06-maintenance/unknowns.md` — Unconfirmed behavior
- `docs/06-maintenance/documentation-changelog.md` — This file

### Source Areas Inspected
- `galaxy_merge/__main__.py` — CLI entry point
- `galaxy_merge/app/launcher.py` — Launcher class, boot sequence
- `galaxy_merge/app/server.py` — FastAPI app, all HTTP/WS routes
- `galaxy_merge/app/lifecycle.py` — Boot log, doctor, provider env vars
- `galaxy_merge/app/ports.py` — Socket reservation, offline ports
- `galaxy_merge/core/session.py` — Session class, WorkRoot detection, .gm/ init
- `galaxy_merge/core/orchestrator.py` — Goal execution pipeline
- `galaxy_merge/core/config.py` — App config, JSON load/save
- `galaxy_merge/core/events.py` — EventLog class
- `galaxy_merge/core/goal.py` — GoalEngine task classification
- `galaxy_merge/core/planner.py` — Planner step generation
- `galaxy_merge/core/locks.py` — LockManager, FileLock, atomic_write/append
- `galaxy_merge/core/concurrency.py` — Monkey-patches for lock-safe access
- `galaxy_merge/core/errors.py` — Exception hierarchy
- `galaxy_merge/core/runtime_models.py` — Pydantic models
- `galaxy_merge/core/prompt_builder.py` — Segment-based prompt assembly
- `galaxy_merge/safety/governor.py` — SafetyGovernor
- `galaxy_merge/safety/path_policy.py` — PathPolicy
- `galaxy_merge/safety/command_policy.py` — CommandPolicy
- `galaxy_merge/providers/registry.py` — ProviderRegistry
- `galaxy_merge/providers/base.py` — ProviderBase ABC
- `galaxy_merge/fusion/council.py` — Council execution
- `galaxy_merge/fusion/router.py` — FusionRouter
- `galaxy_merge/fusion/synthesizer.py` — Synthesizer
- `galaxy_merge/fusion/roles.py` — Role definitions
- `galaxy_merge/fusion/schemas.py` — Role schemas
- `galaxy_merge/tools/kernel.py` — ToolKernel
- `galaxy_merge/tools/schemas.py` — ToolSchema, ToolResult
- `galaxy_merge/memory/store.py` — MemoryStore
- `pyproject.toml` — Dependencies, build config, test config
- `README.md` — Existing project documentation
- `SECURITY.md` — Security policy
- `CONTRIBUTING.md` — Contributing guidelines
- `.github/workflows/ci.yml` — CI pipeline
- `scripts/smoke_test.sh` — E2E smoke test
- `galaxy_merge/gui/static/index.html` — GUI HTML

## 2026-06-29 — Docs-to-Code Fix Pass

### Code Fixes
- `galaxy_merge/core/orchestrator.py` — Removed dead stub methods `_run_planning()` and `_run_scout()` that were never called from any code path
- `galaxy_merge/safety/credential_policy.py` — Removed redundant regex pattern `r"sk-[a-zA-Z0-9]{20,}"` that duplicated the stricter `r"sk-[a-zA-Z0-9]{20,}(?:[^a-zA-Z0-9]|$)"` pattern

### Documentation Corrections
- `docs/06-maintenance/unknowns.md` — Corrected Ollama API endpoint from `/api/generate` to `/api/chat` (verified in `local_ollama.py:34`); marked as Confirmed
- `docs/06-maintenance/known-issues.md` — Corrected "No incremental indexing" claim; `WorkspaceIndexer.incremental_update()` exists and works
- `docs/06-maintenance/unfinished-work.md` — Corrected deployment policy description: implementation is complete (rules-based, default-block), not "basic"
- `docs/06-maintenance/unfinished-work.md` — Corrected git checkpoints: no restore logic exists (was "minimal")
- `docs/06-maintenance/unfinished-work.md` — Clarified token budget: `TokenBudgetManager` is tested but not wired into orchestrator; `PromptAssembly` IS used by council

### Issues Verified as Not Reproducible
- Credential duplicate regex: Both patterns are defense-in-depth; removed the strictly redundant one

### Issues Verified as Intentional Limitations
- Advisory locks (fcntl.flock) Linux/macOS only — by design, platform requirement documented
- Token estimation `len(content) // 4` — rough estimate, adequate for budget decisions
- Binary provider health — sufficient for current fallback logic

## 2026-06-29 — Unit Test Engineering Pass

### New Test Files Added
- `tests/test_goal.py` — GoalEngine: task classification (24 parametrized cases), file extraction, scope estimation, pattern compilation
- `tests/test_planner.py` — Planner: plan generation for all 7 task types, missing keys, file preservation
- `tests/test_git.py` — Checkpoints: save/list/empty/special chars; generate_diff: unified/identical/multiline/unicode; GitRepo: is_repo/status/branch/clean/log
- `tests/test_kernel_extended.py` — ToolKernel: sync/async handlers, safety blocking, exception wrapping, event emission, schema lookup
- `tests/test_workspace_extras.py` — TaskScope: containment with/without plan; FileSummarizer: all 10 file types, import counting, size reporting
- `tests/test_reviewer.py` — FusionReviewer: approval, error rejection, no-plan rejection, contradiction rejection, risk filtering, missing keys
- `tests/test_prompt_builder.py` — PromptBuilder: segment ordering, message assembly, token tracking, chaining, all add_* methods
- `tests/test_mock_provider.py` — MockProvider: responses, failures, call history, role extraction, credential redaction

### Test Count
- Before: 1100 tests
- After: 1255 tests (+155 new)
- All passing

### Documentation Updated
- `docs/05-operations/testing-and-verification.md` — Added new test files to table, test fixtures section, coverage notes, running commands for new tests
