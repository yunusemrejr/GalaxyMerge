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


@pytest.mark.asyncio
async def test_council_lists_configured_providers_before_goal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given: local provider configuration exists but no goal has started.
    monkeypatch.delenv("GM_COUNCIL_MISSING_KEY", raising=False)
    init_gm_dir(tmp_path)
    config_dir = tmp_path / ".gm" / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "providers.json").write_text(
        json.dumps(
            {
                "providers": {
                    "ready_mock": {
                        "enabled": True,
                        "type": "mock",
                        "base_url": "http://mock",
                        "auth": {"type": "none"},
                    },
                    "missing_key": {
                        "enabled": True,
                        "type": "openai_compatible",
                        "base_url": "https://example.invalid/v1",
                        "auth": {
                            "type": "env",
                            "env_var": "GM_COUNCIL_MISSING_KEY",
                        },
                    },
                }
            }
        )
    )
    (config_dir / "models.json").write_text(
        json.dumps(
            {
                "models": {
                    "ready_mock:planner": {
                        "provider": "ready_mock",
                        "model": "mock-planner",
                        "enabled": True,
                        "roles": ["planner"],
                    },
                    "missing_key:reviewer": {
                        "provider": "missing_key",
                        "model": "reviewer",
                        "enabled": True,
                        "roles": ["reviewer"],
                    },
                }
            }
        )
    )
    session = Session(tmp_path)
    session.save_state()
    server = SessionServer(session, port=0)

    try:
        # When: the GUI asks for council status before creating an orchestrator.
        response = await _request(server, "GET", "/api/council")

        # Then: provider truth is visible instead of an empty placeholder.
        assert response.status_code == 200
        payload = response.json()
        providers = {item["provider_id"]: item for item in payload["providers"]}
        assert payload["tools"] == []
        assert providers["ready_mock"]["available"] is True
        assert providers["missing_key"]["available"] is False
        assert (
            providers["missing_key"]["warning"]
            == "missing env var: GM_COUNCIL_MISSING_KEY"
        )
        assert payload["roles"] == []
        assert payload["degraded_roles"] == []
    finally:
        server._socket.close()
