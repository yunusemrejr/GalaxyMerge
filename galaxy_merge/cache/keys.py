import hashlib
import json
from typing import Any


CONFIG_HASH: str = ""
TOOL_VERSION: str = "0.1.0"
SAFETY_POLICY_HASH: str = ""
WORKROOT_HASH: str = ""


def set_config_hash(hash_val: str) -> None:
    global CONFIG_HASH
    CONFIG_HASH = hash_val


def set_safety_policy_hash(hash_val: str) -> None:
    global SAFETY_POLICY_HASH
    SAFETY_POLICY_HASH = hash_val


def set_workroot_hash(hash_val: str) -> None:
    global WORKROOT_HASH
    WORKROOT_HASH = hash_val


def _full_cache_key(prefix: str, *parts: str) -> str:
    """Build a cache key with workspace, config, safety, and tool version entropy."""
    raw = ":".join(
        [
            prefix,
            WORKROOT_HASH,
            CONFIG_HASH,
            SAFETY_POLICY_HASH,
            TOOL_VERSION,
            *parts,
        ]
    )
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def provider_cache_key(
    provider_id: str,
    model: str,
    role: str,
    messages_hash: str,
    stable_prefix_hash: str = "",
    tool_schema_hash: str = "",
    output_schema_hash: str = "",
) -> str:
    """Cache key for provider responses.

    Includes stable_prefix_hash to distinguish cache-friendly requests.
    Includes tool_schema_hash and output_schema_hash to detect schema changes.
    """
    parts = [provider_id, model, role, messages_hash]
    if stable_prefix_hash:
        parts.append(f"sp:{stable_prefix_hash}")
    if tool_schema_hash:
        parts.append(f"ts:{tool_schema_hash}")
    if output_schema_hash:
        parts.append(f"os:{output_schema_hash}")
    return _full_cache_key("provider", *parts)


def file_cache_key(workroot_id: str, file_path: str, file_hash: str) -> str:
    return _full_cache_key("file", workroot_id, file_path, file_hash)


def skill_cache_key(workroot_id: str, query: str, skill_hash: str = "") -> str:
    return _full_cache_key("skill", workroot_id, query, skill_hash)


def fusion_cache_key(goal_hash: str, council_name: str) -> str:
    return _full_cache_key("fusion", council_name, goal_hash)


def web_cache_key(source: str, query_or_url: str) -> str:
    h = hashlib.sha256(query_or_url.encode()).hexdigest()[:16]
    return _full_cache_key("web", source, h)


def browser_cache_key(session_id: str, url: str, evidence_type: str) -> str:
    h = hashlib.sha256(url.encode()).hexdigest()[:16]
    return _full_cache_key("browser", session_id, h, evidence_type)


def github_cache_key(repo_url: str, ref: str = "", path: str = "") -> str:
    parts = [repo_url]
    if ref:
        parts.append(f"ref:{ref}")
    if path:
        parts.append(f"path:{path}")
    return _full_cache_key("github", *parts)


def command_cache_key(command: str, cwd_hash: str, env_policy_hash: str = "") -> str:
    cmd_hash = hashlib.sha256(command.encode()).hexdigest()[:16]
    return _full_cache_key("command", cmd_hash, cwd_hash, env_policy_hash)


def compaction_cache_key(session_id: str, reason: str, model_id: str, role: str) -> str:
    return _full_cache_key("compaction", session_id, reason, model_id, role)


def hash_messages(messages: list[dict[str, str]]) -> str:
    """Deterministic hash of a messages list. Uses sort_keys for canonical JSON."""
    raw = json.dumps(messages, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def hash_messages_with_stable_prefix(
    messages: list[dict[str, str]], stable_prefix_hash: str
) -> str:
    """Hash messages including stable prefix identifier for cache discrimination."""
    raw = json.dumps(
        {"stable_prefix_hash": stable_prefix_hash, "messages": messages}, sort_keys=True
    )
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def hash_goal(goal: str) -> str:
    return hashlib.sha256(goal.encode()).hexdigest()[:16]


def hash_skill(skill_name: str, query: str) -> str:
    raw = f"{skill_name}:{query}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def hash_tool_schemas(schemas: list[dict[str, Any]]) -> str:
    """Deterministic hash of tool schemas for cache invalidation."""
    raw = json.dumps(schemas, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def hash_output_schema(schema: dict[str, Any]) -> str:
    """Deterministic hash of an output schema."""
    raw = json.dumps(schema, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def hash_file_content(content: str) -> str:
    """SHA-256 hash of file content (first 16 hex chars)."""
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def hash_prompt_assembly(segment_hashes: list[str]) -> str:
    """Hash of an ordered list of segment hashes."""
    raw = "|".join(segment_hashes)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def hash_config_dict(config: dict[str, Any]) -> str:
    """Deterministic hash of a config dict for cache key entropy."""
    raw = json.dumps(config, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]
