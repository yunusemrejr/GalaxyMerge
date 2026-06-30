# Architecture Overview

## Layer Model

Galaxy Merge is organized into nine cooperating layers:

```
┌─────────────────────────────────────────────┐
│  1. Launcher Layer (__main__.py, launcher.py)│
│     CLI parsing, WorkRoot detection, boot    │
├─────────────────────────────────────────────┤
│  2. Server Layer (app/server.py)             │
│     FastAPI app, HTTP routes, WebSocket      │
├─────────────────────────────────────────────┤
│  3. GUI Layer (gui/static/)                  │
│     Browser-based HTML/CSS/JS interface      │
├─────────────────────────────────────────────┤
│  4. Core Layer (core/)                       │
│     Session, config, events, orchestrator,   │
│     planner, goal engine, locks, concurrency │
├─────────────────────────────────────────────┤
│  5. Safety Layer (safety/)                   │
│     Governor, path/command/credential/self   │
│     protection policies, audit log           │
├─────────────────────────────────────────────┤
│  6. Tools Layer (tools/)                     │
│     ToolKernel, 16+ tool modules (file,      │
│     shell, git, memory, notes, web, etc.)    │
├─────────────────────────────────────────────┤
│  7. Fusion Layer (fusion/)                   │
│     Council, router, synthesizer, roles,     │
│     schemas, scoring, reviewer               │
├─────────────────────────────────────────────┤
│  8. Providers Layer (providers/)             │
│     Registry, OpenAI-compat, Ollama, Mock    │
├─────────────────────────────────────────────┤
│  9. Intelligence Layer                       │
│     Workspace (indexer, tree, symbols),      │
│     Memory (store, project, session,         │
│     retrieval, compaction), Skills,          │
│     Locations, Browser, Web, GitHub, Cache   │
└─────────────────────────────────────────────┘
```

## Key Relationships

- **Launcher** creates a **Session**, starts the **Server**, opens the **GUI**
- **Server** exposes HTTP/WebSocket API, delegates goal execution to **Orchestrator**
- **Orchestrator** coordinates: GoalEngine → Planner → FusionRouter → Council → Synthesizer → ToolKernel → Verification
- **ToolKernel** enforces safety through **SafetyGovernor** before every mutation
- **Council** spawns parallel LLM calls via **ProviderRegistry**, fuses results via **Synthesizer**
- **SafetyGovernor** composes: PathPolicy + CommandPolicy + CredentialPolicy + SelfProtectionPolicy
- All shared state access goes through **fcntl.flock** advisory locks

## Entry Points

| Entry Point | File | Purpose |
|------------|------|---------|
| CLI `gm` | `galaxy_merge/__main__.py` | Main CLI entry, dispatches to Launcher |
| Launcher | `galaxy_merge/app/launcher.py` | Boot coordinator: session, server, browser, heartbeat |
| Server | `galaxy_merge/app/server.py` | FastAPI app with all HTTP/WS routes |
| Orchestrator | `galaxy_merge/core/orchestrator.py` | Goal execution pipeline |

## Design Principles

1. **Harness over chatbot.** The harness owns execution; models contribute reasoning.
2. **Deterministic safety.** Safety policies are code, not model judgment.
3. **Evidence-based completion.** Claims require verification evidence (file content, test output, build output).
4. **Project-local isolation.** All runtime state in `.gm/`, never committed.
5. **Graceful degradation.** Missing providers, failed roles, and partial results are handled without crashing.
