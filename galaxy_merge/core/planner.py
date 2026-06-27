from typing import Any


class Planner:
    def create_plan(self, parsed_goal: dict[str, Any]) -> dict[str, Any]:
        task_type = parsed_goal.get("task_type", "small_edit")
        files = parsed_goal.get("mentioned_files", [])

        plan = {
            "goal": parsed_goal.get("goal", ""),
            "task_type": task_type,
            "steps": [],
            "relevant_files": files,
            "completion_criteria": [],
        }

        if task_type == "bug_fix":
            plan["steps"] = [
                "identify the bug location",
                "understand the failing behavior",
                "apply minimal fix",
                "verify fix with tests",
            ]
            plan["completion_criteria"] = [
                "bug is fixed",
                "tests pass",
            ]
        elif task_type == "feature":
            plan["steps"] = [
                "understand existing code structure",
                "design implementation approach",
                "implement feature",
                "add tests",
                "verify",
            ]
            plan["completion_criteria"] = [
                "feature works",
                "tests pass",
            ]
        elif task_type == "large_refactor":
            plan["steps"] = [
                "map current architecture",
                "design target architecture",
                "implement refactor incrementally",
                "verify no regressions",
            ]
            plan["completion_criteria"] = [
                "refactor complete",
                "existing tests pass",
            ]
        else:
            plan["steps"] = [
                "understand the change needed",
                "apply change",
                "verify",
            ]
            plan["completion_criteria"] = [
                "change applied correctly",
            ]

        return plan
