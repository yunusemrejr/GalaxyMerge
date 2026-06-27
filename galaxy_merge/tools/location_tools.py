from pathlib import Path
from typing import Any

from galaxy_merge.tools.schemas import ToolSchema, ToolResult
from galaxy_merge.locations.classifier import LocationClassifier
from galaxy_merge.locations.registry import LocationRegistry


def make_location_tools(workroot: Path, gm_dir: Path, install_dir: Path | None = None) -> list[tuple[ToolSchema, Any]]:
    classifier = LocationClassifier(workroot, gm_dir, install_dir)
    registry = LocationRegistry(gm_dir)

    async def location_classify(target: str, target_type: str = "path") -> ToolResult:
        result = classifier.classify(target, target_type)
        return ToolResult(success=True, data=result)

    async def location_registry_read() -> ToolResult:
        data = registry.to_dict()
        return ToolResult(success=True, data=data)

    return [
        (ToolSchema("location.classify", "Classify a path or command into a location class", parameters={
            "target": {"type": "string", "required": True},
            "target_type": {"type": "string", "default": "path"},
        }), location_classify),
        (ToolSchema("location.registry.read", "Read the current location registry"), location_registry_read),
    ]
