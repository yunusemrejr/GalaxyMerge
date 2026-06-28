

from pathlib import Path

import pytest

pytestmark = [pytest.mark.integration]

from galaxy_merge.app.server import (
    SessionServer,
    _build_tree,
    build_council_event_summary,
    build_locations_payload,
    build_logs_payload,
    build_notes_payload,
)
from galaxy_merge.app.launcher import Launcher
from galaxy_merge.core.session import Session, init_gm_dir


@pytest.fixture
def session(tmp_path: Path) -> Session:
    init_gm_dir(tmp_path)
    created = Session(tmp_path)
    created.save_state()
    return created


@pytest.fixture
def server(session: Session) -> SessionServer:
    return SessionServer(session, port=0)


class TestSessionServer:
    def test_registers_expected_api_routes(self, server: SessionServer) -> None:
        paths = {getattr(route, "path", "") for route in server.app.routes}

        assert "/api/session" in paths
        assert "/api/project" in paths
        assert "/api/tree" in paths
        assert "/api/events" in paths
        assert "/api/safety" in paths
        assert "/api/tools" in paths
        assert "/api/locations" in paths
        assert "/api/notes" in paths
        assert "/api/browser/sessions" in paths
        assert "/api/council" in paths

    def test_session_payload_contains_session_id(self, session: Session) -> None:
        data = session.to_dict()

        assert data["session_id"].startswith("gmsess_")
        assert data["workroot"] == str(session.workroot)

    def test_project_file_exists_after_init(self, session: Session) -> None:
        assert (session.gm_dir / "project.json").exists()


class TestLauncher:
    def test_launcher_opens_browser_by_default(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        opened = []

        import pathlib

        class FakeServer:
            def __init__(self):
                self.config_dir = pathlib.Path(tmp_path / "config_templates")
                self._socket = None

            def serve(self):
                pass

        def fake_start_server(session: Session, port: int = 0) -> dict[str, object]:
            return {"url": "http://127.0.0.1:43210/", "port": 43210, "server": FakeServer()}

        monkeypatch.setattr("galaxy_merge.app.launcher.start_server", fake_start_server)
        monkeypatch.setattr("galaxy_merge.app.launcher.open_browser", opened.append)

        result = Launcher(project_dir=str(tmp_path)).run()

        assert result == 0
        assert opened == ["http://127.0.0.1:43210/"]

    def test_launcher_respects_no_browser(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        opened = []

        import pathlib

        class FakeServer:
            def __init__(self):
                self.config_dir = pathlib.Path(tmp_path / "config_templates")
                self._socket = None

            def serve(self):
                pass

        def fake_start_server(session: Session, port: int = 0) -> dict[str, object]:
            return {"url": "http://127.0.0.1:43210/", "port": 43210, "server": FakeServer()}

        monkeypatch.setattr("galaxy_merge.app.launcher.start_server", fake_start_server)
        monkeypatch.setattr("galaxy_merge.app.launcher.open_browser", opened.append)

        result = Launcher(project_dir=str(tmp_path), no_browser=True).run()

        assert result == 0
        assert opened == []


class TestPayloadBuilders:
    def test_tree_payload_contains_workspace_file(self, tmp_path: Path) -> None:
        (tmp_path / "main.py").write_text("print('ok')\n")

        data = _build_tree(tmp_path, tmp_path, max_entries=20)

        names = [child["name"] for child in data["children"]]
        assert "main.py" in names

    def test_logs_payload_is_paginated(self, tmp_path: Path) -> None:
        log_path = tmp_path / "project.log"
        log_path.write_text("\n".join(f"line {i}" for i in range(20)))

        data = build_logs_payload(log_path, limit=5, offset=5)

        assert data["lines"] == [f"line {i}" for i in range(5, 10)]
        assert data["total"] == 20
        assert data["truncated"] is True

    def test_notes_payload_is_structured_and_legacy_compatible(self, tmp_path: Path) -> None:
        notes_dir = tmp_path / "notes"
        notes_dir.mkdir()
        (notes_dir / "test.md").write_text("hello")

        data = build_notes_payload(notes_dir)

        assert data["notes"][0]["name"] == "test"
        assert data["test"] == "hello"

    def test_locations_payload_exposes_workroot(self, session: Session) -> None:
        data = build_locations_payload(session.workroot, session.gm_dir)

        assert data["workroot"] == str(session.workroot)

    def test_council_payload_summarizes_and_redacts_provider_failures(self, tmp_path: Path) -> None:
        events = [
            {
                "time": "2026-06-28T10:00:00+00:00",
                "event": "provider_called",
                "role": "reviewer",
                "provider_id": "mock_a",
                "model": "mock-review",
                "attempt": 1,
            },
            {
                "time": "2026-06-28T10:00:01+00:00",
                "event": "role_execution_failed",
                "role": "reviewer",
                "provider_id": "mock_a",
                "model": "mock-review",
                "error": "HTTP 401 OPENAI_API_KEY=sk-testtesttesttesttesttest",
                "error_type": "auth",
                "attempt": 1,
                "retry_count": 2,
                "fallback_decision": "pending",
                "duration_ms": 4,
            },
            {
                "time": "2026-06-28T10:00:02+00:00",
                "event": "role_fallback",
                "role": "reviewer",
                "from_provider": "mock_a",
                "to_provider": "mock_b",
                "model": "mock-review-b",
                "fallback_decision": "selected",
                "retry_count": 2,
            },
        ]

        data = build_council_event_summary(events, tmp_path)

        assert data["degraded_roles"] == ["reviewer"]
        assert data["roles"][0]["status"] == "degraded"
        assert data["roles"][0]["error"] == "HTTP 401 OPENAI_API_KEY=***REDACTED***"
        assert data["fallback_events"][0]["to_provider"] == "mock_b"


class TestSafety:
    def test_readonly_mode_detection(self, tmp_path: Path) -> None:
        init_gm_dir(tmp_path)
        created = Session(tmp_path)
        import galaxy_merge

        pkg_dir = Path(galaxy_merge.__file__).resolve().parent.parent
        created.workroot = pkg_dir
        server = SessionServer(created, port=0)

        assert server._check_launch_inside_codebase() is True
