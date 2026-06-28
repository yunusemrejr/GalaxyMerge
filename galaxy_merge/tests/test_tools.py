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

    @pytest.mark.asyncio
    async def test_relative_mutation_paths_are_checked_against_workroot(self, tmp_path, monkeypatch):
        # Given: the process cwd is outside the WorkRoot.
        from galaxy_merge.safety.governor import SafetyGovernor
        from galaxy_merge.safety.audit import SafetyAudit
        from galaxy_merge.tools.kernel import ToolKernel
        from galaxy_merge.tools.file_tools import make_file_tools

        workroot = tmp_path / "project"
        outside = tmp_path / "outside"
        workroot.mkdir()
        outside.mkdir()
        audit = SafetyAudit(workroot / ".gm" / "safety" / "audit.jsonl")
        gov = SafetyGovernor(workroot, workroot / ".gm", audit)
        kernel = ToolKernel(gov)
        for schema, handler in make_file_tools(workroot):
            kernel.register(schema, handler)
        monkeypatch.chdir(outside)

        # When: a relative path mutation is executed through the native kernel.
        result = await kernel.execute("file.write", {
            "path": "src/result.txt",
            "content": "ok",
            "expected_hash": "",
        })

        # Then: safety permits the WorkRoot-local target and the file is written there.
        assert result.success is True
        assert (workroot / "src" / "result.txt").read_text() == "ok"
        assert not (outside / "src" / "result.txt").exists()

    @pytest.mark.asyncio
    async def test_required_public_safety_tools_are_registered(self, tmp_path):
        # Given: an initialized orchestrator tool registry.
        from galaxy_merge.core.orchestrator import Orchestrator
        from galaxy_merge.core.session import Session, init_gm_dir

        init_gm_dir(tmp_path)
        session = Session(tmp_path)
        session.save_state()
        repo_root = Path(__file__).resolve().parents[2]
        orchestrator = Orchestrator(
            session,
            repo_root / "config",
            repo_root,
        )

        # When: the native tool schemas are listed.
        await orchestrator.initialize()
        tools = {tool["name"] for tool in orchestrator.tool_kernel.list_tools()}

        # Then: public release safety is available inside the native tool kernel.
        assert "secret.scan" in tools
        assert "repo.public_safety.audit" in tools
