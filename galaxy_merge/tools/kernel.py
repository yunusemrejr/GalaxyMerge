import inspect
import time
from pathlib import Path
from typing import Any, Callable, Coroutine

from galaxy_merge.tools.schemas import ToolSchema, ToolResult
from galaxy_merge.safety.governor import SafetyGovernor
from galaxy_merge.core.errors import SafetyBlocked


ToolHandler = Callable[..., ToolResult | Coroutine[Any, Any, ToolResult]]


class ToolKernel:
    def __init__(self, safety_governor: SafetyGovernor, event_log=None):
        self.safety = safety_governor
        self._event_log = event_log
        self._tools: dict[str, tuple[ToolSchema, ToolHandler]] = {}

    def register(self, schema: ToolSchema, handler: ToolHandler) -> None:
        self._tools[schema.name] = (schema, handler)

    def get_schema(self, name: str) -> ToolSchema | None:
        pair = self._tools.get(name)
        return pair[0] if pair else None

    def list_tools(self) -> list[dict[str, Any]]:
        return [schema.to_dict() for schema, _ in self._tools.values()]

    async def execute(
        self,
        name: str,
        params: dict[str, Any] | None = None,
        session_id: str = "",
    ) -> ToolResult:
        pair = self._tools.get(name)
        if not pair:
            self._emit_event("tool_unknown", session_id=session_id, tool=name)
            return ToolResult(success=False, error=f"unknown tool: {name}")

        schema, handler = pair
        params = params or {}

        if schema.requires_safety and schema.mutates:
            target = params.get("path", params.get("target", ""))
            if target:
                safety_check = self.safety.check_path_write(self._safety_target(str(target)))
                if safety_check["decision"] == "block":
                    self._emit_event(
                        "tool_blocked",
                        session_id=session_id,
                        tool=name,
                        reason=safety_check["reason"],
                    )
                    return ToolResult(
                        success=False,
                        error=f"safety blocked: {safety_check['reason']}",
                        blocked=True,
                    )

        start = time.monotonic()
        try:
            raw = handler(**params)
            if inspect.iscoroutine(raw):
                result = await raw
            else:
                result = raw  # type: ignore[assignment]
            duration = int((time.monotonic() - start) * 1000)
            result.data = {
                **(result.data or {}),
                "_duration_ms": duration,
            }
            self._emit_event(
                "tool_completed",
                session_id=session_id,
                tool=name,
                mutates=schema.mutates,
                duration_ms=duration,
                success=result.success,
            )
            return result
        except SafetyBlocked as e:
            self._emit_event(
                "tool_blocked", session_id=session_id, tool=name, reason=str(e)
            )
            return ToolResult(success=False, error=str(e), blocked=True)
        except Exception as e:
            self._emit_event(
                "tool_failed", session_id=session_id, tool=name, error=str(e)
            )
            return ToolResult(success=False, error=str(e))

    def _emit_event(self, event: str, **kwargs: Any) -> None:
        if self._event_log:
            self._event_log.emit(event, **kwargs)

    def _safety_target(self, target: str) -> str:
        path = Path(target)
        if path.is_absolute():
            return str(path)
        return str((self.safety.workroot / path).resolve())
