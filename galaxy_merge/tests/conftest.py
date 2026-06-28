"""Root conftest for Galaxy Merge tests.

Provides shared fixtures, markers, and session-level setup.
"""

from pathlib import Path

import pytest

from galaxy_merge.tests.fixtures.fakes import (
    FakeBrowserManager,
    FakeClock,
    FakeEventBus,
    FakeProvider,
    FakeProviderRegistry,
    make_fake_config,
    make_fake_gm_dir,
    make_fake_project,
)

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
        if source.exists():
            target.write_text(source.read_text())


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_provider():
    """Return a FakeProvider instance."""
    return FakeProvider()


@pytest.fixture
def fake_registry():
    """Return a FakeProviderRegistry with one fake provider pre-loaded."""
    reg = FakeProviderRegistry()
    reg.add(FakeProvider("fake"))
    return reg


@pytest.fixture
def fake_browser(tmp_path):
    """Return a FakeBrowserManager with profile in tmp_path."""
    return FakeBrowserManager(profile_dir=tmp_path / "browser")


@pytest.fixture
def fake_event_bus():
    """Return a FakeEventBus."""
    return FakeEventBus()


@pytest.fixture
def fake_clock():
    """Return a FakeClock starting at t=1000."""
    return FakeClock()


@pytest.fixture
def fake_project(tmp_path):
    """Create and return a fake project directory."""
    return make_fake_project(tmp_path)


@pytest.fixture
def fake_gm_dir(tmp_path):
    """Create and return a fake .gm directory."""
    return make_fake_gm_dir(tmp_path)


@pytest.fixture
def fake_config_dir(tmp_path):
    """Create and return a fake config directory with providers/models/fusion."""
    return make_fake_config(tmp_path)
