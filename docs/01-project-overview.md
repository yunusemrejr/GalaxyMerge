# Project Overview

## What Galaxy Merge Is

Galaxy Merge Harness is a self-contained, Ubuntu/Linux-native, autonomous coding harness. It runs locally on a developer machine, coordinates multiple LLM providers through a multi-role council system, and enforces deterministic safety boundaries on all file and shell operations.

**Primary command:** `gm`  
**Primary interface:** Browser GUI (launched automatically)  
**Runtime owner:** Terminal process that launched `gm`  
**Language:** Python 3.12+  
**Backend:** FastAPI + Uvicorn (ASGI)  
**Frontend:** Vanilla HTML/CSS/JS (no framework)  

## How It Works

1. User runs `gm` from a project directory
2. Launcher detects WorkRoot (project root via `.git`, `package.json`, `pyproject.toml`, etc.)
3. Creates/loads `.gm/` runtime state directory in the project
4. Starts a local FastAPI server on `127.0.0.1` (port auto-selected or specified)
5. Opens the browser GUI
6. Terminal streams operational logs
7. User enters a coding goal through the GUI
8. System: parses goal → loads memory/notes → indexes workspace → creates a council of LLM roles → fuses outputs → executes changes through native tools → verifies → records evidence → reports completion

## Key Design Decisions

- **Models don't own execution.** Every mutation flows through the Native Tool Kernel and the Safety Governor. Models propose; the harness disposes.
- **Multi-model council.** Goals are processed by multiple roles (planner, scout, implementer, reviewer, skeptic, synthesizer) potentially on different providers/models, fused by evidence ranking.
- **Deterministic safety.** Path policies, command policies, credential policies, and self-protection are code-based, not model-judged.
- **Project-local state.** `.gm/` lives inside the target project. Never committed. Never shared.
- **Self-protection.** If `gm` is launched inside its own source tree, it enters read-only diagnostic mode.

## Two-Folder Model

```
~/Desktop/Galaxymerge/     = Galaxy Merge app/source/install folder
~/Desktop/MyProject/       = target project you want Galaxy Merge to work on
```

Running `gm` from the Galaxy Merge source tree activates read-only diagnostic mode (no file writes, no shell mutations, no git mutations).

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.12+ |
| Backend | FastAPI + Uvicorn |
| HTTP Client | httpx |
| Data Models | Pydantic v2 |
| Config | JSON files + YAML |
| HTML Parsing | BeautifulSoup4 + lxml |
| WebSockets | websockets (FastAPI native) |
| Build System | hatchling (via pyproject.toml) |
| Package Manager | uv |
| Testing | pytest + pytest-asyncio + pytest-timeout |
| CI | GitHub Actions |
| Frontend | Vanilla HTML/CSS/JS |
| Locking | fcntl.flock (POSIX advisory locks) |
