#!/usr/bin/env bash
# Galaxy Merge Harness - provider degradation acceptance scenario
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PROJECT_DIR="${1:-$(mktemp -d /tmp/gm-provider-degradation-XXXX)}"
GM_PYTHON=(uv run --project "$REPO_ROOT" python)
SERVER_PID=""

cleanup() {
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

require_cmd curl
require_cmd git

mkdir -p "$PROJECT_DIR/config_templates"
cd "$PROJECT_DIR"
git init >/dev/null 2>&1

cat > "$PROJECT_DIR/README.md" <<'MD'
# Provider Degradation Fixture
MD

cat > "$PROJECT_DIR/config_templates/providers.json" <<'JSON'
{
  "providers": {
    "mock_primary": {
      "enabled": true,
      "type": "mock",
      "base_url": "http://mock-primary",
      "auth": {"type": "none"},
      "timeout_seconds": 2,
      "failures": {
        "reviewer": "HTTP 500 upstream failure OPENAI_API_KEY=sk-providerdegradationx"
      }
    },
    "mock_fallback": {
      "enabled": true,
      "type": "mock",
      "base_url": "http://mock-fallback",
      "auth": {"type": "none"},
      "timeout_seconds": 2,
      "responses": {
        "reviewer": {
          "findings": [
            {
              "type": "verification",
              "file": "README.md",
              "evidence": "test_output",
              "severity": "low",
              "recommendation": "fallback reviewer completed"
            }
          ],
          "risks": [],
          "approved": true
        }
      }
    }
  }
}
JSON

cat > "$PROJECT_DIR/config_templates/models.json" <<'JSON'
{
  "models": {
    "mock_primary:reviewer": {
      "provider": "mock_primary",
      "model": "mock-primary-reviewer",
      "enabled": true,
      "context_window": 32000,
      "output_limit": 4096,
      "strengths": ["review"],
      "roles": ["reviewer"],
      "cost_tier": "low",
      "latency_tier": "fast",
      "cache_behavior": {"supports_prefix_cache": false}
    },
    "mock_fallback:reviewer": {
      "provider": "mock_fallback",
      "model": "mock-fallback-reviewer",
      "enabled": true,
      "context_window": 32000,
      "output_limit": 4096,
      "strengths": ["review"],
      "roles": ["reviewer"],
      "cost_tier": "low",
      "latency_tier": "fast",
      "cache_behavior": {"supports_prefix_cache": false}
    }
  }
}
JSON

cat > "$PROJECT_DIR/config_templates/fusion.json" <<'JSON'
{
  "councils": {
    "coding_default": {
      "max_parallel_calls": 1,
      "timeout_seconds": 5,
      "per_role_timeout": 2,
      "retry_count": 2,
      "retry_backoff": 0.01,
      "retry_backoff_max": 0.01,
      "minimum_quorum": 1,
      "degraded_mode": "continue_with_warnings",
      "roles": {
        "reviewer": {
          "required": true,
          "criticality": "required_for_completion",
          "fallback_chain": ["mock_primary:reviewer", "mock_fallback:reviewer"],
          "model_selector": {
            "role": "reviewer",
            "cost_policy": "cheap",
            "prefer_strengths": ["review"]
          }
        }
      }
    }
  }
}
JSON

cat > "$PROJECT_DIR/config_templates/routing.json" <<'JSON'
{
  "routing_rules": [
    {"match": {"task_type": "small_edit"}, "council": "coding_default"}
  ],
  "fallback": {"council": "coding_default"}
}
JSON

git add README.md >/dev/null 2>&1
git commit -m "fixture: provider degradation baseline" >/dev/null 2>&1

EVIDENCE_DIR="$PROJECT_DIR/.gm/acceptance/provider_degradation"
mkdir -p "$EVIDENCE_DIR"
GM_LOG="$EVIDENCE_DIR/gm-terminal.log"

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

"${GM_PYTHON[@]}" - "$REPO_ROOT" "$PROJECT_DIR" "$SESSION_ID" "$API_BASE" "$EVIDENCE_DIR" <<'PY'
import asyncio
import json
import sys
import time
import urllib.request
from pathlib import Path

from galaxy_merge.core.locks import atomic_write
from galaxy_merge.core.orchestrator import Orchestrator
from galaxy_merge.core.session import Session
from galaxy_merge.safety.credential_policy import CredentialPolicy

RUNTIME_NEEDLE = "sk-providerdegradationx"


async def main() -> int:
    repo_root = Path(sys.argv[1])
    project_dir = Path(sys.argv[2])
    session_id = sys.argv[3]
    api_base = sys.argv[4]
    evidence_dir = Path(sys.argv[5])
    report_path = evidence_dir / "acceptance-report.json"

    session = Session(project_dir, session_id=session_id)
    session.save_state()
    orchestrator = Orchestrator(session, project_dir / "config_templates", repo_root)
    await orchestrator.initialize()
    session.event_log.emit(
        "acceptance_provider_degradation_started",
        session_id=session_id,
    )

    start = time.monotonic()
    result = await orchestrator.tool_kernel.execute(
        "council.spawn",
        {
            "goal": "review provider fallback behavior",
            "council_name": "coding_default",
        },
        session_id=session_id,
    )
    elapsed_ms = int((time.monotonic() - start) * 1000)

    with urllib.request.urlopen(f"{api_base}/api/council", timeout=5) as response:
        api_payload = json.loads(response.read().decode("utf-8"))

    events = session.event_log.replay()
    events_text = json.dumps(events, default=str)
    api_text = json.dumps(api_payload, default=str)
    result_dict = result.to_dict()

    provider_called = [e for e in events if e.get("event") == "provider_called"]
    role_failures = [e for e in events if e.get("event") == "role_execution_failed"]
    provider_failures = [e for e in events if e.get("event") == "provider_failed"]
    fallback_events = [e for e in events if e.get("event") == "role_fallback"]

    checks = {
        "tool_success": result.success,
        "bounded_runtime": elapsed_ms < 5000,
        "fallback_success_result": (
            result.success
            and "reviewer" in ((result.data or {}).get("results") or {})
            and "error" not in ((result.data or {}).get("results") or {}).get("reviewer", [{}])[0]
        ),
        "degraded_role_returned": "reviewer" in ((result.data or {}).get("degraded_roles") or []),
        "provider_called_events": len(provider_called) >= 2,
        "role_failure_logged": any(e.get("role") == "reviewer" for e in role_failures),
        "provider_failure_logged": any(e.get("provider_id") == "mock_primary" for e in provider_failures),
        "fallback_logged": any(
            e.get("from_provider") == "mock_primary" and e.get("to_provider") == "mock_fallback"
            for e in fallback_events
        ),
        "failure_event_has_required_fields": all(
            field in role_failures[0]
            for field in ["provider_id", "model", "role", "error_type", "duration_ms", "retry_count", "fallback_decision"]
        ) if role_failures else False,
        "api_exposes_degraded_role": "reviewer" in (api_payload.get("degraded_roles") or []),
        "api_exposes_fallback": any(
            event.get("to_provider") == "mock_fallback"
            for event in api_payload.get("fallback_events", [])
        ),
        "raw_secret_absent_from_events": RUNTIME_NEEDLE not in events_text,
        "raw_secret_absent_from_api": RUNTIME_NEEDLE not in api_text,
    }
    passed = all(checks.values())

    report = {
        "passed": passed,
        "project_dir": str(project_dir),
        "session_id": session_id,
        "api_base": api_base,
        "elapsed_ms": elapsed_ms,
        "checks": checks,
        "tool_result": result_dict,
        "api_council": api_payload,
        "events": {
            "provider_called": provider_called,
            "role_execution_failed": role_failures,
            "provider_failed": provider_failures,
            "role_fallback": fallback_events,
        },
        "evidence": {
            "terminal_log": str(evidence_dir / "gm-terminal.log"),
            "report": str(report_path),
            "events": str(session.events_path),
        },
    }
    redactor = CredentialPolicy(project_dir)

    def redact_value(value):
        if isinstance(value, str):
            return redactor.redact(value)
        if isinstance(value, list):
            return [redact_value(item) for item in value]
        if isinstance(value, dict):
            return {key: redact_value(item) for key, item in value.items()}
        return value

    atomic_write(report_path, json.dumps(redact_value(report), indent=2, default=str))
    session.event_log.emit(
        "acceptance_provider_degradation_completed",
        session_id=session_id,
        passed=passed,
        report=str(report_path),
    )
    print(json.dumps({"passed": passed, "report": str(report_path), "checks": checks}, indent=2))
    return 0 if passed else 1


raise SystemExit(asyncio.run(main()))
PY

REPORT_PATH="$EVIDENCE_DIR/acceptance-report.json"
"${GM_PYTHON[@]}" - "$REPORT_PATH" <<'PY'
import json
import sys
from pathlib import Path

report = json.loads(Path(sys.argv[1]).read_text())
if not report.get("passed"):
    print(json.dumps(report.get("checks", {}), indent=2), file=sys.stderr)
    raise SystemExit(1)
print(f"PASS: acceptance report {sys.argv[1]}")
PY
