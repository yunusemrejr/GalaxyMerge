# Persistence and State

## `.gm/` Directory Structure

Created by `init_gm_dir()` in `core/session.py`. 25+ subdirectories, 15+ files.

```
.gm/
├── project.json                    # Project identity (id, workroot, language hints)
├── README.md                       # Generated readme
├── notes/
│   ├── index.json                  # Notes index (schema_version, notes[])
│   ├── history/                    # Note version history
│   └── .trash/                     # Deleted notes
├── memory/
│   ├── known_facts.jsonl           # Project facts
│   ├── known_failures.jsonl        # Known failures
│   ├── verified_fixes.jsonl        # Verified fixes
│   ├── lessons.jsonl               # Lessons learned
│   └── preferences.json            # User preferences
├── sessions/
│   ├── registry.jsonl              # Session registry (one line per session)
│   ├── registry.lock               # Lock file
│   ├── ports.json                  # Session→port mapping
│   ├── ports.lock                  # Lock file
│   ├── heartbeats/                 # <session_id>.hb files
│   └── <session_id>/
│       ├── state.json              # Session state
│       ├── goal.json               # Goal data
│       ├── events.jsonl            # All events
│       ├── events.lock             # Lock file
│       ├── transcript.jsonl        # Session memory
│       ├── transcript.lock         # Lock file
│       ├── council.jsonl           # Council logs
│       ├── tool_calls.jsonl        # Tool call records
│       ├── safety.jsonl            # Safety decisions
│       ├── provider_events.jsonl   # Provider call logs
│       ├── compaction.jsonl        # Compaction records
│       ├── final.md                # Completion summary
│       ├── diffs/                  # Diff artifacts
│       └── artifacts/              # Build artifacts
├── indexes/
│   ├── embeddings/                 # Embedding index
│   └── file_hashes.json            # File hash tracking
├── cache/
│   ├── provider/                   # Provider response cache
│   ├── fusion/                     # Fusion result cache
│   ├── file_summaries/             # File summary cache
│   ├── skill_matches/              # Skill match cache
│   ├── command_results/            # Command result cache
│   ├── web_search/                 # Web search cache
│   ├── browser_pages/              # Browser page cache
│   └── github_scans/               # GitHub scan cache
├── web/
│   ├── searches.jsonl              # Search history
│   ├── fetched_pages.jsonl         # Fetched pages
│   ├── wikipedia.jsonl             # Wikipedia lookups
│   ├── duckduckgo.jsonl            # DuckDuckGo searches
│   └── curl_fetches.jsonl          # Curl fetch history
├── browser/
│   ├── profiles/                   # Browser profiles
│   ├── sessions/                   # Browser sessions
│   ├── screenshots/                # Screenshots
│   ├── console_logs.jsonl          # Console log history
│   ├── network_logs.jsonl          # Network log history
│   └── page_errors.jsonl           # Page error history
├── locations/
│   └── registry.json               # Location classifications
├── github/
│   ├── scans/                      # Scan results
│   ├── issues/                     # Issue data
│   ├── pull_requests/              # PR data
│   └── repos.jsonl                 # Repo scan history
├── logs/
│   └── project.log                 # Application log
├── safety/
│   ├── policy.snapshot.json        # Active safety policy
│   ├── blocked_actions.jsonl       # Blocked action audit log
│   ├── allowed_commands.json       # Allowed command list
│   └── protected_paths.json        # Protected path list
├── git/
│   ├── checkpoints/                # Git checkpoint data
│   └── patchsets/                  # Patch set data
├── skill_matches/                  # Skill match results
└── locks/                          # Advisory lock files
```

## State Transitions

Session state is persisted to `state.json` on every status change via `atomic_write` (temp + rename under flock).

## File Format Standards

- **JSONL** for append-only logs (events, memory, transcripts, audit)
- **JSON** for structured state (project.json, state.json, config files)
- **Markdown** for human-readable summaries (final.md, README.md)
- All writes use `atomic_write()` (temp file + rename under flock)
- All appends use `atomic_append()` (flock + write + unlock)

## TTL and Expiration

Cache entries include `_expires` (unix timestamp). `CacheStore.get()` checks expiration and auto-deletes expired entries.

Heartbeat TTL: 300 seconds. Sessions without heartbeat in 300s are cleaned up.

## Lock Files

Every shared resource has a `.lock` sidecar file used for `fcntl.flock()` advisory locking. Lock files are in `.gm/locks/` or alongside the resource.
