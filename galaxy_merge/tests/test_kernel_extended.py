"""Unit tests for ToolKernel — safety gating, async/sync handlers, error wrapping."""

import pytest

from galaxy_merge.tools.kernel import ToolKernel
from galaxy_merge.tools.schemas import ToolSchema, ToolResult
from galaxy_merge.safety.governor import SafetyGovernor
from galaxy_merge.safety.audit import SafetyAudit
from galaxy_merge.core.errors import SafetyBlocked

pytestmark = [pytest.mark.unit]


def _make_kernel(tmp_path):
    audit = SafetyAudit(tmp_path / "audit.jsonl")
    gov = SafetyGovernor(tmp_path, tmp_path / ".gm", audit)
    return ToolKernel(gov)


class TestToolKernelExecute:
    @pytest.mark.asyncio
    async def test_execute_sync_handler(self, tmp_path):
        kernel = _make_kernel(tmp_path)

        def handler(x: int = 1):
            return ToolResult(success=True, data={"x": x})

        kernel.register(ToolSchema("calc.add", "Add numbers"), handler)
        result = await kernel.execute("calc.add", {"x": 42})
        assert result.success is True
        assert result.data["x"] == 42

    @pytest.mark.asyncio
    async def test_execute_async_handler(self, tmp_path):
        kernel = _make_kernel(tmp_path)

        async def handler(msg: str = "hi"):
            return ToolResult(success=True, data={"msg": msg})

        kernel.register(ToolSchema("async.test", "Async tool"), handler)
        result = await kernel.execute("async.test", {"msg": "hello"})
        assert result.success is True
        assert result.data["msg"] == "hello"

    @pytest.mark.asyncio
    async def test_execute_unknown_tool_returns_error(self, tmp_path):
        kernel = _make_kernel(tmp_path)
        result = await kernel.execute("nonexistent.tool")
        assert result.success is False
        assert "unknown tool" in result.error

    @pytest.mark.asyncio
    async def test_execute_adds_duration_to_result(self, tmp_path):
        kernel = _make_kernel(tmp_path)

        def handler():
            return ToolResult(success=True, data={})

        kernel.register(ToolSchema("fast.tool", "Fast"), handler)
        result = await kernel.execute("fast.tool")
        assert "_duration_ms" in result.data
        assert isinstance(result.data["_duration_ms"], int)

    @pytest.mark.asyncio
    async def test_execute_wraps_safety_blocked_exception(self, tmp_path):
        kernel = _make_kernel(tmp_path)

        def handler():
            raise SafetyBlocked("blocked by policy")

        kernel.register(ToolSchema("blocked.tool", "Blocked"), handler)
        result = await kernel.execute("blocked.tool")
        assert result.success is False
        assert result.blocked is True
        assert "blocked by policy" in result.error

    @pytest.mark.asyncio
    async def test_execute_wraps_generic_exception(self, tmp_path):
        kernel = _make_kernel(tmp_path)

        def handler():
            raise ValueError("something broke")

        kernel.register(ToolSchema("fail.tool", "Fails"), handler)
        result = await kernel.execute("fail.tool")
        assert result.success is False
        assert "something broke" in result.error

    @pytest.mark.asyncio
    async def test_safety_blocks_path_write(self, tmp_path):
        kernel = _make_kernel(tmp_path)

        def handler(path: str = ""):
            return ToolResult(success=True, data={"written": path})

        kernel.register(
            ToolSchema(
                "file.write", "Write file", mutates=True, requires_safety=True
            ),
            handler,
        )
        result = await kernel.execute("file.write", {"path": "/etc/passwd"})
        assert result.success is False
        assert result.blocked is True

    @pytest.mark.asyncio
    async def test_safety_allows_workroot_write(self, tmp_path):
        kernel = _make_kernel(tmp_path)

        def handler(path: str = "", content: str = ""):
            return ToolResult(success=True, data={"path": path})

        kernel.register(
            ToolSchema(
                "file.write", "Write file", mutates=True, requires_safety=True
            ),
            handler,
        )
        result = await kernel.execute(
            "file.write", {"path": "src/test.py", "content": "x"}
        )
        # Should pass safety (relative path inside workroot)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_non_mutating_tool_skips_safety(self, tmp_path):
        kernel = _make_kernel(tmp_path)

        def handler():
            return ToolResult(success=True, data={})

        kernel.register(
            ToolSchema("file.read", "Read file", mutates=False, requires_safety=True),
            handler,
        )
        result = await kernel.execute("file.read")
        assert result.success is True

    @pytest.mark.asyncio
    async def test_default_params_are_empty_dict(self, tmp_path):
        kernel = _make_kernel(tmp_path)
        received_params = {}

        def handler(**kwargs):
            received_params.update(kwargs)
            return ToolResult(success=True, data={})

        kernel.register(ToolSchema("param.test", "Test params"), handler)
        await kernel.execute("param.test")
        assert received_params == {}

    @pytest.mark.asyncio
    async def test_event_log_receives_tool_completed(self, tmp_path):
        from galaxy_merge.core.events import EventLog

        log = EventLog(tmp_path / "events.jsonl")
        audit = SafetyAudit(tmp_path / "audit.jsonl")
        gov = SafetyGovernor(tmp_path, tmp_path / ".gm", audit)
        kernel = ToolKernel(gov, event_log=log)

        def handler():
            return ToolResult(success=True, data={})

        kernel.register(ToolSchema("test.tool", "Test"), handler)
        await kernel.execute("test.tool", session_id="s1")
        events = log.replay()
        assert any(e["event"] == "tool_completed" for e in events)

    def test_get_schema_returns_schema(self, tmp_path):
        kernel = _make_kernel(tmp_path)
        schema = ToolSchema("test.tool", "A test tool")
        kernel.register(schema, lambda: ToolResult(success=True))
        assert kernel.get_schema("test.tool") is schema

    def test_get_schema_returns_none_for_unknown(self, tmp_path):
        kernel = _make_kernel(tmp_path)
        assert kernel.get_schema("nonexistent") is None

    def test_list_tools_returns_all_registered(self, tmp_path):
        kernel = _make_kernel(tmp_path)
        kernel.register(ToolSchema("a.tool", "A"), lambda: ToolResult(success=True))
        kernel.register(ToolSchema("b.tool", "B"), lambda: ToolResult(success=True))
        tools = kernel.list_tools()
        names = {t["name"] for t in tools}
        assert "a.tool" in names
        assert "b.tool" in names
