import pytest
from pathlib import Path

from galaxy_merge.tools.schemas import ToolSchema, ToolResult


class TestToolSchemas:
    def test_schema_creation(self):
        schema = ToolSchema("test.tool", "A test tool", mutates=False)
        d = schema.to_dict()
        assert d["name"] == "test.tool"
        assert d["mutates"] is False

    def test_tool_result_success(self):
        r = ToolResult(success=True, data={"key": "value"})
        d = r.to_dict()
        assert d["success"] is True
        assert d["data"]["key"] == "value"

    def test_tool_result_error(self):
        r = ToolResult(success=False, error="something went wrong")
        assert r.error == "something went wrong"


class TestToolKernel:
    @pytest.mark.asyncio
    async def test_register_and_list(self):
        from galaxy_merge.safety.governor import SafetyGovernor
        from galaxy_merge.safety.audit import SafetyAudit
        from galaxy_merge.tools.kernel import ToolKernel
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            audit = SafetyAudit(tmp / "audit.jsonl")
            gov = SafetyGovernor(tmp, tmp / ".gm", audit)
            kernel = ToolKernel(gov)

            schema = ToolSchema("test.hello", "Says hello")
            async def handler(name: str = "world"):
                return ToolResult(success=True, data={"message": f"hello {name}"})

            kernel.register(schema, handler)

            tools = kernel.list_tools()
            assert len(tools) == 1
            assert tools[0]["name"] == "test.hello"

    @pytest.mark.asyncio
    async def test_execute_unknown_tool(self):
        from galaxy_merge.safety.governor import SafetyGovernor
        from galaxy_merge.safety.audit import SafetyAudit
        from galaxy_merge.tools.kernel import ToolKernel
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            audit = SafetyAudit(tmp / "audit.jsonl")
            gov = SafetyGovernor(tmp, tmp / ".gm", audit)
            kernel = ToolKernel(gov)
            result = await kernel.execute("nonexistent")
            assert result.success is False
            assert "unknown tool" in result.error
