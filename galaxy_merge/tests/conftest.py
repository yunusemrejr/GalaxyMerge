from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def pytest_sessionstart() -> None:
    """Create ignored local test defaults from public-safe examples when absent."""
    config_templates = REPO_ROOT / "galaxy_merge" / "config_templates"
    config_templates.mkdir(exist_ok=True)
    for name in ("fusion", "routing"):
        target = config_templates / f"{name}.json"
        if target.exists():
            continue
        source = REPO_ROOT / "config" / f"{name}.example.json"
        target.write_text(source.read_text())
