#!/usr/bin/env bash
# Galaxy Merge Harness - consolidated acceptance evidence matrix
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
GM_PYTHON=(uv run --project "$REPO_ROOT" python)
DRY_RUN=0
REQUIRE_CLEAN=0
OUTPUT_DIR=""

usage() {
    cat <<'USAGE'
Usage: scripts/acceptance_full_matrix.sh [--dry-run] [--require-clean] [--output-dir DIR]

Runs the public-safety, unit, smoke, webapp repair, and provider-degradation
acceptance gates and writes one JSON matrix report.
USAGE
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --dry-run)
            DRY_RUN=1
            shift
            ;;
        --require-clean)
            REQUIRE_CLEAN=1
            shift
            ;;
        --output-dir)
            OUTPUT_DIR="${2:-}"
            if [ -z "$OUTPUT_DIR" ]; then
                echo "--output-dir requires a value" >&2
                exit 2
            fi
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "unknown argument: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

if [ -z "$OUTPUT_DIR" ]; then
    OUTPUT_DIR="$(mktemp -d /tmp/gm-full-matrix-XXXX)"
fi

mkdir -p "$OUTPUT_DIR/logs"
STEPS_TSV="$OUTPUT_DIR/steps.tsv"
STATIC_JSON="$OUTPUT_DIR/static-checks.json"
REPORT_JSON="$OUTPUT_DIR/acceptance-matrix.json"
: > "$STEPS_TSV"

record_step() {
    local step_id="$1"
    local rc="$2"
    local log_path="$3"
    local command="$4"
    printf '%s\t%s\t%s\t%s\n' "$step_id" "$rc" "$log_path" "$command" >> "$STEPS_TSV"
}

run_step() {
    local step_id="$1"
    shift
    local log_path="$OUTPUT_DIR/logs/${step_id}.log"
    local command_text
    printf -v command_text '%q ' "$@"
    if [ "$DRY_RUN" -eq 1 ]; then
        printf 'SKIPPED dry-run: %s\n' "$command_text" > "$log_path"
        record_step "$step_id" 77 "$log_path" "$command_text"
        return 0
    fi

    set +e
    "$@" > "$log_path" 2>&1
    local rc=$?
    set -e
    record_step "$step_id" "$rc" "$log_path" "$command_text"
    return 0
}

run_static_checks() {
    local log_path="$OUTPUT_DIR/logs/static_checks.log"
    set +e
    "${GM_PYTHON[@]}" - "$REPO_ROOT" "$STATIC_JSON" > "$log_path" 2>&1 <<'PY'
import json
import subprocess
import sys
from pathlib import Path

from galaxy_merge.providers.registry import (
    validate_fusion_config,
    validate_models_config,
    validate_providers_config,
    validate_routing_config,
)


def git_check_ignored(root: Path, path: str) -> bool:
    result = subprocess.run(
        ["git", "check-ignore", "-q", path],
        cwd=root,
        check=False,
    )
    return result.returncode == 0


def load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def auth_is_env_or_none(provider_config: dict) -> bool:
    auth = provider_config.get("auth", {})
    if not isinstance(auth, dict):
        return False
    return auth.get("type") in {"env", "none"}


root = Path(sys.argv[1]).resolve()
output_path = Path(sys.argv[2])
gitignore = (root / ".gitignore").read_text()
readme = (root / "README.md").read_text()
contributing = (root / "CONTRIBUTING.md").read_text()
security = (root / "SECURITY.md").read_text()

providers_example = load_json(root / "config" / "providers.example.json")
models_example = load_json(root / "config" / "models.example.json")
fusion_example = load_json(root / "config" / "fusion.example.json")
routing_example = load_json(root / "config" / "routing.example.json")
example_provider_ids = set(providers_example.get("providers", {}))
example_council_ids = set(fusion_example.get("councils", {}))

local_provider_path = root / "config" / "providers.json"
local_model_path = root / "config" / "models.json"
local_provider_config_valid = False
local_model_config_valid = False
local_provider_auth_env_or_none = False
if local_provider_path.exists():
    local_providers = load_json(local_provider_path)
    local_provider_ids = set(local_providers.get("providers", {}))
    local_provider_config_valid = validate_providers_config(local_providers) == []
    local_provider_auth_env_or_none = all(
        auth_is_env_or_none(config)
        for config in local_providers.get("providers", {}).values()
        if isinstance(config, dict)
    )
    if local_model_path.exists():
        local_models = load_json(local_model_path)
        local_model_config_valid = validate_models_config(local_models, local_provider_ids) == []

source_text = "\n".join(path.read_text(errors="ignore") for path in (root / "galaxy_merge").rglob("*.py"))
checks = {
    "gitignore_blocks_runtime": all(
        pattern in gitignore
        for pattern in [".gm/", ".env", ".env.*", "config/*.json", "galaxy_merge/config_templates/*.json"]
    ),
    "example_configs_exist": all(
        (root / "config" / name).exists()
        for name in ["providers.example.json", "models.example.json", "fusion.example.json", "routing.example.json"]
    ),
    "example_provider_config_valid": validate_providers_config(providers_example) == [],
    "example_model_config_valid": validate_models_config(models_example, example_provider_ids) == [],
    "example_fusion_config_valid": validate_fusion_config(fusion_example) == [],
    "example_routing_config_valid": validate_routing_config(routing_example, example_council_ids) == [],
    "example_auth_uses_env_or_none": all(
        auth_is_env_or_none(config)
        for config in providers_example.get("providers", {}).values()
        if isinstance(config, dict)
    ),
    "docs_explain_safe_setup": all(
        needle in (readme + contributing + security).lower()
        for needle in ["environment", "secret", "provider", "secret_scan.sh"]
    ),
    "local_provider_config_ignored": git_check_ignored(root, "config/providers.json"),
    "local_model_config_ignored": git_check_ignored(root, "config/models.json"),
    "local_provider_config_valid": local_provider_config_valid,
    "local_model_config_valid": local_model_config_valid,
    "local_provider_auth_env_or_none": local_provider_auth_env_or_none,
    "no_opencode_runtime_import": "import opencode" not in source_text and "from opencode" not in source_text,
    "acceptance_scripts_exist": all(
        (root / "scripts" / name).exists()
        for name in ["smoke_test.sh", "acceptance_webapp_repair.sh", "acceptance_provider_degradation.sh"]
    ),
}
hard_failures = [
    key for key in [
        "gitignore_blocks_runtime",
        "example_configs_exist",
        "example_provider_config_valid",
        "example_model_config_valid",
        "example_fusion_config_valid",
        "example_routing_config_valid",
        "example_auth_uses_env_or_none",
        "docs_explain_safe_setup",
        "local_provider_config_ignored",
        "local_model_config_ignored",
        "no_opencode_runtime_import",
        "acceptance_scripts_exist",
    ]
    if not checks.get(key)
]
output_path.write_text(json.dumps({"checks": checks, "hard_failures": hard_failures}, indent=2))
print(json.dumps({"hard_failures": hard_failures}, indent=2))
raise SystemExit(1 if hard_failures else 0)
PY
    local rc=$?
    set -e
    record_step "static_checks" "$rc" "$log_path" "static acceptance checks"
}

run_static_checks
run_step "git_remote" git remote -v
if [ "$REQUIRE_CLEAN" -eq 1 ]; then
    run_step "git_status_clean" bash -lc 'test -z "$(git status --short)"'
else
    run_step "git_status" git status --short --branch
fi
run_step "pytest" "${GM_PYTHON[@]}" -m pytest
run_step "smoke" "$REPO_ROOT/scripts/smoke_test.sh"
run_step "webapp_repair" "$REPO_ROOT/scripts/acceptance_webapp_repair.sh"
run_step "provider_degradation" "$REPO_ROOT/scripts/acceptance_provider_degradation.sh"
run_step "history_scan" "$REPO_ROOT/scripts/secret_scan.sh" --history

"${GM_PYTHON[@]}" - "$STEPS_TSV" "$STATIC_JSON" "$REPORT_JSON" "$DRY_RUN" <<'PY'
import json
import sys
from pathlib import Path

steps_path = Path(sys.argv[1])
static_path = Path(sys.argv[2])
report_path = Path(sys.argv[3])
dry_run = sys.argv[4] == "1"

steps = {}
for line in steps_path.read_text().splitlines():
    step_id, rc, log_path, command = line.split("\t", 3)
    status = "PASS" if rc == "0" else "SKIPPED" if rc == "77" else "FAIL"
    steps[step_id] = {
        "status": status,
        "returncode": int(rc),
        "log": log_path,
        "command": command,
    }

static = json.loads(static_path.read_text()) if static_path.exists() else {"checks": {}}
static_checks = static.get("checks", {})

criteria = [
    (1, "gm launches GUI from normal project", ["smoke"]),
    (2, "terminal owns runtime logs", ["smoke"]),
    (3, "browser GUI connects to correct session", ["smoke", "provider_degradation"]),
    (4, ".gm schema correct", ["smoke", "pytest"]),
    (5, "project notes persistent and CRUD-editable", ["pytest", "webapp_repair"]),
    (6, "multiple sessions in same WorkRoot isolated", ["pytest"]),
    (7, "shared .gm notes/memory/index/cache do not corrupt", ["pytest"]),
    (8, "same-file conflicts detected", ["pytest"]),
    (9, "WorkRoot and TaskScope correct", ["pytest", "smoke"]),
    (10, "provider/model/fusion/routing configs load and validate", ["static:example_provider_config_valid", "static:example_model_config_valid", "static:example_fusion_config_valid", "static:example_routing_config_valid", "pytest"]),
    (11, "API keys read from OS environment", ["static:example_auth_uses_env_or_none", "pytest"]),
    (12, "usable provider endpoints/models configured locally without public secrets", ["static:local_provider_config_valid", "static:local_model_config_valid", "static:local_provider_auth_env_or_none", "static:local_provider_config_ignored"]),
    (13, "Galaxy Merge does not depend on OpenCode runtime", ["static:no_opencode_runtime_import", "pytest"]),
    (14, "council roles real and visible", ["provider_degradation", "pytest"]),
    (15, "fusion is synthesis, not best-answer selection", ["pytest", "webapp_repair"]),
    (16, "provider failures/timeouts degrade safely", ["provider_degradation", "pytest"]),
    (17, "fallback bounded and logged", ["provider_degradation", "pytest"]),
    (18, "terminal shows provider/tool/runtime errors clearly", ["provider_degradation", "smoke"]),
    (19, "GUI shows provider/tool/runtime errors clearly", ["provider_degradation", "smoke"]),
    (20, "native tools work", ["smoke", "pytest"]),
    (21, "shell sandbox works", ["pytest"]),
    (22, "dangerous commands blocked", ["pytest"]),
    (23, "self-modding impossible", ["pytest"]),
    (24, "launch inside Galaxy Merge codebase enters read-only diagnostic mode", ["pytest"]),
    (25, "native web search works", ["pytest"]),
    (26, "DuckDuckGo works", ["pytest"]),
    (27, "Wikipedia works", ["pytest"]),
    (28, "curl/fetch works safely", ["pytest"]),
    (29, "isolated browser automation works", ["webapp_repair", "pytest"]),
    (30, "browser console logs captured", ["webapp_repair", "pytest"]),
    (31, "browser network errors captured", ["webapp_repair", "pytest"]),
    (32, "GitHub repo scan works", ["pytest"]),
    (33, "local/remote/prod locations classified separately", ["pytest", "smoke"]),
    (34, "remote/prod mutation blocked by default", ["pytest"]),
    (35, "skills auto-discovered and used", ["webapp_repair", "pytest"]),
    (36, "memory persists per project", ["pytest"]),
    (37, "cache works without storing secrets", ["pytest", "history_scan"]),
    (38, "compaction preserves mission state", ["pytest"]),
    (39, "tests/build/browser verification run", ["webapp_repair", "pytest"]),
    (40, "completion skeptic prevents premature completion", ["pytest", "webapp_repair"]),
    (41, "GUI handles edge cases", ["smoke", "pytest"]),
    (42, "event logs structured and redacted", ["provider_degradation", "history_scan", "pytest"]),
    (43, "crash recovery minimally functional", ["smoke"]),
    (44, "public repo secret scan passes", ["history_scan"]),
    (45, "README/CONTRIBUTING explain secret-safe configuration", ["static:docs_explain_safe_setup"]),
    (46, "final summary has required evidence fields", ["static_checks", "provider_degradation", "webapp_repair", "history_scan"]),
]


def evidence_status(item: str) -> str:
    if item.startswith("static:"):
        key = item.split(":", 1)[1]
        return "PASS" if static_checks.get(key) else "FAIL"
    return steps.get(item, {"status": "FAIL"})["status"]


def criterion_status(evidence: list[str]) -> str:
    statuses = [evidence_status(item) for item in evidence]
    if any(status == "FAIL" for status in statuses):
        return "FAIL"
    if any(status == "SKIPPED" for status in statuses):
        return "SKIPPED"
    return "PASS"


criterion_rows = [
    {
        "id": cid,
        "criterion": text,
        "status": criterion_status(evidence),
        "evidence": evidence,
    }
    for cid, text, evidence in criteria
]
if any(row["status"] == "FAIL" for row in criterion_rows):
    overall = "FAIL"
elif any(row["status"] == "SKIPPED" for row in criterion_rows):
    overall = "SKIPPED"
else:
    overall = "PASS"

report = {
    "overall_result": overall,
    "criteria": criterion_rows,
    "steps": steps,
    "static_checks": static,
}
report_path.write_text(json.dumps(report, indent=2))
print(json.dumps({"overall_result": overall, "report": str(report_path)}, indent=2))
raise SystemExit(0 if dry_run else 1 if overall == "FAIL" else 0)
PY
