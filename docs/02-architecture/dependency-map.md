# Dependency Map

## Python Dependencies (from pyproject.toml)

| Package | Version | Role |
|---------|---------|------|
| `fastapi` | ≥0.115.0 | HTTP framework, route definitions, WebSocket support |
| `uvicorn[standard]` | ≥0.34.0 | ASGI server (runs FastAPI app) |
| `websockets` | ≥14.0 | WebSocket protocol support |
| `httpx` | ≥0.28.0 | Async HTTP client (used by OpenAI-compatible provider) |
| `pydantic` | ≥2.0.0 | Data validation, config models, state serialization |
| `pyyaml` | ≥6.0 | YAML parsing (config files) |
| `requests` | ≥2.32.0 | Sync HTTP client (web search, fetch) |
| `beautifulsoup4` | ≥4.14.0 | HTML parsing (web fetch, page analysis) |
| `lxml` | ≥5.0.0 | XML/HTML parser backend for BeautifulSoup |
| `pytest-asyncio` | ≥0.24.0 | Async test support |
| `pytest-timeout` | ≥2.4.0 | Test timeout enforcement |

## Build System

| Component | Technology |
|-----------|-----------|
| Build backend | hatchling |
| Package manager | uv |
| Python requirement | ≥3.12 |
| Entry point | `gm = galaxy_merge.__main__:main` |

## Standard Library Dependencies (important)

| Module | Usage |
|--------|-------|
| `fcntl` | Advisory file locking (`flock`) for cross-process safety |
| `asyncio` | Async execution for council, server, goal pipeline |
| `threading` | Heartbeat thread, offline port allocation lock |
| `subprocess` | Syntax checks (py_compile, node --check), git commands |
| `hashlib` | SHA-256 for file hashing, config hashing, cache keys |
| `json` | All state serialization (JSONL for logs, JSON for configs) |
| `secrets` | Session ID and project ID generation |
| `signal` | SIGINT/SIGTERM handling for graceful shutdown |
| `socket` | TCP port reservation for server |
| `pathlib` | All path operations |
| `re` | Goal parsing, command policy pattern matching |
| `tempfile` | Offline port registry file location |

## External Service Dependencies

| Service | Integration | Required? |
|---------|------------|-----------|
| LLM Providers (OpenAI, Anthropic, Google, etc.) | OpenAI-compatible HTTP API | No (graceful degradation) |
| Ollama | Local Ollama HTTP API | No |
| GitHub API | REST API for repo scanning | No (uses GITHUB_TOKEN) |
| DuckDuckGo | HTML scraping for web search | No |
| Wikipedia | REST API for reference lookup | No |

## CI Dependencies

| Tool | Purpose |
|------|---------|
| GitHub Actions | CI pipeline |
| uv | Dependency installation |
| pytest | Test runner |
| node | JS syntax checking |
| secret_scan.sh | Credential leak detection |
