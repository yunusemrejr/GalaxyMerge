"""Unit tests for cache key generation and cache store.

Focused tests for the cache module's key functions and CacheStore class.
"""

import time

import pytest

from galaxy_merge.cache.keys import (
    provider_cache_key,
    file_cache_key,
    skill_cache_key,
    fusion_cache_key,
    web_cache_key,
    hash_messages,
    hash_goal,
    hash_skill,
)
from galaxy_merge.cache.store import CacheStore

pytestmark = [pytest.mark.unit]


class TestCacheKeys:
    def test_provider_cache_key_deterministic(self):
        key1 = provider_cache_key("openai", "gpt-4", "coder", "abc123")
        key2 = provider_cache_key("openai", "gpt-4", "coder", "abc123")
        assert key1 == key2

    def test_provider_cache_key_different_for_different_models(self):
        key1 = provider_cache_key("openai", "gpt-4", "coder", "abc123")
        key2 = provider_cache_key("openai", "gpt-3.5-turbo", "coder", "abc123")
        assert key1 != key2

    def test_file_cache_key_format(self):
        from galaxy_merge.cache.keys import (
            set_workroot_hash,
            set_config_hash,
            set_safety_policy_hash,
        )

        set_workroot_hash("wr123")
        set_config_hash("cfg456")
        set_safety_policy_hash("safe789")
        key = file_cache_key("proj123", "/src/main.py", "sha256abc")
        # Key is now a full SHA-256 hash (32 hex chars)
        assert len(key) == 32
        assert all(c in "0123456789abcdef" for c in key)

    def test_file_cache_key_deterministic(self):
        from galaxy_merge.cache.keys import (
            set_workroot_hash,
            set_config_hash,
            set_safety_policy_hash,
        )

        set_workroot_hash("wr123")
        set_config_hash("cfg456")
        set_safety_policy_hash("safe789")
        key1 = file_cache_key("proj123", "/src/main.py", "sha256abc")
        key2 = file_cache_key("proj123", "/src/main.py", "sha256abc")
        assert key1 == key2

    def test_file_cache_key_different_inputs_different_key(self):
        from galaxy_merge.cache.keys import (
            set_workroot_hash,
            set_config_hash,
            set_safety_policy_hash,
        )

        set_workroot_hash("wr123")
        set_config_hash("cfg456")
        set_safety_policy_hash("safe789")
        key1 = file_cache_key("proj123", "/src/main.py", "sha256abc")
        key2 = file_cache_key("proj123", "/src/main.py", "sha256xyz")
        assert key1 != key2

    def test_skill_cache_key_deterministic(self):
        from galaxy_merge.cache.keys import (
            set_workroot_hash,
            set_config_hash,
            set_safety_policy_hash,
        )

        set_workroot_hash("wr123")
        set_config_hash("cfg456")
        set_safety_policy_hash("safe789")
        key = skill_cache_key("proj123", "how to fix bug")
        assert len(key) == 32

    def test_fusion_cache_key_deterministic(self):
        from galaxy_merge.cache.keys import (
            set_workroot_hash,
            set_config_hash,
            set_safety_policy_hash,
        )

        set_workroot_hash("wr123")
        set_config_hash("cfg456")
        set_safety_policy_hash("safe789")
        key = fusion_cache_key("goalhash123", "council")
        assert len(key) == 32

    def test_web_cache_key_deterministic(self):
        from galaxy_merge.cache.keys import (
            set_workroot_hash,
            set_config_hash,
            set_safety_policy_hash,
        )

        set_workroot_hash("wr123")
        set_config_hash("cfg456")
        set_safety_policy_hash("safe789")
        key = web_cache_key("duckduckgo", "python tutorial")
        assert len(key) == 32

    def test_hash_messages_deterministic(self):
        messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"},
        ]
        h1 = hash_messages(messages)
        h2 = hash_messages(messages)
        assert h1 == h2

    def test_hash_messages_different_order_different_hash(self):
        messages1 = [{"role": "user", "content": "hello"}]
        messages2 = [{"role": "assistant", "content": "hi"}]
        assert hash_messages(messages1) != hash_messages(messages2)

    def test_hash_goal_deterministic(self):
        goal = "fix the bug in main.py"
        h1 = hash_goal(goal)
        h2 = hash_goal(goal)
        assert h1 == h2

    def test_hash_skill_deterministic(self):
        h1 = hash_skill("debugger", "find null pointer")
        h2 = hash_skill("debugger", "find null pointer")
        assert h1 == h2


class TestCacheStore:
    def test_cache_store_creates_dir(self, tmp_path):
        cache_dir = tmp_path / "cache"
        CacheStore(cache_dir)
        assert cache_dir.exists()

    def test_cache_store_get_set(self, tmp_path):
        cache_dir = tmp_path / "cache"
        store = CacheStore(cache_dir)
        store.set("mykey", {"data": 123})
        result = store.get("mykey")
        assert result == {"data": 123}

    def test_cache_store_get_missing(self, tmp_path):
        cache_dir = tmp_path / "cache"
        store = CacheStore(cache_dir)
        result = store.get("nonexistent")
        assert result is None

    def test_cache_store_invalidate(self, tmp_path):
        cache_dir = tmp_path / "cache"
        store = CacheStore(cache_dir)
        store.set("mykey", {"data": 123})
        store.invalidate("mykey")
        assert store.get("mykey") is None

    def test_cache_store_clear(self, tmp_path):
        cache_dir = tmp_path / "cache"
        store = CacheStore(cache_dir)
        store.set("key1", "value1")
        store.set("key2", "value2")
        store.set("key3", "value3")
        store.clear()
        assert store.get("key1") is None
        assert store.get("key2") is None
        assert store.get("key3") is None

    def test_cache_store_ttl_expiration(self, tmp_path):
        cache_dir = tmp_path / "cache"
        store = CacheStore(cache_dir)
        store.set("expiring_key", "value", ttl_seconds=0.1)
        assert store.get("expiring_key") == "value"
        time.sleep(0.15)
        assert store.get("expiring_key") is None
