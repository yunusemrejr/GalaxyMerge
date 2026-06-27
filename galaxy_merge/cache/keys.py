import hashlib
import json


CONFIG_HASH: str = ""
TOOL_VERSION: str = "0.1.0"


def set_config_hash(hash_val: str) -> None:
    global CONFIG_HASH
    CONFIG_HASH = hash_val


def provider_cache_key(provider_id: str, model: str, role: str, messages_hash: str) -> str:
    return f"provider:{provider_id}:{model}:{role}:{messages_hash}:v{TOOL_VERSION}:cfg{CONFIG_HASH}"


def file_cache_key(workroot_id: str, file_path: str, file_hash: str) -> str:
    return f"file:{workroot_id}:{file_path}:{file_hash}:v{TOOL_VERSION}:cfg{CONFIG_HASH}"


def skill_cache_key(workroot_id: str, query: str, skill_hash: str = "") -> str:
    return f"skill:{workroot_id}:{query}:{skill_hash}:v{TOOL_VERSION}:cfg{CONFIG_HASH}"


def fusion_cache_key(goal_hash: str, council_name: str) -> str:
    return f"fusion:{council_name}:{goal_hash}:v{TOOL_VERSION}:cfg{CONFIG_HASH}"


def web_cache_key(source: str, query_or_url: str) -> str:
    h = hashlib.sha256(query_or_url.encode()).hexdigest()[:16]
    return f"web:{source}:{h}:v{TOOL_VERSION}:cfg{CONFIG_HASH}"


def hash_messages(messages: list[dict[str, str]]) -> str:
    raw = json.dumps(messages, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def hash_goal(goal: str) -> str:
    return hashlib.sha256(goal.encode()).hexdigest()[:16]


def hash_skill(skill_name: str, query: str) -> str:
    raw = f"{skill_name}:{query}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]
