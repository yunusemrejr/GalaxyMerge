# Unfinished Work

## Partially Implemented

### MCP Integration
- Referenced in design docs as future work
- No MCP server or client code exists
- Architecture is MCP-ready (tools are schema-defined)

### Streaming Responses
- Council waits for full response from each role
- No token-by-token streaming to GUI
- WebSocket broadcasts events, not model output tokens

### Semantic Memory Search
- `MemoryRetriever` loads recent entries by kind
- No embedding-based or keyword-based search across memory
- `indexes/embeddings/` directory exists but is unused

### Git Checkpoints
- `git/checkpoints.py` exists with `save()` and `list_all()` methods
- Checkpoint data stored in `.gm/git/checkpoints.jsonl`
- No checkpoint restore or rollback logic exists — checkpoints are records only

### Deployment Policy
- `DeploymentPolicy` class exists in `locations/deployment_policy.py`
- Referenced by shell tools for remote mutation patterns
- Implementation is complete: rules-based policy with default-block, `add_rule()`, and `to_dict()` methods
- Currently not exposed via API or GUI for user configuration

### Token Budget Management
- `token/budget.py` and `token/segments.py` exist
- Token estimation is `len(content) // 4` (rough)
- `TokenBudgetManager` is tested (unit tests in test_token_economy.py) but not wired into the orchestrator's execution pipeline
- `PromptAssembly` in segments.py IS used by the council for prompt construction

### GitHub Integration
- `GitHubScanner` can scan repos via REST API
- Issue and PR creation/management not implemented
- GitHub data stored in `.gm/github/` but not used in goal execution

### Web Search
- DuckDuckGo scraping and Wikipedia API work
- No caching of search results across sessions
- No search result ranking or filtering

## Not Started

- Plugin system for external tools
- Multi-user support
- Remote collaboration
- Cloud sync
- VS Code extension
- TUI interface
- Docker packaging
