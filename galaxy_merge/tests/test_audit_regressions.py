import json
from pathlib import Path

import pytest

from galaxy_merge.app.server import SessionServer, _build_tree, build_logs_payload, build_notes_payload
from galaxy_merge.core.session import Session, init_gm_dir
from galaxy_merge.fusion.router import FusionRouter
from galaxy_merge.providers.registry import ProviderRegistry, validate_routing_config


class TestAuditConfigRegressions:
    def test_template_routing_references_existing_councils(self) -> None:
        config_dir = Path("galaxy_merge/config_templates")
        fusion = json.loads((config_dir / "fusion.json").read_text())
        routing = json.loads((config_dir / "routing.json").read_text())

        errors = validate_routing_config(routing, set(fusion["councils"]))

        assert errors == []

    def test_small_edit_selects_non_empty_council_from_templates(self) -> None:
        config_dir = Path("galaxy_merge/config_templates")
        registry = ProviderRegistry(config_dir)
        registry.load()
        router = FusionRouter(registry, config_dir)

        council = router.select_council("small_edit")

        assert council.get("roles")

    def test_missing_env_key_marks_provider_unavailable(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("GM_AUDIT_MISSING_KEY", raising=False)
        (tmp_path / "providers.json").write_text(json.dumps({
            "providers": {
                "audit": {
                    "enabled": True,
                    "type": "openai_compatible",
                    "base_url": "https://example.invalid/v1",
                    "auth": {"type": "env", "env_var": "GM_AUDIT_MISSING_KEY"},
                }
            }
        }))
        (tmp_path / "models.json").write_text(json.dumps({
            "models": {
                "audit:model": {
                    "provider": "audit",
                    "model": "model",
                    "enabled": True,
                    "roles": ["planner"],
                }
            }
        }))

        registry = ProviderRegistry(tmp_path)
        registry.load()
        providers = registry.available_providers()

        assert providers[0]["healthy"] is False
        assert providers[0]["available"] is False
        assert providers[0]["warning"] == "missing env var: GM_AUDIT_MISSING_KEY"


class TestAuditApiRegressions:
    def test_logs_endpoint_is_bounded(self, tmp_path: Path) -> None:
        log_path = tmp_path / ".gm" / "logs" / "project.log"
        log_path.parent.mkdir(parents=True)
        log_path.write_text("\n".join(f"line {i}" for i in range(2000)))

        data = build_logs_payload(log_path)

        assert len(data["lines"]) <= 500
        assert data["truncated"] is True

    def test_tree_endpoint_is_bounded(self, tmp_path: Path) -> None:
        for i in range(80):
            path = tmp_path / "tree" / f"dir_{i}"
            path.mkdir(parents=True)
            (path / f"file_{i}.txt").write_text("x")

        data = _build_tree(tmp_path, tmp_path, max_entries=25)

        assert data["truncated"] is True
        assert data["entry_count"] <= 25

    def test_notes_endpoint_is_bounded_and_structured(self, tmp_path: Path) -> None:
        init_gm_dir(tmp_path)
        notes_dir = tmp_path / ".gm" / "notes"
        for i in range(30):
            (notes_dir / f"note_{i}.md").write_text("body")

        data = build_notes_payload(notes_dir, limit=10)

        assert len(data["notes"]) == 10
        assert data["truncated"] is True

    def test_browser_open_is_visible_in_sessions(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from galaxy_merge.browser.manager import BrowserManager

        def fake_open(self: BrowserManager, session_id: str, url: str = "about:blank") -> dict[str, object]:
            self._sessions[session_id] = {
                "process": None,
                "profile_dir": str(self.profile_path(session_id)),
                "data_dir": str(self.profile_path(session_id)),
                "url": url,
                "started_at": 1.0,
            }
            return {"success": True, "session_id": session_id, "url": url, "pid": 0}

        monkeypatch.setattr(BrowserManager, "open_session", fake_open)
        init_gm_dir(tmp_path)
        session = Session(tmp_path)
        session.save_state()
        server = SessionServer(session, port=0)

        opened = server._browser_manager.open_session(f"{session.session_id}:gui", "about:blank")
        sessions = []
        for item in server._browser_manager.list_sessions():
            if item["session_id"] == f"{session.session_id}:gui":
                sessions.append({**item, "session_id": "gui"})

        assert opened["success"] is True
        assert sessions[0]["session_id"] == "gui"

    def test_browser_logs_are_filtered_by_session_and_cdp_events_are_recorded(self, tmp_path: Path) -> None:
        from galaxy_merge.browser.cdp import CDPMonitor
        from galaxy_merge.browser.console_logs import ConsoleLogCollector
        from galaxy_merge.browser.network_logs import NetworkLogCollector

        console_a = ConsoleLogCollector("sess_a", tmp_path)
        console_b = ConsoleLogCollector("sess_b", tmp_path)
        network_a = NetworkLogCollector(tmp_path, "sess_a")
        network_b = NetworkLogCollector(tmp_path, "sess_b")
        monitor = CDPMonitor(0, console_a, network_a)

        monitor._handle_event({
            "method": "Runtime.consoleAPICalled",
            "params": {"type": "error", "args": [{"value": "boom"}]},
        })
        monitor._handle_event({
            "method": "Network.responseReceived",
            "params": {"type": "Document", "response": {"url": "https://example.test", "status": 200}},
        })

        assert console_a.get_logs()[0]["message"] == "boom"
        assert console_b.get_logs() == []
        assert network_a.get_logs()[0]["url"] == "https://example.test"
        assert network_b.get_logs() == []


class TestAuditVerificationRegressions:
    @pytest.mark.asyncio
    async def test_empty_fusion_plan_does_not_pass_verification(self, tmp_path: Path) -> None:
        from galaxy_merge.core.orchestrator import Orchestrator

        init_gm_dir(tmp_path)
        session = Session(tmp_path)
        orchestrator = Orchestrator(session, Path("galaxy_merge/config_templates"))

        result = await orchestrator._verify({"plan": [], "changes_proposed": 0})

        assert result["passed"] is False
        assert "no executable plan produced" in result["issues"]
