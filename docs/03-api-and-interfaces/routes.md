# HTTP Routes

All routes are defined in `galaxy_merge/app/server.py` (`SessionServer._build_app()`). Server binds to `127.0.0.1` only.

## Session & Project

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/session` | Current session state (id, workroot, status, goal, readonly_mode) |
| GET | `/api/project` | Project metadata from `.gm/project.json` |
| GET | `/api/sessions` | Active sessions list with port mappings |

## File Operations

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/tree?path=&max_entries=` | Directory tree (relative to WorkRoot) |
| GET | `/api/file?path=` | File content (redacted, path-safety checked) |

## Goal Management

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/goal` | Submit a coding goal. Body: `{"goal": "..."}` |
| POST | `/api/stop` | Stop current goal execution |
| POST | `/api/resume` | Resume a stopped session |

## Events & Logs

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/events?limit=&offset=&since=&redact=` | Event log (paginated, filterable) |
| GET | `/api/logs?limit=&offset=` | Project log file |

## Council & Tools

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/council` | Council status and registered tools |
| GET | `/api/tools` | List all registered tools with schemas |

## Notes

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/notes` | List all notes |
| POST | `/api/notes` | Create a note. Body: `{"title": "...", "content": "..."}` |
| PUT | `/api/notes/<id>` | Update a note |
| DELETE | `/api/notes/<id>` | Delete a note |

## Web

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/web/search?q=&source=` | Web search (duckduckgo) |
| POST | `/api/web/fetch` | Fetch a URL. Body: `{"url": "..."}` |

## Browser

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/browser/sessions` | List browser sessions |
| POST | `/api/browser/open` | Open a URL in browser. Body: `{"url": "..."}` |
| GET | `/api/browser/console` | Browser console logs |
| GET | `/api/browser/network` | Browser network logs |
| GET | `/api/browser/errors` | Browser page errors |
| GET | `/api/browser/screenshot?session_id=` | Take screenshot (returns base64) |

## GitHub

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/github/scan?url=` | Scan a GitHub repository |

## Other

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/locations` | Location classification (workroot, galaxy_merge, system) |
| GET | `/api/memory?kind=` | Memory records (facts, failures, fixes, lessons) |
| GET | `/api/skills` | Registered skills |
| GET | `/api/safety` | Safety policy, blocked commands, recent blocked actions |
| POST | `/api/secret-scan` | Run secret scanner. Body: `{"include_history": bool}` |
| GET | `/api/health` | Health check (gm validation, tools count, providers, events) |

## Static Files

The GUI is served at `/` as static files from `galaxy_merge/gui/static/`.
