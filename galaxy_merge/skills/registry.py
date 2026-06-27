from pathlib import Path
from typing import Any

from galaxy_merge.cache.store import CacheStore
from galaxy_merge.cache.keys import skill_cache_key, hash_skill
from galaxy_merge.skills.discovery import SkillDiscovery
from galaxy_merge.skills.matcher import SkillMatcher


class SkillRegistry:
    def __init__(self, cache_dir: Path | None = None):
        self.discovery = SkillDiscovery()
        self.matcher = SkillMatcher()
        self._skills: list[dict[str, Any]] = []
        self._cache = CacheStore(cache_dir / "skill_matches") if cache_dir else None

    def load(self) -> None:
        self._skills = self.discovery.discover()

    def search(self, query: str) -> list[dict[str, Any]]:
        if self._cache:
            key = skill_cache_key("workspace", query)
            cached = self._cache.get(key)
            if cached is not None:
                return cached
        result = self.matcher.match(self._skills, query)
        if self._cache:
            key = skill_cache_key("workspace", query, hash_skill("all", query))
            self._cache.set(key, result, ttl_seconds=600)
        return result

    def list_all(self) -> list[dict[str, Any]]:
        return self._skills

    def count(self) -> int:
        return len(self._skills)
