from typing import Any


class ToolSchema:
    def __init__(
        self,
        name: str,
        description: str,
        mutates: bool = False,
        requires_safety: bool = True,
        parameters: dict[str, Any] | None = None,
    ):
        self.name = name
        self.description = description
        self.mutates = mutates
        self.requires_safety = requires_safety
        self.parameters = parameters or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "mutates": self.mutates,
            "requires_safety": self.requires_safety,
            "parameters": self.parameters,
        }

    def __hash__(self) -> int:
        return hash(self.name)

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, ToolSchema):
            return self.name == other.name
        if isinstance(other, str):
            return self.name == other
        return False


class ToolResult:
    def __init__(
        self,
        success: bool,
        data: Any = None,
        error: str | None = None,
        blocked: bool = False,
    ):
        self.success = success
        self.data = data
        self.error = error
        self.blocked = blocked

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "blocked": self.blocked,
        }
