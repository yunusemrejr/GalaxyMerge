from pathlib import Path
from typing import Any

from galaxy_merge.fusion.council import Council
from galaxy_merge.providers.registry import ProviderRegistry


class FusionRouter:
    def __init__(self, providers: ProviderRegistry, config_dir: Path):
        self.providers = providers
        self.config_dir = config_dir
        self._routing_rules: list[dict[str, Any]] = []
        self._fallback: dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        routing_path = self.config_dir / "routing.json"
        if routing_path.exists():
            import json
            data = json.loads(routing_path.read_text())
            self._routing_rules = data.get("routing_rules", [])
            self._fallback = data.get("fallback", {})

        fusion_path = self.config_dir / "fusion.json"
        if fusion_path.exists():
            import json
            self._fusion_config = json.loads(fusion_path.read_text())
        else:
            self._fusion_config = {}

    def select_council(self, task_type: str) -> dict[str, Any]:
        for rule in self._routing_rules:
            match = rule.get("match", {})
            if match.get("task_type") == task_type:
                council_name = rule.get("council", "")
                councils = self._fusion_config.get("councils", {})
                if council_name in councils:
                    return councils[council_name]

        fallback_name = self._fallback.get("council", "coding_default")
        councils = self._fusion_config.get("councils", {})
        return councils.get(fallback_name, {})

    def create_council(self, task_type: str, goal: str, event_log=None, session_id: str = "") -> Council:
        config = self.select_council(task_type)
        council = Council(self.providers, config, goal, event_log=event_log, session_id=session_id)
        return council
