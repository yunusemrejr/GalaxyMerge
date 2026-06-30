# Testing and Verification

## Test Suite

Location: `galaxy_merge/tests/`  
Framework: pytest + pytest-asyncio + pytest-timeout  
Total tests: 1255 (as of 2026-06-29)  
Timeout: 30s per test (thread method)

### Test Categories (markers)

| Marker | Purpose |
|--------|---------|
| `unit` | Pure unit tests, no I/O, no subprocesses, no network |
| `integration` | Backend/tool interactions using TestClient and fakes |
| `e2e` | Full gm smoke flow with isolated temp project |
| `slow` | Long-running tests |
| `browser` | Browser manager / CDP / headless driver tests |
| `network` | Real network endpoints (skipped by default) |
| `provider` | Provider adapters via real HTTP (skipped by default) |
| `github` | GitHub API tests |

### Key Test Files

| File | Covers |
|------|--------|
| `test_gm_structure.py` | .gm/ directory creation and validation |
| `test_config.py` | Config loading and validation |
| `test_safety_governor.py` | Safety Governor path/command/credential checks |
| `test_safety.py` | Safety policy enforcement |
| `test_cache.py` | Cache key generation, TTL expiration |
| `test_concurrency.py` | File locking, conflict detection |
| `test_fusion.py` | Fusion/synthesizer logic |
| `test_fusion_council.py` | Council execution with mocks |
| `test_memory.py` | Memory store CRUD |
| `test_notes_persistence.py` | Notes CRUD with index |
| `test_ports.py` | Port reservation |
| `test_browser.py` | Browser manager |
| `test_tools.py` | Tool kernel execution |
| `test_kernel_extended.py` | ToolKernel: safety gating, async/sync handlers, error wrapping, event emission |
| `test_web.py` | Web search/fetch |
| `test_workspace.py` | Workspace indexer |
| `test_workspace_extras.py` | TaskScope containment, FileSummarizer type detection |
| `test_goal.py` | GoalEngine: task classification, file extraction, scope estimation |
| `test_planner.py` | Planner: plan generation by task type |
| `test_git.py` | Git subsystem: Checkpoints, generate_diff, GitRepo |
| `test_reviewer.py` | FusionReviewer: approval/rejection logic |
| `test_prompt_builder.py` | PromptBuilder: segment ordering, message assembly, token tracking |
| `test_mock_provider.py` | MockProvider: deterministic test infrastructure |
| `test_integration.py` | Backend integration |
| `test_server_asgi.py` | ASGI server tests |
| `test_token_economy.py` | Token budget |
| `test_gui_js_syntax.py` | JavaScript syntax validation |
| `test_provider_config.py` | Provider config validation |
| `test_provider_env_safety.py` | Provider env var safety |
| `test_public_repo_safety.py` | Public repo hygiene |
| `test_redteam_safety.py` | Red-team safety tests |
| `test_opencode_import.py` | OpenCode import |
| `test_locations.py` | Location classification |
| `test_github.py` | GitHub scanner |
| `test_install_flow.py` | Install script |
| `test_audit_regressions.py` | Audit regression tests |
| `test_degraded_fusion_metadata.py` | Degraded fusion handling |

### Test Configuration

From `pyproject.toml`:
```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["galaxy_merge/tests"]
timeout = 30
timeout_method = "thread"
```

### Test Fixtures

Shared fixtures in `conftest.py` and `fixtures/fakes.py`:
- `FakeProvider` — deterministic provider with canned responses
- `FakeProviderRegistry` — in-memory provider registry
- `FakeBrowserManager` — browser manager that never launches a real browser
- `FakeEventBus` — in-memory event bus
- `FakeClock` — deterministic clock
- `make_fake_project()` — creates minimal project directory
- `make_fake_gm_dir()` — creates minimal .gm directory structure
- `make_fake_config()` — creates config directory with providers/models/fusion
- `temp_env()` — context manager for temporary environment variables

## Running Tests

```bash
# Full suite (all 1255 tests, ~21s)
uv run pytest

# Specific test file
uv run pytest galaxy_merge/tests/test_safety_governor.py -v

# Unit tests only
uv run pytest -m unit -v

# Run new tests added in this pass
uv run pytest galaxy_merge/tests/test_goal.py galaxy_merge/tests/test_planner.py galaxy_merge/tests/test_git.py galaxy_merge/tests/test_reviewer.py galaxy_merge/tests/test_workspace_extras.py galaxy_merge/tests/test_kernel_extended.py galaxy_merge/tests/test_prompt_builder.py galaxy_merge/tests/test_mock_provider.py -v

# Exclude slow/integration tests
uv run pytest --ignore=galaxy_merge/tests/test_backend_runtime.py --ignore=galaxy_merge/tests/test_redteam_v3_comprehensive.py

# Run with duration reporting
uv run pytest --durations=20
```

## Smoke Test

`scripts/smoke_test.sh` — full end-to-end lifecycle:
1. Creates temp project with git init
2. Tests WorkRoot detection
3. Tests CLI (--version, --doctor)
4. Starts server, captures API base
5. Verifies all API endpoints (/api/session, /api/project, /api/tree, /api/safety, /api/tools, /api/events, /api/file, /api/council, /api/locations, /api/notes)
6. Submits a goal
7. Verifies session state files
8. Verifies GUI serves HTML
9. Clean shutdown
10. Crash recovery test
11. .gm/ structure verification

## CI Pipeline

`.github/workflows/ci.yml`:
1. Unit tests (excluding slow/integration/redteam suites)
2. JS syntax check (`node --check` on all GUI JS files)
3. Smoke test
4. Secret scan (with history)
5. Repo hygiene (.gm/ and .env not tracked, config examples clean)

## Coverage Notes

Coverage was not measured (no pytest-cov configured). Based on module analysis:

| Directory | Source files | Files with tests | Coverage |
|-----------|-------------|-----------------|----------|
| core/ | 12 | 10 | 83% |
| safety/ | 10 | 9 | 90% |
| fusion/ | 7 | 7 | 100% |
| tools/ | 18 | 11 | 61% |
| providers/ | 5 | 3 | 60% |
| memory/ | 5 | 4 | 80% |
| workspace/ | 7 | 5 | 71% |
| git/ | 3 | 3 | 100% |
| token/ | 2 | 2 | 100% |
| cache/ | 5 | 2 | 40% |

### Important Gaps Remaining

- `core/orchestrator.py` — 440 lines of orchestration logic, tested only indirectly
- `providers/openai_compat.py` — real provider implementation, no unit tests
- `app/notes_api.py` — HTTP route handlers, tested only via integration
- `browser/cdp.py` — CDP protocol handling, tested only via collectors
- `cache/` thin wrappers — low priority, simple delegation
