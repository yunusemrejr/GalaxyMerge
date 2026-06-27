from pathlib import Path
from typing import Any

from galaxy_merge.memory.store import MemoryStore
from galaxy_merge.memory.project_memory import ProjectMemory
from galaxy_merge.tools.notes_tools import get_injected_notes, clear_goal_injections


class MemoryRetriever:
    def __init__(self, gm_dir: Path):
        self.gm_dir = gm_dir
        self.project_memory = ProjectMemory(gm_dir)
        self.store = MemoryStore(gm_dir)
        self._note_roles: dict[str, list[str]] = {}

    def get_context_for_goal(self, goal: str) -> dict[str, Any]:
        memory_context = self.project_memory.get_relevant_context(goal)

        notes_context = ""
        notes_dir = self.gm_dir / "notes"
        injected = get_injected_notes()
        note_parts = []

        if injected:
            for name in injected:
                path = notes_dir / f"{name}.md"
                if path.exists():
                    note_parts.append(f"--- {name} (injected) ---\n{path.read_text()}")
        elif notes_dir.exists():
            index_path = notes_dir / "index.json"
            pinned = []
            if index_path.exists():
                import json
                try:
                    index = json.loads(index_path.read_text())
                    pinned = [n["path"].replace(".md", "") for n in index.get("notes", []) if n.get("pinned")]
                except Exception:
                    pass
            for f in sorted(notes_dir.iterdir()):
                if f.suffix != ".md" or f.stem == "index" or f.parent.name == ".trash":
                    continue
                if pinned and f.stem not in pinned:
                    continue
                note_parts.append(f"--- {f.stem} ---\n{f.read_text()[:500]}")

        if note_parts:
            notes_context = "\n\n".join(note_parts)

        return {
            "memory": memory_context,
            "notes": notes_context,
            "injected_notes": injected,
        }

    def record_note_usage(self, note_name: str, role: str) -> None:
        if note_name not in self._note_roles:
            self._note_roles[note_name] = []
        self._note_roles[note_name].append(role)

    def get_note_usage(self) -> dict[str, list[str]]:
        return dict(self._note_roles)

    def clear_for_new_goal(self) -> None:
        self._note_roles.clear()
        clear_goal_injections()
