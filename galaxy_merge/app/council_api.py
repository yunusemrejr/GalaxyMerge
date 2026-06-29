"""Council and tool status API endpoints."""

from collections.abc import Callable
from pathlib import Path

from fastapi import FastAPI

from galaxy_merge.app.payloads import build_council_event_summary, _redact_nested
from galaxy_merge.core.orchestrator import Orchestrator
from galaxy_merge.core.session import Session
from galaxy_merge.providers.registry import ProviderRegistry
from galaxy_merge.safety.credential_policy import CredentialPolicy


def register_council_routes(
    app: FastAPI,
    session: Session,
    config_dir: Path,
    get_orchestrator: Callable[[], Orchestrator | None],
) -> None:
    @app.get("/api/council")
    async def get_council():
        orchestrator = get_orchestrator()
        policy = CredentialPolicy(session.workroot)
        summary = build_council_event_summary(
            session.event_log.replay(),
            session.workroot,
        )
        if orchestrator:
            providers = _redact_nested(
                orchestrator.providers.available_providers(), policy
            )
            warnings = _redact_nested(orchestrator.providers.load_errors(), policy)
            return {
                "tools": orchestrator.tool_kernel.list_tools(),
                "providers": providers,
                "warnings": warnings,
                **summary,
            }

        registry = ProviderRegistry(config_dir, session_id=session.session_id)
        registry.load()
        providers = _redact_nested(registry.available_providers(), policy)
        warnings = _redact_nested(registry.load_errors(), policy)
        return {"tools": [], "providers": providers, "warnings": warnings, **summary}

    @app.get("/api/tools")
    async def get_tools():
        orchestrator = get_orchestrator()
        if orchestrator:
            return {"tools": orchestrator.tool_kernel.list_tools()}
        return {"tools": []}
