import json
from pathlib import Path
from typing import Any

from galaxy_merge.core.session import Session
from galaxy_merge.core.goal import GoalEngine
from galaxy_merge.core.events import EventLog
from galaxy_merge.core.planner import Planner
from galaxy_merge.tools.kernel import ToolKernel
from galaxy_merge.safety.governor import SafetyGovernor
from galaxy_merge.safety.sandbox import Sandbox
from galaxy_merge.safety.audit import SafetyAudit
from galaxy_merge.providers.registry import ProviderRegistry
from galaxy_merge.fusion.router import FusionRouter
from galaxy_merge.fusion.synthesizer import Synthesizer
from galaxy_merge.fusion.reviewer import review_fusion_result
from galaxy_merge.fusion.schemas import ROLE_SCHEMAS
from galaxy_merge.workspace.indexer import WorkspaceIndexer
from galaxy_merge.workspace.root import analyze_workroot
from galaxy_merge.memory.project_memory import ProjectMemory
from galaxy_merge.memory.session_memory import SessionMemory
from galaxy_merge.memory.retrieval import MemoryRetriever
from galaxy_merge.memory.compaction import Compactor
from galaxy_merge.skills.registry import SkillRegistry
from galaxy_merge.locations.classifier import LocationClassifier
from galaxy_merge.locations.registry import LocationRegistry
from galaxy_merge.locations.deployment_policy import DeploymentPolicy


class Orchestrator:
    def __init__(self, session: Session, config_dir: Path, install_dir: Path | None = None):
        self.session = session
        self.config_dir = config_dir
        self.install_dir = install_dir
        self.goal_engine = GoalEngine()
        self.planner = Planner()
        self.event_log = session.event_log
        self.safety_audit = SafetyAudit(session.gm_dir / "safety" / "blocked_actions.jsonl")
        self.safety = SafetyGovernor(session.workroot, session.gm_dir, self.safety_audit)
        self.sandbox = Sandbox(session.workroot)
        self.tool_kernel = ToolKernel(self.safety, self.event_log)
        self.providers = ProviderRegistry(config_dir)
        self.fusion_router = FusionRouter(self.providers, config_dir)
        self.synthesizer = Synthesizer()
        self.fusion_config: dict[str, Any] = {}
        self.indexer = WorkspaceIndexer(session.workroot)
        self.project_memory = ProjectMemory(session.gm_dir)
        self.session_memory = SessionMemory(session.session_dir)
        self.memory_retriever = MemoryRetriever(session.gm_dir)
        self.compactor = Compactor(session.gm_dir)
        self.skill_registry = SkillRegistry(session.gm_dir)
        self.location_classifier = LocationClassifier(session.workroot, session.gm_dir, install_dir)
        self.location_registry = LocationRegistry(session.gm_dir)
        self.deployment_policy = DeploymentPolicy(session.gm_dir)
        self._initialized = False

    async def initialize(self) -> None:
        if self._initialized:
            return

        self.providers.load()
        self.skill_registry.load()
        self.location_registry.init_from_project(self.session.workroot, self.session.gm_dir)
        self.fusion_config = self._load_fusion_config()

        workspace_info = analyze_workroot(self.session.workroot)
        self.session_memory.add_entry("workspace_info", workspace_info)

        self.event_log.emit("workroot_detected", session_id=self.session.session_id, workroot=str(self.session.workroot))
        self._register_tools()

        self._initialized = True
        self.event_log.emit("session_started", session_id=self.session.session_id)

    def _load_fusion_config(self) -> dict[str, Any]:
        path = self.config_dir / "fusion.json"
        if path.exists():
            try:
                import json
                return json.loads(path.read_text())
            except (json.JSONDecodeError, OSError):
                pass
        return {"max_parallel_calls": 4, "timeout_seconds": 180, "roles": {}}

    def _register_tools(self) -> None:
        from galaxy_merge.tools.file_tools import make_file_tools
        for schema, handler in make_file_tools(self.session.workroot):
            self.tool_kernel.register(schema, handler)

        from galaxy_merge.tools.shell_tools import make_shell_tools
        for schema, handler in make_shell_tools(self.session.workroot, self.safety, self.sandbox,
                                                self.location_classifier, self.deployment_policy):
            self.tool_kernel.register(schema, handler)

        from galaxy_merge.tools.git_tools import make_git_tools
        for schema, handler in make_git_tools(self.session.workroot):
            self.tool_kernel.register(schema, handler)

        from galaxy_merge.tools.memory_tools import make_memory_tools
        for schema, handler in make_memory_tools(self.session.gm_dir):
            self.tool_kernel.register(schema, handler)

        from galaxy_merge.tools.notes_tools import make_notes_tools
        for schema, handler in make_notes_tools(self.session.gm_dir):
            self.tool_kernel.register(schema, handler)

        from galaxy_merge.tools.skill_tools import make_skill_tools
        for schema, handler in make_skill_tools(self.skill_registry):
            self.tool_kernel.register(schema, handler)

        from galaxy_merge.tools.index_tools import make_index_tools
        for schema, handler in make_index_tools(self.session.workroot):
            self.tool_kernel.register(schema, handler)

        from galaxy_merge.tools.verification_tools import make_verification_tools
        for schema, handler in make_verification_tools(self.session.workroot):
            self.tool_kernel.register(schema, handler)

        from galaxy_merge.tools.web_tools import make_web_tools
        for schema, handler in make_web_tools(self.session.gm_dir):
            self.tool_kernel.register(schema, handler)

        from galaxy_merge.tools.github_tools import make_github_tools
        for schema, handler in make_github_tools(self.session.gm_dir):
            self.tool_kernel.register(schema, handler)

        from galaxy_merge.tools.location_tools import make_location_tools
        for schema, handler in make_location_tools(self.session.workroot, self.session.gm_dir, self.install_dir):
            self.tool_kernel.register(schema, handler)

        from galaxy_merge.tools.browser_tools import make_browser_tools
        for schema, handler in make_browser_tools(self.session.gm_dir, self.session.session_id):
            self.tool_kernel.register(schema, handler)

        from galaxy_merge.tools.provider_tools import make_provider_tools
        for schema, handler in make_provider_tools(self.providers):
            self.tool_kernel.register(schema, handler)

        from galaxy_merge.tools.council_tools import make_council_tools
        for schema, handler in make_council_tools(self.providers, self.fusion_config):
            self.tool_kernel.register(schema, handler)

        from galaxy_merge.tools.completion_tools import make_completion_tools
        for schema, handler in make_completion_tools():
            self.tool_kernel.register(schema, handler)

    async def execute_goal(self, goal: str) -> dict[str, Any]:
        self.memory_retriever.clear_for_new_goal()
        self.session.set_goal(goal)
        self.session_memory.add_entry("goal", goal)
        self.event_log.emit("goal_received", session_id=self.session.session_id, goal=goal)

        parsed = self.goal_engine.parse(goal)
        self.session._state["status"] = "understanding"
        self.session.save_state()
        self.event_log.emit("goal_parsed", session_id=self.session.session_id, task_type=parsed.get("task_type", ""))

        memory_context = self.memory_retriever.get_context_for_goal(goal)
        if memory_context.get("notes"):
            self.event_log.emit("note_loaded", session_id=self.session.session_id, notes_count=len(memory_context.get("notes", "")))
        if memory_context.get("injected_notes"):
            self.event_log.emit("note_loaded", session_id=self.session.session_id, injected=memory_context["injected_notes"])
        workspace_info = analyze_workroot(self.session.workroot)

        plan = self.planner.create_plan(parsed)
        self.session._state["status"] = "planning"
        self.session.save_state()

        matched_skills = self.skill_registry.search(goal)
        if matched_skills:
            self.event_log.emit("skill_selected", session_id=self.session.session_id, skills=[s["name"] for s in matched_skills[:3]])

        self.event_log.emit("council_started", session_id=self.session.session_id, task_type=parsed.get("task_type", ""))
        council = self.fusion_router.create_council(parsed.get("task_type", "small_edit"), goal, event_log=self.event_log)
        council_results = await council.execute()
        self.event_log.emit("council_completed", session_id=self.session.session_id, roles=list(council_results.keys()))

        self.event_log.emit("fusion_started", session_id=self.session.session_id)
        fused = self.synthesizer.fuse(council_results)
        self.event_log.emit("fusion_completed", session_id=self.session.session_id, changes_proposed=fused.get("changes_proposed", 0))

        self.session._state["status"] = "executing"
        self.session.save_state()
        execution_results = []
        for change in fused.get("plan", []):
            tool_name = change.get("tool", "")
            params = change.get("params", {})
            if tool_name:
                loc = self.location_classifier.classify(params.get("path", tool_name), "path")
                if loc["classification"] in ("galaxy_merge_app_codebase",):
                    continue
                self.event_log.emit("tool_call_started", session_id=self.session.session_id, tool=tool_name)
                result = await self.tool_kernel.execute(tool_name, params, self.session.session_id)
                self.event_log.emit(
                    "tool_call_completed" if result.success else "tool_call_blocked",
                    session_id=self.session.session_id,
                    tool=tool_name,
                    status="success" if result.success else "blocked",
                    duration_ms=result.data.get("_duration_ms", 0) if result.data else 0,
                )
                execution_results.append({"tool": tool_name, "success": result.success, "blocked": result.blocked})

        self.session._state["status"] = "testing"
        self.session.save_state()
        self.event_log.emit("verification_started", session_id=self.session.session_id)
        verification = await self._verify(fused)
        self.event_log.emit("verification_completed", session_id=self.session.session_id, passed=verification.get("passed", False))

        review = review_fusion_result(fused)
        complete = verification.get("passed", False) and review.get("approved", False)

        self.event_log.emit("completion_review_started", session_id=self.session.session_id)
        if complete:
            self.session._state["status"] = "complete"
            self.session.mark_completed()
            self.session_memory.add_entry("completion", {"status": "complete"})
            self.event_log.emit("completion_accepted", session_id=self.session.session_id)
            self._promote_to_memory(goal, fused, verification)
        else:
            self.session._state["status"] = "failed_safe"
            self.session_memory.add_entry("completion", {
                "status": "incomplete",
                "issues": verification.get("issues", []) + review.get("issues", []),
            })
            self.event_log.emit("completion_rejected", session_id=self.session.session_id)

        return {
            "goal": goal,
            "parsed": parsed,
            "complete": complete,
            "plan": plan,
            "fusion": fused,
            "verification": verification,
            "review": review,
            "execution_results": execution_results,
            "skills_matched": [s["name"] for s in matched_skills[:3]],
        }

    def _promote_to_memory(self, goal: str, fused: dict[str, Any], verification: dict[str, Any]) -> None:
        if fused.get("changes_proposed", 0) > 0:
            files = set()
            for change in fused.get("plan", []):
                fp = change.get("params", {}).get("path", "")
                if fp:
                    files.add(fp)
            if files:
                self.project_memory.record_fact(f"changed files: {', '.join(sorted(files))}", source="session")
        if verification.get("passed"):
            test_commands = [c for c in fused.get("summary", "").split() if "test" in c.lower()]
            if test_commands:
                self.project_memory.record_lesson(f"verified with: {' '.join(test_commands)}", category="testing")
        self.project_memory.record_fact(f"completed goal: {goal[:100]}", source="session")

    async def _run_planning(self, task_type: str, goal: str, memory: dict[str, Any], workspace: dict[str, Any]) -> dict[str, Any]:
        return {"task_type": task_type, "goal": goal, "workspace": workspace}

    async def _run_scout(self, plan: dict[str, Any]) -> dict[str, Any]:
        return {"status": "skipped"}

    async def _verify(self, fused: dict[str, Any]) -> dict[str, Any]:
        issues = []
        if not fused.get("plan"):
            issues.append("no executable plan produced")
        if fused.get("errors"):
            issues.extend(f"fusion error: {error}" for error in fused.get("errors", []))
        if fused.get("schema_errors"):
            issues.extend(f"schema error: {error}" for error in fused.get("schema_errors", []))
        for change in fused.get("plan", []):
            path = change.get("params", {}).get("path", "")
            if path:
                target = (self.session.workroot / path).resolve()
                if not target.exists():
                    issues.append(f"planned file does not exist: {path}")
                    continue
                ext = target.suffix
                if ext == ".py":
                    import subprocess
                    r = subprocess.run(
                        ["python3", "-m", "py_compile", str(target)],
                        capture_output=True, text=True, timeout=15,
                    )
                    if r.returncode != 0:
                        issues.append(f"syntax error in {path}: {r.stderr[:200]}")
                elif ext in (".js", ".ts", ".tsx", ".jsx"):
                    import subprocess
                    r = subprocess.run(
                        ["node", "--check", str(target)],
                        capture_output=True, text=True, timeout=15,
                    )
                    if r.returncode != 0:
                        issues.append(f"syntax error in {path}: {r.stderr[:200]}")
        return {"passed": len(issues) == 0, "issues": issues}
