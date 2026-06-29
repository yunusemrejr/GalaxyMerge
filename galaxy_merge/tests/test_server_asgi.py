"""ASGI endpoint regression tests that avoid sync-client deadlocks."""

import json
from pathlib import Path

import httpx
import pytest

from galaxy_merge.app.server import SessionServer
from galaxy_merge.core.session import Session, init_gm_dir

pytestmark = [pytest.mark.integration]


async def _request(server: SessionServer, method: str, path: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        return await client.request(method, path)


@pytest.mark.asyncio
async def test_events_endpoint_defaults_to_legacy_list_shape(tmp_path: Path) -> None:
    # Given: a session with recorded events.
    init_gm_dir(tmp_path)
    session = Session(tmp_path)
    session.save_state()
    for i in range(3):
        session.event_log.emit("log", session_id=session.session_id, index=i)
    server = SessionServer(session, port=0)

    try:
        # When: the legacy events endpoint is requested without query params.
        response = await _request(server, "GET", "/api/events")

        # Then: it returns the legacy list shape.
        assert response.status_code == 200
        payload = response.json()
        assert isinstance(payload, list)
        assert payload[-1]["index"] == 2
    finally:
        server._socket.close()


@pytest.mark.asyncio
async def test_resume_refuses_completed_session(tmp_path: Path) -> None:
    # Given: a completed session.
    init_gm_dir(tmp_path)
    session = Session(tmp_path)
    session.mark_completed()
    server = SessionServer(session, port=0)

    try:
        # When: the GUI asks to resume it.
        response = await _request(server, "POST", "/api/resume")

        # Then: resume is rejected.
        assert response.status_code == 409
    finally:
        server._socket.close()


@pytest.mark.asyncio
async def test_resume_restores_crashed_session(tmp_path: Path) -> None:
    # Given: a crashed session.
    init_gm_dir(tmp_path)
    session = Session(tmp_path)
    session.mark_crashed("boom")
    server = SessionServer(session, port=0)

    try:
        # When: the GUI asks to resume it.
        response = await _request(server, "POST", "/api/resume")

        # Then: the session becomes active and running again.
        assert response.status_code == 200
        assert response.json()["status"] == "resumed"
        state = json.loads(
            (
                tmp_path / ".gm" / "sessions" / session.session_id / "state.json"
            ).read_text()
        )
        assert state["status"] == "running"
    finally:
        server._socket.close()
