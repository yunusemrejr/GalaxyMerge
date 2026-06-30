# Known Issues

## Current Limitations

### Browser Automation
- Browser manager depends on CDP (Chrome DevTools Protocol) — requires Chrome/Chromium installed
- Browser sessions are not fully isolated (shared profile directory)
- Screenshot capture may fail if no browser is running

### Provider System
- No built-in rate limiting per provider (relies on provider-side limits)
- Provider health is binary (healthy/unhealthy) — no gradual degradation
- Mock provider returns fixed responses — not useful for production testing

### Fusion System
- Council execution has no streaming — waits for all roles to complete
- Synthesizer uses simple word-overlap for contradiction resolution
- Evidence ranking is hardcoded, not configurable

### Concurrency
- Advisory locks (fcntl.flock) are Linux/macOS only — no Windows support
- Lock timeout is global (30s default) — no per-resource configuration
- No deadlock detection

### Workspace Intelligence
- File hash tracking uses SHA-256[:16] — collision possible (astronomically unlikely)
- Symbol extraction is basic (regex-based, not AST-based)
- Incremental indexing exists (`WorkspaceIndexer.incremental_update()`) but requires explicit file list — no automatic file-watcher trigger

### Memory System
- Memory retrieval is simple (recent N entries) — no semantic search
- Compaction is basic (truncation) — no intelligent summarization
- No cross-session memory sharing

### GUI
- Vanilla HTML/CSS/JS — no framework, no component system
- No mobile responsiveness
- No dark mode toggle (uses CSS variables but single theme)

## Platform Support

- Primary: Ubuntu/Linux
- macOS: Should work (fcntl.flock available) but not primary target
- Windows: Not supported (fcntl.flock unavailable, path separators)
