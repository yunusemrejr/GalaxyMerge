from pathlib import Path
from typing import Any

from galaxy_merge.core.locks import atomic_write


class DeploymentPolicy:
    def __init__(self, gm_dir: Path):
        self.path = gm_dir / "locations" / "deployment_policy.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._policy: dict[str, Any] = self._load()

    def _load(self) -> dict[str, Any]:
        if self.path.exists():
            import json
            return json.loads(self.path.read_text())
        return {
            "schema_version": 1,
            "default": "block",
            "rules": [],
        }

    def _save(self) -> None:
        import json
        atomic_write(self.path, json.dumps(self._policy, indent=2))

    def check(self, target_class: str, command: str) -> dict[str, Any]:
        if target_class in ("local_workroot", "local_taskscope", "local_gm_project_state"):
            return {"decision": "allow", "reason": "local project operation"}

        for rule in self._policy.get("rules", []):
            if rule.get("target_class") == target_class:
                if rule.get("allowed_commands"):
                    for allowed in rule["allowed_commands"]:
                        if allowed in command:
                            return {"decision": "allow", "reason": f"matched rule: {rule.get('name', '')}"}
                    return {"decision": "block", "reason": f"no matching allowed command for rule: {rule.get('name', '')}"}
                return {"decision": rule.get("action", "block"), "reason": rule.get("reason", "blocked by policy")}

        return {"decision": "block", "reason": "remote/production mutation blocked by default"}

    def add_rule(self, name: str, target_class: str, allowed_commands: list[str], action: str = "allow") -> None:
        self._policy.setdefault("rules", []).append({
            "name": name,
            "target_class": target_class,
            "allowed_commands": allowed_commands,
            "action": action,
        })
        self._save()

    def to_dict(self) -> dict[str, Any]:
        return dict(self._policy)
