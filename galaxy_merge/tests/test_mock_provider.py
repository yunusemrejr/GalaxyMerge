"""Unit tests for MockProvider — deterministic test infrastructure."""

import pytest

from galaxy_merge.providers.mock import MockProvider

pytestmark = [pytest.mark.unit]


class TestMockProvider:
    @pytest.mark.asyncio
    async def test_returns_configured_response(self):
        provider = MockProvider("test", {"responses": {"planner": {"steps": ["a"]}}})
        result = await provider.chat_completion(
            [{"role": "system", "content": "You are the planner role"}],
            "test-model",
        )
        assert result["success"] is True
        assert "steps" in result["content"]

    @pytest.mark.asyncio
    async def test_returns_default_response_for_unknown_role(self):
        provider = MockProvider("test", {})
        result = await provider.chat_completion(
            [{"role": "system", "content": "unknown role"}],
            "test-model",
        )
        assert result["success"] is True
        assert "mock response" in result["content"]

    @pytest.mark.asyncio
    async def test_returns_failure_when_configured(self):
        provider = MockProvider(
            "test", {"failures": {"planner": {"error": "timeout", "success": False}}}
        )
        result = await provider.chat_completion(
            [{"role": "system", "content": "You are the planner role"}],
            "test-model",
        )
        assert result["success"] is False
        assert "timeout" in result["error"]

    @pytest.mark.asyncio
    async def test_returns_string_failure(self):
        provider = MockProvider("test", {"failures": {"planner": "network error"}})
        result = await provider.chat_completion(
            [{"role": "system", "content": "You are the planner role"}],
            "test-model",
        )
        assert result["success"] is False
        assert "network error" in result["error"]

    @pytest.mark.asyncio
    async def test_tracks_call_history(self):
        provider = MockProvider("test", {})
        await provider.chat_completion(
            [{"role": "system", "content": "You are the planner role"}],
            "model-a",
        )
        await provider.chat_completion(
            [{"role": "system", "content": "You are the reviewer role"}],
            "model-b",
        )
        assert len(provider.call_history) == 2
        assert provider.call_history[0]["role"] == "planner"
        assert provider.call_history[1]["role"] == "reviewer"

    @pytest.mark.asyncio
    async def test_set_role_response(self):
        provider = MockProvider("test", {})
        provider.set_role_response("scout", {"files": ["a.py"]})
        result = await provider.chat_completion(
            [{"role": "system", "content": "You are the scout role"}],
            "test-model",
        )
        assert "files" in result["content"]

    @pytest.mark.asyncio
    async def test_set_role_failure(self):
        provider = MockProvider("test", {})
        provider.set_role_failure("scout", "rate limited")
        result = await provider.chat_completion(
            [{"role": "system", "content": "You are the scout role"}],
            "test-model",
        )
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_check_health_returns_healthy(self):
        provider = MockProvider("test", {})
        result = await provider.check_health()
        assert result is True

    def test_extract_role_from_system_message(self):
        provider = MockProvider("test", {})
        messages = [{"role": "system", "content": "You are the implementer role."}]
        role = provider._extract_role(messages)
        assert role == "implementer"

    def test_extract_role_synthesizer(self):
        provider = MockProvider("test", {})
        messages = [{"role": "system", "content": "You are the synthesizer role."}]
        role = provider._extract_role(messages)
        assert role == "synthesizer"

    def test_extract_role_empty_for_no_system(self):
        provider = MockProvider("test", {})
        messages = [{"role": "user", "content": "do something"}]
        role = provider._extract_role(messages)
        assert role == ""

    @pytest.mark.asyncio
    async def test_redacts_credentials_in_failure(self):
        provider = MockProvider(
            "test",
            {"failures": {"planner": "auth failed sk-1234567890abcdef1234567890abcdef"}},
        )
        result = await provider.chat_completion(
            [{"role": "system", "content": "You are the planner role"}],
            "test-model",
        )
        assert "sk-1234567890abcdef1234567890abcdef" not in result["error"]
        assert "REDACTED" in result["error"]

    @pytest.mark.asyncio
    async def test_call_history_records_provider(self):
        provider = MockProvider("my_provider", {})
        await provider.chat_completion(
            [{"role": "system", "content": "You are the planner role"}],
            "model-x",
        )
        assert provider.call_history[0]["provider"] == "my_provider"
        assert provider.call_history[0]["model"] == "model-x"
