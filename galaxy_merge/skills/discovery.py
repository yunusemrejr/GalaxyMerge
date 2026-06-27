from pathlib import Path
from typing import Any

SKILL_DIRS: list[Path] = [
    Path.home() / "skills",
    Path.home() / ".config" / "galaxy-merge" / "skills",
]

SUPPORTED_FORMATS: set[str] = {"SKILL.md", "README.md", "skill.json", "skill.yaml"}


class SkillDiscovery:
    def discover(self) -> list[dict[str, Any]]:
        skills = []
        for base_dir in SKILL_DIRS:
            if not base_dir.exists():
                continue
            for entry in sorted(base_dir.iterdir()):
                if entry.is_dir():
                    skill = self._parse_skill_dir(entry)
                    if skill:
                        skills.append(skill)
                elif entry.name in SUPPORTED_FORMATS:
                    skill = self._parse_skill_file(entry)
                    if skill:
                        skills.append(skill)
        return skills

    def _parse_skill_dir(self, path: Path) -> dict[str, Any] | None:
        name = path.name
        summary = ""
        triggers: list[str] = []

        for fmt in SUPPORTED_FORMATS:
            skill_file = path / fmt
            if skill_file.exists():
                content = skill_file.read_text()
                summary = self._extract_summary(content, fmt)
                triggers = self._extract_triggers(content, fmt)
                break

        return {
            "name": name,
            "summary": summary[:200],
            "triggers": triggers,
            "path": str(path),
        }

    def _parse_skill_file(self, path: Path) -> dict[str, Any] | None:
        name = path.stem
        content = path.read_text()
        return {
            "name": name,
            "summary": self._extract_summary(content, path.suffix),
            "triggers": self._extract_triggers(content, path.suffix),
            "path": str(path),
        }

    def _extract_summary(self, content: str, fmt: str) -> str:
        for line in content.splitlines():
            line = line.strip()
            if line.startswith("# "):
                return line[2:].strip()
            if line.startswith('"summary"') or line.startswith("summary"):
                parts = line.split(":", 1)
                if len(parts) > 1:
                    return parts[1].strip().strip('",')
        return content[:200].strip()

    def _extract_triggers(self, content: str, fmt: str) -> list[str]:
        if fmt == "skill.json":
            import json
            try:
                data = json.loads(content)
                return data.get("triggers", [])
            except json.JSONDecodeError:
                pass
        elif fmt in (".yaml", "skill.yaml"):
            try:
                import yaml
                data = yaml.safe_load(content)
                if isinstance(data, dict):
                    return data.get("triggers", [])
            except Exception:
                pass
        return []
