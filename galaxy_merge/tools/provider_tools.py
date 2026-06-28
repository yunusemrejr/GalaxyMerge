from typing import Any

from galaxy_merge.tools.schemas import ToolSchema, ToolResult


def make_provider_tools(provider_registry) -> list[tuple[ToolSchema, Any]]:
    async def provider_call(
        provider_id: str,
        model: str,
        messages: list[dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int | None = None,
    ) -> ToolResult:
        provider = provider_registry.get(provider_id)
        if not provider:
            return ToolResult(
                success=False, error=f"provider '{provider_id}' not found"
            )
        if not provider.healthy:
            return ToolResult(
                success=False, error=f"provider '{provider_id}' is unhealthy"
            )

        result = await provider.chat_completion(
            messages, model, temperature=temperature
        )
        if result.get("success"):
            return ToolResult(
                success=True,
                data={
                    "provider": provider_id,
                    "model": result.get("model", model),
                    "content": result.get("content", ""),
                    "usage": result.get("usage", {}),
                },
            )
        return ToolResult(
            success=False, error=result.get("error", "provider call failed")
        )

    return [
        (
            ToolSchema(
                "provider.call",
                "Call a provider directly with a chat completion request",
                parameters={
                    "provider_id": {"type": "string", "required": True},
                    "model": {"type": "string", "required": True},
                    "messages": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "role": {"type": "string"},
                                "content": {"type": "string"},
                            },
                        },
                        "required": True,
                    },
                    "temperature": {"type": "number", "default": 0.3},
                    "max_tokens": {"type": "integer", "default": None},
                },
            ),
            provider_call,
        ),
    ]
