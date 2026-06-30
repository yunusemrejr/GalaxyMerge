# Galaxy Merge Harness — Documentation

Technical documentation for the Galaxy Merge Harness codebase. All claims verified against source.

**Repository:** `https://github.com/yunusemrejr/GalaxyMerge`  
**Author:** Yunus Emre Vurgun  
**Version:** 0.1.0  
**Platform:** Ubuntu/Linux (Python 3.12+)  

## Table of Contents

| File | Purpose |
|------|---------|
| [00-index.md](00-index.md) | Navigation index for all docs |
| [01-project-overview.md](01-project-overview.md) | What the project is, how it works, who it's for |
| **Architecture** | |
| [02-architecture/README.md](02-architecture/README.md) | Architecture overview and layer model |
| [02-architecture/runtime-flow.md](02-architecture/runtime-flow.md) | Startup sequence, goal execution, shutdown |
| [02-architecture/module-map.md](02-architecture/module-map.md) | Directory and module map |
| [02-architecture/dependency-map.md](02-architecture/dependency-map.md) | External dependencies and their roles |
| [02-architecture/data-flow.md](02-architecture/data-flow.md) | How data moves through the system |
| [02-architecture/process-lifecycle.md](02-architecture/process-lifecycle.md) | Session lifecycle, heartbeats, crash recovery |
| **APIs & Interfaces** | |
| [03-api-and-interfaces/README.md](03-api-and-interfaces/README.md) | API overview |
| [03-api-and-interfaces/cli.md](03-api-and-interfaces/cli.md) | CLI commands and flags |
| [03-api-and-interfaces/routes.md](03-api-and-interfaces/routes.md) | HTTP API routes |
| [03-api-and-interfaces/websocket.md](03-api-and-interfaces/websocket.md) | WebSocket event streaming |
| [03-api-and-interfaces/schemas-and-types.md](03-api-and-interfaces/schemas-and-types.md) | Data types, Pydantic models, JSON schemas |
| **Implementation** | |
| [04-implementation/README.md](04-implementation/README.md) | Implementation overview |
| [04-implementation/configuration.md](04-implementation/configuration.md) | Config loading, env vars, templates |
| [04-implementation/persistence-and-state.md](04-implementation/persistence-and-state.md) | .gm/ layout, state files, caches |
| [04-implementation/safety-model.md](04-implementation/safety-model.md) | Safety Governor, policies, redaction |
| [04-implementation/council-and-fusion.md](04-implementation/council-and-fusion.md) | Multi-model council, fusion, synthesizer |
| [04-implementation/logging-and-errors.md](04-implementation/logging-and-errors.md) | Event logging, error classes, audit |
| [04-implementation/security-boundaries.md](04-implementation/security-boundaries.md) | Trust boundaries, path safety, secrets |
| [04-implementation/concurrency.md](04-implementation/concurrency.md) | Locking, session isolation, heartbeats |
| **Operations** | |
| [05-operations/build-and-run.md](05-operations/build-and-run.md) | Install, run, build commands |
| [05-operations/testing-and-verification.md](05-operations/testing-and-verification.md) | Test suite, smoke tests, CI |
| [05-operations/deployment.md](05-operations/deployment.md) | Deployment and distribution |
| [05-operations/troubleshooting.md](05-operations/troubleshooting.md) | Common issues and fixes |
| **Maintenance** | |
| [06-maintenance/known-issues.md](06-maintenance/known-issues.md) | Known bugs and limitations |
| [06-maintenance/unfinished-work.md](06-maintenance/unfinished-work.md) | Partial implementations and TODOs |
| [06-maintenance/unknowns.md](06-maintenance/unknowns.md) | Unconfirmed behavior and open questions |
| [06-maintenance/documentation-changelog.md](06-maintenance/documentation-changelog.md) | What docs were created/changed |
