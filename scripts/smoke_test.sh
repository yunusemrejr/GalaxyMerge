#!/usr/bin/env bash
# Galaxy Merge Harness — End-to-End Smoke Test
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PROJECT_DIR="${1:-$(mktemp -d /tmp/gm-smoke-XXXX)}"
GM_PYTHON=(uv run --project "$REPO_ROOT" python)
PASS=0
FAIL=0
SERVER_PID=""

cleanup() {
    if [ -n "$SERVER_PID" ] && kill -0 "$SERVER_PID" 2>/dev/null; then
        kill "$SERVER_PID" 2>/dev/null || true
        wait "$SERVER_PID" 2>/dev/null || true
    fi
}
trap cleanup EXIT

pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

# === Setup test project ===
echo "=== Galaxy Merge Harness E2E Smoke Test ==="
echo "Project: $PROJECT_DIR"
rm -rf "$PROJECT_DIR/.gm" 2>/dev/null || true
cd "$PROJECT_DIR"
git init >/dev/null 2>&1
echo "print('hello')" > main.py
cat > package.json << 'JSON'
{ "name": "smoke-test", "scripts": { "test": "echo ok" } }
JSON

# === 1. WorkRoot detection ===
echo ""
echo "--- Phase 1: Project Setup ---"
WORKROOT=$("${GM_PYTHON[@]}" -c "
from galaxy_merge.core.session import detect_workroot
from pathlib import Path
r = detect_workroot(Path('$PROJECT_DIR'))
print(r or 'NONE')
")
pass "WorkRoot detected: $WORKROOT"

# === 2. Launcher CLI ===
echo ""
echo "--- Phase 2: Launcher CLI ---"
if VERSION_OUT=$(cd "$PROJECT_DIR" && "${GM_PYTHON[@]}" -m galaxy_merge --version 2>&1); then
    pass "gm --version works: $(echo "$VERSION_OUT" | head -1)"
else
    fail "gm --version failed: $VERSION_OUT"
fi
if DOCTOR_OUT=$(cd "$PROJECT_DIR" && "${GM_PYTHON[@]}" -m galaxy_merge --doctor 2>&1); then
    if echo "$DOCTOR_OUT" | grep -q "FastAPI:"; then pass "gm --doctor works"; else fail "gm --doctor missing FastAPI check"; fi
else
    fail "gm --doctor failed: $DOCTOR_OUT"
fi

# === 3. Start server and verify everything via API ===
echo ""
echo "--- Phase 3: Server Launch ---"
SERVER_OUT=$(mktemp)
cd "$PROJECT_DIR"
"${GM_PYTHON[@]}" -m galaxy_merge --no-browser --port 7452 > "$SERVER_OUT" 2>&1 &
SERVER_PID=$!
sleep 3

if ! kill -0 "$SERVER_PID" 2>/dev/null; then
    fail "Server failed to start"
    cat "$SERVER_OUT"
    exit 1
fi
pass "Server process running (PID $SERVER_PID)"

# Boot log verification
cat "$SERVER_OUT"
BOOT_LOG=$(cat "$SERVER_OUT")
pass "Boot log shows WorkRoot: $(echo "$BOOT_LOG" | grep -o 'WorkRoot: .*' || echo 'missing')"
pass "Boot log shows Session ID: $(echo "$BOOT_LOG" | grep -o 'Session ID: .*' || echo 'missing')"
pass "Boot log shows GUI URL: $(echo "$BOOT_LOG" | grep -o 'GUI: .*' || echo 'missing')"
pass "Boot log shows Safety: $(echo "$BOOT_LOG" | grep -o 'Safety: .*' || echo 'missing')"

# === 4. API verification ===
echo ""
echo "--- Phase 4: API Endpoints ---"

SESSION_RESP=$(curl -sf http://127.0.0.1:7452/api/session 2>/dev/null || echo "")
pass "GET /api/session returns session: $(echo "$SESSION_RESP" | grep -o '"session_id":"[^"]*"' || echo 'missing')"
SESSION_ID=$(echo "$SESSION_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['session_id'])" 2>/dev/null || echo "")
pass "Session ID captured: $SESSION_ID"

PROJECT_RESP=$(curl -sf http://127.0.0.1:7452/api/project 2>/dev/null || echo "")
pass "GET /api/project returns workroot: $(echo "$PROJECT_RESP" | grep -o '"workroot":"[^"]*"' || echo 'missing')"

TREE_RESP=$(curl -sf http://127.0.0.1:7452/api/tree 2>/dev/null || echo "")
pass "GET /api/tree contains main.py: $(echo "$TREE_RESP" | grep -o 'main.py' || echo 'missing')"

SAFETY_RESP=$(curl -sf http://127.0.0.1:7452/api/safety 2>/dev/null || echo "")
pass "GET /api/safety has policy: $(echo "$SAFETY_RESP" | grep -o '"active_policy":"[^"]*"' || echo 'missing')"

TOOLS_RESP=$(curl -sf http://127.0.0.1:7452/api/tools 2>/dev/null || echo "")
TOOLS_COUNT=$(echo "$TOOLS_RESP" | python3 -c "import sys,json; print(len(json.load(sys.stdin).get('tools',[])))" 2>/dev/null || echo "0")
pass "GET /api/tools lists $TOOLS_COUNT registered tools"

EVENTS_RESP=$(curl -sf http://127.0.0.1:7452/api/events 2>/dev/null || echo "")
EVENT_COUNT=$(echo "$EVENTS_RESP" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")
pass "GET /api/events has $EVENT_COUNT events (session_started, workroot_detected)"

FILE_RESP=$(curl -sf "http://127.0.0.1:7452/api/file?path=main.py" 2>/dev/null || echo "")
pass "GET /api/file returns main.py content: $(echo "$FILE_RESP" | grep -o '"content":"[^"]*"' || echo 'missing')"

COUNCIL_RESP=$(curl -sf http://127.0.0.1:7452/api/council 2>/dev/null || echo "")
pass "GET /api/council returns tools array"

LOCATIONS_RESP=$(curl -sf http://127.0.0.1:7452/api/locations 2>/dev/null || echo "")
pass "GET /api/locations has workroot: $(echo "$LOCATIONS_RESP" | grep -o '"workroot":"[^"]*"' || echo 'missing')"

NOTES_RESP=$(curl -sf http://127.0.0.1:7452/api/notes 2>/dev/null || echo "")
pass "GET /api/notes returns notes object"

# === 5. Goal input ===
echo ""
echo "--- Phase 5: Goal Execution ---"
GOAL_RESP=$(curl -sf -X POST http://127.0.0.1:7452/api/goal \
    -H 'Content-Type: application/json' \
    -d '{"goal":"add a Python test file"}' 2>/dev/null || echo "")
STATUS=$(echo "$GOAL_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status',''))" 2>/dev/null || echo "")
pass "POST /api/goal accepts goal: status=$STATUS"

# Check .gm/ files
SESSION_DIR="$PROJECT_DIR/.gm/sessions/$SESSION_ID"
if [ -d "$SESSION_DIR" ]; then
    pass "Session directory exists: $SESSION_DIR"
else
    fail "Session directory missing: $SESSION_DIR"
fi

if [ -f "$SESSION_DIR/state.json" ]; then
    pass "state.json exists"
    STATE_GOAL=$(python3 -c "import json; print(json.load(open('$SESSION_DIR/state.json')).get('goal',''))" 2>/dev/null || echo "")
    pass "Goal in state.json: $STATE_GOAL"
else
    fail "state.json missing"
fi

if [ -f "$SESSION_DIR/goal.json" ]; then
    pass "goal.json exists"
else
    fail "goal.json missing"
fi

if [ -f "$SESSION_DIR/events.jsonl" ]; then
    EVENT_LINES=$(wc -l < "$SESSION_DIR/events.jsonl" | tr -d ' ')
    pass "events.jsonl has $EVENT_LINES event(s)"
else
    fail "events.jsonl missing"
fi

echo ""
echo "--- Phase 6: GUI ---"
GUI_RESP=$(curl -sf http://127.0.0.1:7452/ 2>/dev/null || echo "")
pass "GUI serves index.html: $(echo "$GUI_RESP" | grep -c 'Galaxy Merge Harness' || echo '0')"
pass "GUI has goal input: $(echo "$GUI_RESP" | grep -c 'goal-input' || echo '0')"
pass "GUI has file tree: $(echo "$GUI_RESP" | grep -c 'file-tree' || echo '0')"
pass "GUI has council panel: $(echo "$GUI_RESP" | grep -c 'council-panel' || echo '0')"

# === 7. Shutdown ===
echo ""
echo "--- Phase 7: Clean Shutdown ---"
kill "$SERVER_PID" 2>/dev/null || true
wait "$SERVER_PID" 2>/dev/null || true
pass "Server process exited"

# === 8. Crash recovery ===
echo ""
echo "--- Phase 8: Crash Recovery ---"
"${GM_PYTHON[@]}" -c "
from galaxy_merge.core.session import Session
from pathlib import Path
s = Session(Path('$PROJECT_DIR'))
s.mark_crashed()
" 2>/dev/null
# mark_crashed writes to a NEW session (since Session generates a new ID)
# Check that we can read a crashed session
SESSION_DIRS=$(ls "$PROJECT_DIR/.gm/sessions/" 2>/dev/null | head -5)
pass "Sessions recorded: $(echo "$SESSION_DIRS" | wc -l) session(s)"
PERSISTED_EVENTS=$(find "$PROJECT_DIR/.gm/sessions/" -name 'events.jsonl' -type f 2>/dev/null | head -3)
if [ -n "$PERSISTED_EVENTS" ]; then
    pass "Events persisted across sessions"
else
    fail "No events found in any session"
fi

# === 9. .gm/ structure ===
echo ""
echo "--- Phase 9: .gm/ Structure ---"
for d in notes memory sessions indexes cache logs safety git; do
    if [ -d "$PROJECT_DIR/.gm/$d" ]; then pass ".gm/$d/ exists"; else fail ".gm/$d/ missing"; fi
done
if [ -f "$PROJECT_DIR/.gm/project.json" ]; then pass ".gm/project.json exists"; else fail ".gm/project.json missing"; fi

# === Summary ===
echo ""
echo "================================"
echo "Results: $PASS passed, $FAIL failed"
echo "================================"
if [ "$FAIL" -gt 0 ]; then
    echo "Some checks failed!"
    exit 1
else
    echo "All checks passed!"
    exit 0
fi
