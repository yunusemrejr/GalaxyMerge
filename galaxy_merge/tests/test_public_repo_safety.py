
import pytest

pytestmark = [pytest.mark.integration]


import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [*args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_public_publish_candidates_exclude_local_runtime_state() -> None:
    # Given: the public repository candidate set is computed with Git ignores.
    result = _git("ls-files", "--cached", "--others", "--exclude-standard")

    # When: local-only harness state exists in the checkout.
    assert result.returncode == 0, result.stderr
    paths = set(result.stdout.splitlines())

    # Then: machine-local state and generated acceptance fixtures are excluded.
    forbidden_prefixes = (
        ".gm/",
        ".opencode/",
        ".pi/",
        "acceptance_fixture/",
        "galaxy_merge/config_templates/providers.json",
        "galaxy_merge/config_templates/models.json",
    )
    leaked = sorted(path for path in paths if path.startswith(forbidden_prefixes))
    assert leaked == []


def test_public_example_configs_are_placeholder_only() -> None:
    # Given: public-safe examples are the only config JSON intended for GitHub.
    example_paths = {
        "providers": REPO_ROOT / "config" / "providers.example.json",
        "models": REPO_ROOT / "config" / "models.example.json",
        "fusion": REPO_ROOT / "config" / "fusion.example.json",
        "routing": REPO_ROOT / "config" / "routing.example.json",
    }

    # When: the examples are loaded from the public config directory.
    loaded = {name: json.loads(path.read_text()) for name, path in example_paths.items()}

    # Then: they use documentation placeholders, not local provider choices.
    providers = loaded["providers"]["providers"]
    assert set(providers) == {"example_openai_compatible", "example_local_ollama"}
    assert providers["example_openai_compatible"]["base_url"] == "https://api.example.invalid/v1"
    assert providers["example_openai_compatible"]["auth"]["env_var"] == "GM_EXAMPLE_PROVIDER_API_KEY"

    model_text = json.dumps(loaded["models"]).lower()
    local_provider_names = ("deepseek", "stepfun", "streamlake", "minimax", "openrouter", "moonshot")
    assert not any(provider_name in model_text for provider_name in local_provider_names)


@pytest.mark.integration
def test_fallback_secret_scan_accepts_public_candidate_set() -> None:
    # Given: the repository has fake red-team strings and placeholder examples.
    script = REPO_ROOT / "scripts" / "secret_scan.sh"

    # When: the public safety scanner runs without optional third-party tools.
    result = _run(str(script))

    # Then: the candidate set is accepted without leaking local runtime state.
    assert result.returncode == 0, result.stderr


@pytest.mark.integration
def test_fallback_secret_scan_accepts_git_history() -> None:
    # Given: public history may contain more than one commit.
    script = REPO_ROOT / "scripts" / "secret_scan.sh"

    # When: the fallback scanner is asked to scan history.
    result = _run(str(script), "--history")

    # Then: each revision is scanned as its own Git revision argument.
    assert result.returncode == 0, result.stderr


def test_acceptance_matrix_dry_run_lists_all_final_criteria(tmp_path: Path) -> None:
    # Given: the consolidated acceptance matrix supports a dry-run mode.
    script = REPO_ROOT / "scripts" / "acceptance_full_matrix.sh"

    # When: the report is generated without launching runtime services.
    result = _run(str(script), "--dry-run", "--output-dir", str(tmp_path))

    # Then: every final acceptance criterion is represented with evidence refs.
    assert result.returncode == 0, result.stderr
    report = json.loads((tmp_path / "acceptance-matrix.json").read_text())
    assert len(report["criteria"]) == 46
    assert {row["id"] for row in report["criteria"]} == set(range(1, 47))
    assert report["steps"]["pytest"]["status"] == "SKIPPED"
    assert report["steps"]["provider_degradation"]["status"] == "SKIPPED"
