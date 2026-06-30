# Module Map

## Top-Level Structure

```
galaxy_merge/
├── __init__.py              # Empty package init
├── __main__.py              # CLI entry point (gm command)
├── app/                     # Application layer (launcher, server, lifecycle)
├── browser/                 # Browser automation (CDP, screenshots, logs)
├── cache/                   # Caching subsystem (file, fusion, provider)
├── config_templates/        # Default config files (providers, models, fusion, routing, safety)
├── core/                    # Core runtime (session, config, events, orchestrator, locks)
├── fusion/                  # Multi-model council system (council, router, synthesizer, roles)
├── git/                     # Git operations (checkpoints, diffs, repo)
├── github/                  # GitHub API integration (scanner)
├── gui/                     # Browser GUI (static HTML/CSS/JS)
├── locations/               # Location classification and deployment policy
├── memory/                  # Memory subsystem (store, project, session, retrieval, compaction)
├── providers/               # LLM provider adapters (registry, base, openai_compat, ollama, mock)
├── safety/                  # Safety enforcement (governor, path, command, credential, self-protection)
├── skills/                  # Skill discovery and matching
├── tests/                   # Test suite
├── token/                   # Token budget management
├── tools/                   # Native tool kernel and all tool implementations
├── web/                     # Web search and fetch (DuckDuckGo, Wikipedia, search, fetch)
└── workspace/               # Workspace intelligence (indexer, tree, symbols, scope, summaries)
```

## Module Details

### `app/` — Application Layer
| File | Purpose |
|------|---------|
| `launcher.py` | `Launcher` class: boot sequence, signal handling, heartbeat, shutdown |
| `server.py` | `SessionServer` class: FastAPI app, all HTTP routes, WebSocket gateway |
| `lifecycle.py` | Boot log, doctor diagnostics, provider env var checking |
| `ports.py` | Socket reservation, offline port allocation (for tests) |
| `payloads.py` | Response builders for locations, logs, notes, council, tree |
| `notes_api.py` | Notes CRUD route registration |
| `council_api.py` | Council status route registration |
| `browser.py` | Browser open helper |

### `core/` — Core Runtime
| File | Purpose |
|------|---------|
| `session.py` | `Session` class, WorkRoot detection, `.gm/` init, structure validation |
| `orchestrator.py` | `Orchestrator` class: full goal execution pipeline |
| `config.py` | `AppConfig`, JSON load/save, config hash |
| `events.py` | `EventLog` class: JSONL event emission and replay |
| `goal.py` | `GoalEngine`: regex-based task type classification |
| `planner.py` | `Planner`: generates step plans per task type |
| `locks.py` | `LockManager`, `FileLock`, `atomic_write`, `atomic_append` |
| `concurrency.py` | Monkey-patches for lock-safe shared state access |
| `errors.py` | Exception hierarchy (GalaxyMergeError, SafetyBlocked, ToolError, etc.) |
| `runtime_models.py` | Pydantic models (SessionState, GoalState, ToolCall, etc.) |
| `prompt_builder.py` | Segment-based prompt assembly for cache efficiency |
| `opencode_import.py` | Import provider metadata from OpenCode exports |

### `safety/` — Safety Enforcement
| File | Purpose |
|------|---------|
| `governor.py` | `SafetyGovernor`: composes all policies, central safety check |
| `path_policy.py` | `PathPolicy`: blocks system paths, user credential paths, symlink escapes |
| `command_policy.py` | `CommandPolicy`: blocks dangerous commands, sudo, rm -rf, curl\|sh, env injection |
| `credential_policy.py` | `CredentialPolicy`: scans text for API keys, tokens, credentials |
| `self_protection.py` | `SelfProtectionPolicy`: read-only mode when inside Galaxy Merge codebase |
| `audit.py` | `SafetyAudit`: JSONL audit log for blocked actions |
| `sandbox.py` | `Sandbox`: command execution sandbox |
| `command_inspector.py` | Remote mutation detection, protected redirect detection |
| `path_utils.py` | `is_relative_to`, `resolve_inside` helpers |

### `providers/` — LLM Provider Adapters
| File | Purpose |
|------|---------|
| `registry.py` | `ProviderRegistry`: loads config, selects models, marks unhealthy |
| `base.py` | `ProviderBase` ABC: chat_completion, check_health, availability |
| `openai_compat.py` | `OpenAICompatibleProvider`: httpx-based OpenAI-compatible API client |
| `local_ollama.py` | `OllamaProvider`: local Ollama API client |
| `mock.py` | `MockProvider`: returns canned responses for testing |

### `fusion/` — Council & Fusion System
| File | Purpose |
|------|---------|
| `council.py` | `Council`: parallel role execution with retry, fallback, quorum |
| `router.py` | `FusionRouter`: selects council config based on task type |
| `synthesizer.py` | `Synthesizer`: fuses council outputs by evidence ranking |
| `roles.py` | `ROLE_DEFINITIONS`: purpose and instructions per role |
| `schemas.py` | `ROLE_SCHEMAS`: JSON schemas for each role's output |
| `scoring.py` | Model scoring helpers |
| `reviewer.py` | `review_fusion_result`: post-fusion approval check |

### `tools/` — Native Tool Kernel
| File | Purpose |
|------|---------|
| `kernel.py` | `ToolKernel`: tool registration, safety-gated execution |
| `schemas.py` | `ToolSchema`, `ToolResult` data classes |
| `file_tools.py` | file.read, file.write, file.patch, file.delete |
| `shell_tools.py` | shell.run (with safety/sandbox enforcement) |
| `git_tools.py` | git.status, git.diff, git.commit, git.checkpoint |
| `memory_tools.py` | memory.read, memory.write, memory.search |
| `notes_tools.py` | notes.create, notes.read, notes.update, notes.delete |
| `skill_tools.py` | skill.search, skill.list |
| `index_tools.py` | index.refresh, index.search |
| `verification_tools.py` | verify.syntax, verify.build |
| `web_tools.py` | web.search, web.fetch |
| `github_tools.py` | github.scan_repo |
| `location_tools.py` | location.classify |
| `security_tools.py` | secret.scan |
| `browser_tools.py` | browser.open, browser.screenshot |
| `provider_tools.py` | provider.status |
| `council_tools.py` | council.status, council.execute |
| `completion_tools.py` | completion.verify |

### `memory/` — Memory Subsystem
| File | Purpose |
|------|---------|
| `store.py` | `MemoryStore`: JSONL append/read with file locking |
| `project_memory.py` | `ProjectMemory`: facts, failures, fixes, lessons |
| `session_memory.py` | `SessionMemory`: per-session transcript entries |
| `retrieval.py` | `MemoryRetriever`: context assembly for goals |
| `compaction.py` | `Compactor`: compresses old memory entries |

### `workspace/` — Workspace Intelligence
| File | Purpose |
|------|---------|
| `indexer.py` | `WorkspaceIndexer`: file hash tracking, incremental updates |
| `tree.py` | `FileTree`: builds directory tree representation |
| `symbols.py` | Symbol extraction |
| `root.py` | `analyze_workroot`: detects language, framework, git status |
| `scope.py` | Scope estimation |
| `summaries.py` | File summary generation |
| `ignore.py` | .gitignore-aware file filtering |
