# Unknowns

Items that could not be confirmed from source inspection alone.

## Runtime Behavior

| Item | Status | Notes |
|------|--------|-------|
| Exact token counting accuracy | Unknown | Uses `len(content) // 4` estimation, not provider tokenizer |
| Provider-side cache hit rates | Unknown | Prefix caching is supported but effectiveness depends on provider |
| Maximum concurrent session limit | Unknown | No explicit limit found; bounded by OS file descriptors and memory |
| WebSocket reconnection behavior | Unknown | Server doesn't implement reconnection; client-side responsibility |

## Configuration

| Item | Status | Notes |
|------|--------|-------|
| Custom safety policy format | Unknown | `safety.json` exists but default policy is hardcoded |
| Routing rule priority | Unknown | Rules are checked in order; no explicit priority field |
| Fusion config inheritance | Unknown | No mechanism for config inheritance or overrides |

## Integration

| Item | Status | Notes |
|------|--------|-------|
| OpenCode export format | Partially known | `opencode_import.py` handles it but format spec not documented |
| Browser CDP version compatibility | Unknown | Depends on installed Chrome/Chromium version |
| Ollama API version | Confirmed | Uses `/api/chat` for completions and `/api/tags` for health checks (Ollama 0.1.x+ API) |

## Testing

| Item | Status | Notes |
|------|--------|-------|
| Test coverage percentage | Unknown | No coverage tool configured |
| Flaky test rate | Unknown | No flaky test tracking |
| Performance benchmarks | Unknown | No benchmark suite |
