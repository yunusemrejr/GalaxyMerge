#!/usr/bin/env bash
# Galaxy Merge Harness — broken webapp repair acceptance scenario
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PROJECT_DIR="${1:-$(mktemp -d /tmp/gm-webapp-repair-XXXX)}"
GM_PYTHON=(uv run --project "$REPO_ROOT" python)
SERVER_PID=""
APP_PID=""

cleanup() {
    if [ -n "$APP_PID" ] && kill -0 "$APP_PID" 2>/dev/null; then
        kill "$APP_PID" 2>/dev/null || true
        wait "$APP_PID" 2>/dev/null || true
    fi
    if [ -n "$SERVER_PID" ] && kill -0 "$SERVER_PID" 2>/dev/null; then
        kill "$SERVER_PID" 2>/dev/null || true
        wait "$SERVER_PID" 2>/dev/null || true
    fi
}
trap cleanup EXIT

require_cmd() {
    if ! command -v "$1" >/dev/null 2>&1; then
        echo "missing required command: $1" >&2
        exit 1
    fi
}

require_cmd git
require_cmd node
require_cmd npm
require_cmd curl

mkdir -p "$PROJECT_DIR/src" "$PROJECT_DIR/tests" "$PROJECT_DIR/config_templates"
cd "$PROJECT_DIR"
git init >/dev/null 2>&1

cp "$REPO_ROOT/config/providers.example.json" "$PROJECT_DIR/config_templates/providers.json"
cp "$REPO_ROOT/config/models.example.json" "$PROJECT_DIR/config_templates/models.json"
cp "$REPO_ROOT/config/fusion.example.json" "$PROJECT_DIR/config_templates/fusion.json"
cp "$REPO_ROOT/config/routing.example.json" "$PROJECT_DIR/config_templates/routing.json"

cat > "$PROJECT_DIR/package.json" <<'JSON'
{
  "name": "gm-webapp-repair-fixture",
  "private": true,
  "type": "module",
  "scripts": {
    "test": "node tests/test_math.mjs"
  }
}
JSON

cat > "$PROJECT_DIR/src/index.html" <<'HTML'
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <title>Galaxy Merge Repair Fixture</title>
    <link rel="icon" href="data:,">
  </head>
  <body>
    <main>
      <h1>Repair Fixture</h1>
      <p id="status">Loading</p>
    </main>
    <script type="module" src="/app.js"></script>
  </body>
</html>
HTML

cat > "$PROJECT_DIR/src/app.js" <<'JS'
import { double } from "./math.js";

const status = document.querySelector("#status");
status.textContent = `Answer: ${double(21)}`;
JS

cat > "$PROJECT_DIR/tests/test_math.mjs" <<'JS'
const math = await import("../src/math.js");

if (math.double(21) !== 42) {
  throw new Error(`expected double(21) to equal 42, got ${math.double(21)}`);
}

console.log("math ok");
JS

git add package.json src/index.html src/app.js tests/test_math.mjs >/dev/null 2>&1
git commit -m "fixture: broken webapp baseline" >/dev/null 2>&1

EVIDENCE_DIR="$PROJECT_DIR/.gm/acceptance/webapp_repair"
mkdir -p "$EVIDENCE_DIR"
GM_LOG="$EVIDENCE_DIR/gm-terminal.log"
APP_LOG="$EVIDENCE_DIR/app-server.log"

"${GM_PYTHON[@]}" -m galaxy_merge --no-browser --port 0 > "$GM_LOG" 2>&1 &
SERVER_PID=$!

for _ in $(seq 1 60); do
    if grep -q '^GUI: ' "$GM_LOG"; then
        break
    fi
    sleep 0.25
done

if ! kill -0 "$SERVER_PID" 2>/dev/null; then
    echo "gm server failed to start" >&2
    cat "$GM_LOG" >&2
    exit 1
fi

GUI_URL="$(sed -n 's/^GUI: //p' "$GM_LOG" | tail -1)"
if [ -z "$GUI_URL" ]; then
    echo "gm GUI URL not found in terminal log" >&2
    cat "$GM_LOG" >&2
    exit 1
fi

API_BASE="${GUI_URL%/}"
SESSION_ID="$(curl -sf "$API_BASE/api/session" | "${GM_PYTHON[@]}" -c 'import json,sys; print(json.load(sys.stdin)["session_id"])')"

APP_PORT="$("${GM_PYTHON[@]}" - <<'PY'
import socket

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
    sock.bind(("127.0.0.1", 0))
    print(sock.getsockname()[1])
PY
)"

python3 -m http.server "$APP_PORT" --bind 127.0.0.1 --directory "$PROJECT_DIR/src" > "$APP_LOG" 2>&1 &
APP_PID=$!
APP_URL="http://127.0.0.1:${APP_PORT}/"

for _ in $(seq 1 60); do
    if curl -sf "$APP_URL" >/dev/null 2>&1; then
        break
    fi
    sleep 0.25
done

GM_BROWSER_HEADLESS=1 "${GM_PYTHON[@]}" - "$REPO_ROOT" "$PROJECT_DIR" "$SESSION_ID" "$APP_URL" "$EVIDENCE_DIR" <<'PY'
import asyncio
import json
import os
import shutil
import sys
import time
from pathlib import Path

from galaxy_merge.core.locks import atomic_write
from galaxy_merge.core.orchestrator import Orchestrator
from galaxy_merge.core.session import Session
from galaxy_merge.safety.credential_policy import CredentialPolicy


async def main() -> int:
    repo_root = Path(sys.argv[1])
    project_dir = Path(sys.argv[2])
    session_id = sys.argv[3]
    app_url = sys.argv[4]
    evidence_dir = Path(sys.argv[5])
    report_path = evidence_dir / "acceptance-report.json"

    os.environ["GM_BROWSER_HEADLESS"] = "1"
    session = Session(project_dir, session_id=session_id)
    session.save_state()
    orchestrator = Orchestrator(session, project_dir / "config_templates", repo_root)
    await orchestrator.initialize()
    session.event_log.emit(
        "acceptance_webapp_repair_started",
        session_id=session_id,
        app_url=app_url,
    )

    tool_results: list[dict[str, object]] = []

    async def tool(name: str, params: dict[str, object] | None = None) -> dict[str, object]:
        result = await orchestrator.tool_kernel.execute(name, params or {}, session_id)
        record = {"tool": name, "params": params or {}, "result": result.to_dict()}
        tool_results.append(record)
        return result.to_dict()

    async def wait_page_errors_stable(min_count: int) -> dict[str, object]:
        previous_count = -1
        stable_polls = 0
        current: dict[str, object] = {"success": False, "data": {"count": 0, "page_errors": []}}
        for _ in range(40):
            current = await tool("browser.page_errors.read", {"session_id": "repair"})
            count = int((current.get("data") or {}).get("count", 0))
            if count >= min_count and count == previous_count:
                stable_polls += 1
            else:
                stable_polls = 0
            previous_count = count
            if stable_polls >= 2:
                return current
            time.sleep(0.25)
        return current

    await tool("notes.write", {
        "name": "webapp-repair-context",
        "title": "Webapp Repair Context",
        "content": "Use browser console and npm test output. The fixture should show Answer: 42.",
    })
    await tool("notes.tag", {"name": "webapp-repair-context", "tags": ["acceptance", "webapp"]})
    await tool("notes.pin", {"name": "webapp-repair-context", "pinned": True})
    await tool("notes.inject", {"name": "webapp-repair-context"})
    skill_search = await tool("skill.search", {"query": "web frontend browser console debugging"})

    pre_test = await tool("shell.run", {"command": "npm test", "timeout": 30})
    browser_open = await tool("browser.open", {"url": app_url, "session_id": "repair"})
    if not browser_open["success"]:
        raise RuntimeError(f"browser.open failed: {browser_open}")

    initial_errors = await wait_page_errors_stable(min_count=1)

    initial_network = await tool("browser.network.read", {"session_id": "repair"})
    initial_console = await tool("browser.console.read", {"session_id": "repair"})
    before_screenshot = await tool("browser.screenshot", {"session_id": "repair"})
    before_screenshot_copy = evidence_dir / "before.png"
    before_screenshot_path = (before_screenshot.get("data") or {}).get("screenshot_path")
    if before_screenshot_path:
        shutil.copyfile(str(before_screenshot_path), before_screenshot_copy)

    math_content = "export function double(value) {\n  return value * 2;\n}\n"
    write_fix = await tool("file.write", {
        "path": "src/math.js",
        "content": math_content,
        "expected_hash": "",
    })
    post_test = await tool("shell.run", {"command": "npm test", "timeout": 30})

    before_error_count = int((initial_errors.get("data") or {}).get("count", 0))
    await tool("browser.navigate", {"session_id": "repair", "url": f"{app_url}?fixed=1"})

    final_dom: dict[str, object] = {"success": False, "data": {}}
    for _ in range(40):
        final_dom = await tool("browser.dom.snapshot", {"session_id": "repair", "selector": "#status"})
        html_preview = str((final_dom.get("data") or {}).get("html_preview", ""))
        if "Answer: 42" in html_preview:
            break
        time.sleep(0.25)

    final_errors = await wait_page_errors_stable(min_count=before_error_count)
    final_network = await tool("browser.network.read", {"session_id": "repair"})
    after_screenshot = await tool("browser.screenshot", {"session_id": "repair"})
    after_screenshot_copy = evidence_dir / "after.png"
    after_screenshot_path = (after_screenshot.get("data") or {}).get("screenshot_path")
    if after_screenshot_path:
        shutil.copyfile(str(after_screenshot_path), after_screenshot_copy)
    git_status = await tool("git.status")
    git_diff = await tool("git.diff")

    council_results = {
        "planner": [{
            "parsed": {
                "goal_understanding": "Repair missing browser module and failing npm test.",
                "relevant_files": ["src/app.js", "src/math.js", "tests/test_math.mjs"],
                "steps": ["Capture browser failure", "Create missing module", "Verify npm and DOM"],
                "completion_criteria": ["npm test passes", "DOM shows Answer: 42", "no new page errors after reload"],
                "risks": [],
            },
        }],
        "scout": [{
            "parsed": {
                "files_found": ["src/app.js", "tests/test_math.mjs"],
                "architecture_summary": "Static ES module app served by a local Python HTTP server.",
                "uncertainties": [],
            },
        }],
        "implementer": [{
            "parsed": {
                "changes": [{
                    "file": "src/math.js",
                    "action": "create",
                    "diff": math_content,
                    "rationale": "The browser and npm test both fail because app.js imports a missing math.js module.",
                }],
            },
        }],
        "reviewer": [{
            "parsed": {
                "findings": [{
                    "type": "verification",
                    "file": "src/math.js",
                    "evidence": "test_output",
                    "severity": "pass",
                    "recommendation": "Keep the small pure function and npm test.",
                }],
                "risks": [],
                "approved": True,
            },
        }],
        "cheap_verifier": [{
            "parsed": {
                "findings": [{
                    "type": "browser",
                    "file": "src/app.js",
                    "evidence": "tool_logs",
                    "severity": "pass",
                }],
                "syntax_ok": True,
                "summary": "Browser DOM and npm test verified after repair.",
            },
        }],
        "skeptic": [{
            "parsed": {
                "blockers": [],
                "missing_evidence": [],
                "completion_claim_valid": True,
            },
        }],
    }
    synthesis = await tool("council.synthesize", {"council_results": council_results})
    synthesis_output = ((synthesis.get("data") or {}).get("output") or {})
    review = await tool("council.review", {
        "fusion_result": synthesis_output,
    })

    final_error_count = int((final_errors.get("data") or {}).get("count", 0))
    dom_preview = str((final_dom.get("data") or {}).get("html_preview", ""))
    post_test_data = post_test.get("data") or {}
    completion_payload = dict(synthesis_output)
    completion_payload["verification_evidence"] = {
        "dom_preview": dom_preview,
        "post_test_stdout": post_test_data.get("stdout", ""),
        "post_test_stderr": post_test_data.get("stderr", ""),
        "browser_error_count_after_reload": final_error_count,
    }
    completion = await tool("completion.review", {
        "result": completion_payload,
        "criteria": ["src/math.js", "Answer: 42", "npm test"],
    })
    await tool("browser.close", {"session_id": "repair"})

    pre_test_failed = not bool(pre_test.get("success"))
    post_test_passed = bool(post_test.get("success"))
    initial_browser_failed = before_error_count > 0
    no_new_browser_errors = final_error_count == before_error_count
    dom_fixed = "Answer: 42" in dom_preview
    screenshot_captured = bool(after_screenshot.get("success"))
    council_review_passed = bool((review.get("data") or {}).get("approved"))
    completion_review_passed = bool((completion.get("data") or {}).get("approved"))

    passed = all([
        pre_test_failed,
        post_test_passed,
        initial_browser_failed,
        no_new_browser_errors,
        dom_fixed,
        bool(write_fix.get("success")),
        screenshot_captured,
        council_review_passed,
        completion_review_passed,
    ])

    report = {
        "passed": passed,
        "project_dir": str(project_dir),
        "session_id": session_id,
        "app_url": app_url,
        "notes_used": ["webapp-repair-context"],
        "skill_search": skill_search,
        "checks": {
            "pre_test_failed": pre_test_failed,
            "post_test_passed": post_test_passed,
            "initial_browser_failed": initial_browser_failed,
            "no_new_browser_errors_after_reload": no_new_browser_errors,
            "dom_fixed": dom_fixed,
            "screenshot_captured": screenshot_captured,
            "council_review_passed": council_review_passed,
            "completion_review_passed": completion_review_passed,
        },
        "evidence": {
            "terminal_log": str(evidence_dir / "gm-terminal.log"),
            "app_server_log": str(evidence_dir / "app-server.log"),
            "report": str(report_path),
            "events": str(session.session_dir / "events.jsonl"),
            "browser_console": str(session.gm_dir / "browser" / "console_logs.jsonl"),
            "browser_network": str(session.gm_dir / "browser" / "network_logs.jsonl"),
            "browser_page_errors": str(session.gm_dir / "browser" / "page_errors.jsonl"),
            "before_screenshot": str(before_screenshot_copy),
            "after_screenshot": str(after_screenshot_copy),
        },
        "browser": {
            "initial_errors": initial_errors,
            "initial_console": initial_console,
            "initial_network": initial_network,
            "final_errors": final_errors,
            "final_network": final_network,
            "final_dom": final_dom,
        },
        "tests": {
            "pre": pre_test,
            "post": post_test,
        },
        "git": {
            "status": git_status,
            "diff": git_diff,
        },
        "council": {
            "roles": list(council_results.keys()),
            "synthesis": synthesis,
            "review": review,
            "completion": completion,
        },
        "tool_results": tool_results,
    }
    redactor = CredentialPolicy(project_dir)
    atomic_write(report_path, redactor.redact(json.dumps(report, indent=2, default=str)))
    session.event_log.emit(
        "acceptance_webapp_repair_completed",
        session_id=session_id,
        passed=passed,
        report=str(report_path),
    )
    print(json.dumps({"passed": passed, "report": str(report_path)}, indent=2))
    return 0 if passed else 1


raise SystemExit(asyncio.run(main()))
PY

REPORT_PATH="$EVIDENCE_DIR/acceptance-report.json"
if "${GM_PYTHON[@]}" - "$REPORT_PATH" <<'PY'
import json
import sys
from pathlib import Path

report = json.loads(Path(sys.argv[1]).read_text())
if not report.get("passed"):
    print(json.dumps(report.get("checks", {}), indent=2), file=sys.stderr)
    raise SystemExit(1)
print(f"PASS: acceptance report {sys.argv[1]}")
PY
then
    exit 0
fi

echo "FAIL: acceptance report $REPORT_PATH" >&2
exit 1
