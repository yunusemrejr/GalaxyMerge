# Configuration

## Config Locations

| Location | Purpose |
|----------|---------|
| `~/.config/galaxy-merge/config.json` | App-level config (install dir, default port, browser pref) |
| `galaxy_merge/config_templates/` | Project-level config templates (copied during install) |
| `config/*.example.json` | Public example configs (placeholders only, safe to commit) |
| `.env` | Environment variables (never committed) |

## Config Files

### `providers.json`
Maps provider IDs to API endpoints and auth:
```json
{
  "providers": {
    "openai": {
      "type": "openai_compatible",
      "base_url": "https://api.openai.com/v1",
      "auth": {"type": "env", "env_var": "OPENAI_API_KEY"},
      "enabled": true
    }
  }
}
```

### `models.json`
Maps model keys to providers, roles, and capabilities:
```json
{
  "models": {
    "gpt-4o": {
      "provider": "openai",
      "model": "gpt-4o",
      "roles": ["planner", "implementer", "reviewer"],
      "cost_tier": "medium",
      "context_window": 128000,
      "strengths": ["reasoning", "code"]
    }
  }
}
```

### `fusion.json`
Council configurations:
```json
{
  "councils": {
    "coding_default": {
      "roles": {
        "planner": {"required": true, "model_selector": {"cost_policy": "balanced"}},
        "implementer": {"required": true},
        "reviewer": {"required": true},
        "skeptic": {"required": false}
      },
      "max_parallel_calls": 4,
      "timeout_seconds": 180,
      "retry_count": 3
    }
  }
}
```

### `routing.json`
Maps task types to councils:
```json
{
  "routing_rules": [
    {"match": {"task_type": "bug_fix"}, "council": "coding_default"}
  ],
  "fallback": {"council": "coding_default"}
}
```

### `safety.json`
Safety policy configuration (currently uses default policy).

## Environment Variables

### Provider Keys
```
OPENAI_API_KEY, ANTHROPIC_API_KEY, GOOGLE_API_KEY, DEEPSEEK_API_KEY,
MINIMAX_API_KEY, STREAMLAKE_API_KEY, STEPFUN_API_KEY, OPENROUTER_API_KEY,
NVIDIA_API_KEY, KIMI_API_KEY, OLLAMA_API_KEY, GITHUB_TOKEN, GH_TOKEN
```

### System
- `GALAXY_MERGE_OPENCODE_EXPORT` — path to OpenCode provider export for import
- `PYTEST_CURRENT_TEST` — enables offline socket mode for tests
- `GMLAUNCHER_OFFLINE` — enables offline socket mode

## Config Hash

`compute_config_hash(config_dir)` concatenates all config files and returns a SHA-256 prefix. Used for cache invalidation when config changes.

## Config Validation

`ProviderRegistry.load()` validates:
- `providers.json`: each provider has `type`, `base_url`, valid `auth`
- `models.json`: each model has `provider`, `model`, `roles[]`
- `fusion.json`: each council has `roles` object
- `routing.json`: rules reference existing councils
