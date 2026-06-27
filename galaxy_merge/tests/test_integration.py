from pathlib import Path

import pytest

from galaxy_merge.app.server import SessionServer, _build_tree, build_locations_payload, build_logs_payload, build_notes_payload
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


class TestSafety:
    def test_readonly_mode_detection(self, tmp_path: Path) -> None:
        init_gm_dir(tmp_path)
        created = Session(tmp_path)
        import galaxy_merge

        pkg_dir = Path(galaxy_merge.__file__).resolve().parent.parent
        created.workroot = pkg_dir
        server = SessionServer(created, port=0)

        assert server._check_launch_inside_codebase() is True
