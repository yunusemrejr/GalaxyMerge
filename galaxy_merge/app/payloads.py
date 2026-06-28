"""Payload builders for Galaxy Merge API responses.

Kept separate from server.py for modularity.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from galaxy_merge.locations.classifier import LocationClassifier
from galaxy_merge.locations.registry import LocationRegistry
from galaxy_merge.safety.credential_policy import CredentialPolicy
from galaxy_merge.core.concurrency import read_active_port_map
from galaxy_merge.core.locks import atomic_write

APP_INSTALL_DIR = Path(__file__).resolve().parent.parent.parent


def build_locations_payload(
    workroot: Path, gm_dir: Path, app_install_dir: Path = APP_INSTALL_DIR
) -> dict[str, Any]:
    registry = LocationRegistry(gm_dir)
    registry.init_from_project(workroot, gm_dir)
    data = registry.to_dict()
    classifier = LocationClassifier(workroot, gm_dir, app_install_dir)
    classified = [
        classifier.classify(str(workroot), "path"),
        classifier.classify(str(gm_dir), "path"),
    ]
    for remote in data.get("remote_targets", []):
        classified.append(
            {
                "target": remote.get("id", ""),
                "classification": remote.get("classification", "unknown"),
                "host": remote.get("host", ""),
                "path": remote.get("path", ""),
                "repo": remote.get("repo", ""),
                "risk": "high"
                if remote.get("classification")
                in ("production_target", "staging_target")
                else "medium",
                "policy_decision": remote.get("write_policy", "blocked_by_default"),
                "is_remote": True,
                "is_production": remote.get("classification") == "production_target",
                "is_local": False,
            }
        )
    data["classified_locations"] = classified
    return data


def build_logs_payload(
    log_path: Path, limit: int = 500, offset: int = 0
) -> dict[str, Any]:
    safe_limit = max(1, min(limit, 2000))
    safe_offset = max(0, offset)
    if not log_path.exists():
        return {
            "lines": [],
            "total": 0,
            "offset": safe_offset,
            "limit": safe_limit,
            "truncated": False,
        }
    lines = log_path.read_text().splitlines()
    window = lines[safe_offset : safe_offset + safe_limit]
    return {
        "lines": window,
        "total": len(lines),
        "offset": safe_offset,
        "limit": safe_limit,
        "truncated": safe_offset + len(window) < len(lines),
    }


def build_notes_payload(
    notes_dir: Path, limit: int = 100, offset: int = 0
) -> dict[str, Any]:
    safe_limit = max(1, min(limit, 500))
    safe_offset = max(0, offset)
    if not notes_dir.exists():
        return {
            "notes": [],
            "total": 0,
            "offset": safe_offset,
            "limit": safe_limit,
            "truncated": False,
        }
    index = {}
    index_path = notes_dir / "index.json"
    if index_path.exists():
        try:
            index_data = json.loads(index_path.read_text())
            for item in index_data.get("notes", []):
                index[item.get("path", "").replace(".md", "")] = item
        except (json.JSONDecodeError, OSError):
            index = {}
    files = [
        f
        for f in sorted(notes_dir.iterdir())
        if f.suffix in (".md", ".txt", ".json") and f.name != "index.json"
    ]
    entries = []
    legacy_notes = {}
    for f in files[safe_offset : safe_offset + safe_limit]:
        content = f.read_text()
        meta = index.get(f.stem, {})
        entries.append(
            {
                "name": f.stem,
                "path": f.name,
                "content": content,
                "preview": content[:200],
                "id": meta.get("id", f"note_{f.stem}"),
                "title": meta.get("title", f.stem),
                "tags": meta.get("tags", []),
                "pinned": bool(meta.get("pinned", False)),
                "created_at": meta.get("created_at", ""),
                "updated_at": meta.get("updated_at", ""),
            }
        )
        legacy_notes[f.stem] = content
    return {
        **legacy_notes,
        "notes": entries,
        "total": len(files),
        "offset": safe_offset,
        "limit": safe_limit,
        "truncated": safe_offset + len(entries) < len(files),
    }


def _read_json_file(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return fallback


def _load_notes_index(notes_dir: Path) -> dict[str, Any]:
    index_path = notes_dir / "index.json"
    payload = _read_json_file(index_path, {"schema_version": 1, "notes": []})
    if not isinstance(payload, dict):
        return {"schema_version": 1, "notes": []}
    payload.setdefault("schema_version", 1)
    notes = payload.get("notes", [])
    if not isinstance(notes, list):
        payload["notes"] = []
    return payload


def _save_notes_index(notes_dir: Path, index: dict[str, Any]) -> None:
    index_path = notes_dir / "index.json"
    atomic_write(index_path, json.dumps(index, indent=2), _nested_lock=True)


def _upsert_note_index(
    notes_dir: Path,
    note_name: str,
    path: str,
    *,
    created_at: str | None = None,
    tags: list[str] | None = None,
    pinned: bool = False,
    title: str | None = None,
    updated_at: str | None = None,
) -> None:
    notes_dir.mkdir(parents=True, exist_ok=True)
    index = _load_notes_index(notes_dir)
    entries = index.setdefault("notes", [])
    normalized_path = path.strip()
    target = None
    for item in entries:
        if item.get("path") == normalized_path:
            target = item
            break
    if target is None:
        target = {
            "id": f"note_{note_name}",
            "path": normalized_path,
            "title": title or note_name,
            "created_at": created_at or datetime.now(timezone.utc).isoformat(),
            "updated_at": updated_at or datetime.now(timezone.utc).isoformat(),
            "tags": sorted(set(tags or [])),
            "pinned": pinned,
        }
        entries.append(target)
    else:
        if title is not None:
            target["title"] = title
        if created_at is not None:
            target["created_at"] = created_at
        target["updated_at"] = updated_at or datetime.now(timezone.utc).isoformat()
        if tags is not None:
            target["tags"] = sorted(set(tags))
        if pinned:
            target["pinned"] = pinned
        elif pinned is False:
            target["pinned"] = False
    _save_notes_index(notes_dir, index)


def _remove_note_from_index(notes_dir: Path, note_name: str) -> None:
    notes_dir.mkdir(parents=True, exist_ok=True)
    index = _load_notes_index(notes_dir)
    notes = index.get("notes", [])
    if not isinstance(notes, list):
        return
    target_name = f"{note_name}.md"
    index["notes"] = [item for item in notes if item.get("path") != target_name]
    _save_notes_index(notes_dir, index)


def _read_active_sessions(
    gm_dir: Path, current_session_id: str
) -> list[dict[str, Any]]:
    import time

    ports = read_active_port_map(gm_dir)
    now = time.time()
    hb_dir = gm_dir / "sessions" / "heartbeats"
    sessions: list[dict[str, Any]] = []
    seen: set[str] = set()
    for session_id, record in sorted(ports.items()):
        seen.add(session_id)
        state_path = gm_dir / "sessions" / session_id / "state.json"
        state = _read_json_file(state_path, {})
        hb = hb_dir / f"{session_id}.hb"
        hb_age = now - hb.stat().st_mtime if hb.exists() else None
        active = hb_age is not None and hb_age < 300
        sessions.append(
            {
                "session_id": session_id,
                "port": record.get("port"),
                "pid": record.get("pid"),
                "workroot": state.get("workroot", gm_dir.parent.as_posix()),
                "status": state.get("status", "unknown"),
                "goal": state.get("goal", ""),
                "active": bool(active),
                "heartbeat_age": round(hb_age, 1) if hb_age is not None else None,
                "error": state.get("error"),
                "goal_state": state.get("status", "unknown"),
                "last_heartbeat": record.get("updated_at"),
            }
        )

    if current_session_id not in seen:
        current_state = _read_json_file(
            gm_dir / "sessions" / current_session_id / "state.json", {}
        )
        hb = hb_dir / f"{current_session_id}.hb"
        hb_age = now - hb.stat().st_mtime if hb.exists() else None
        current_record = ports.get(current_session_id, {})
        sessions.append(
            {
                "session_id": current_session_id,
                "port": current_record.get("port"),
                "pid": current_record.get("pid"),
                "workroot": current_state.get("workroot", gm_dir.parent.as_posix()),
                "status": current_state.get("status", "unknown"),
                "goal": current_state.get("goal", ""),
                "active": hb_age is not None and hb_age < 300,
                "heartbeat_age": round(hb_age, 1) if hb_age is not None else None,
                "error": current_state.get("error"),
                "goal_state": current_state.get("status", "unknown"),
                "last_heartbeat": hb.stat().st_mtime if hb.exists() else None,
            }
        )

    sessions.sort(key=lambda item: (not item["active"], item["session_id"]))
    return sessions


def _redact_nested(value: Any, policy: CredentialPolicy) -> Any:
    if isinstance(value, str):
        return policy.redact(value)
    if isinstance(value, list):
        return [_redact_nested(item, policy) for item in value]
    if isinstance(value, dict):
        return {key: _redact_nested(item, policy) for key, item in value.items()}
    return value


def build_council_event_summary(
    events: list[dict[str, Any]], workroot: Path, limit: int = 200
) -> dict[str, Any]:
    policy = CredentialPolicy(workroot)
    recent = events[-max(1, min(limit, 1000)) :]
    rows_by_key: dict[tuple[str, str, str], dict[str, Any]] = {}
    provider_failures: list[dict[str, Any]] = []
    fallback_events: list[dict[str, Any]] = []

    for raw_event in recent:
        event = _redact_nested(raw_event, policy)
        event_name = event.get("event", "")
        role = event.get("role", "")
        provider_id = (
            event.get("provider_id")
            or event.get("provider")
            or event.get("to_provider", "")
        )
        model = event.get("model", "")
        key = (role, provider_id, model)

        if event_name == "provider_called":
            rows_by_key[key] = {
                "role": role,
                "provider": provider_id,
                "provider_id": provider_id,
                "model": model,
                "status": "called",
                "attempt": event.get("attempt"),
                "time": event.get("time"),
            }
        elif event_name == "role_execution_failed":
            rows_by_key[key] = {
                "role": role,
                "provider": provider_id,
                "provider_id": provider_id,
                "model": model,
                "status": "degraded",
                "error": event.get("error", ""),
                "error_type": event.get("error_type", ""),
                "attempt": event.get("attempt"),
                "retry_count": event.get("retry_count"),
                "fallback_decision": event.get("fallback_decision", ""),
                "duration_ms": event.get("duration_ms"),
                "time": event.get("time"),
            }
        elif event_name == "provider_failed":
            failure = {
                "role": role,
                "provider": provider_id,
                "provider_id": provider_id,
                "model": model,
                "status": "failed",
                "error": event.get("error", ""),
                "error_type": event.get("error_type", ""),
                "attempt": event.get("attempt"),
                "retry_count": event.get("retry_count"),
                "fallback_decision": event.get("fallback_decision", ""),
                "duration_ms": event.get("duration_ms"),
                "time": event.get("time"),
            }
            provider_failures.append(failure)
            rows_by_key[key] = failure
        elif event_name == "role_fallback":
            fallback = {
                "role": role,
                "from_provider": event.get("from_provider", ""),
                "to_provider": event.get("to_provider", ""),
                "provider": event.get("to_provider", ""),
                "model": model,
                "status": "fallback",
                "fallback_decision": event.get("fallback_decision", ""),
                "retry_count": event.get("retry_count"),
                "time": event.get("time"),
            }
            fallback_events.append(fallback)

    return {
        "roles": list(rows_by_key.values()),
        "degraded_roles": sorted(
            {
                row.get("role", "")
                for row in rows_by_key.values()
                if row.get("role") and row.get("status") in {"degraded", "failed"}
            }
        ),
        "provider_failures": provider_failures,
        "fallback_events": fallback_events,
    }


def build_tree(path: Path, base: Path, max_entries: int = 500) -> dict[str, Any]:
    counter = {"count": 0, "truncated": False}

    def build(current: Path) -> dict[str, Any]:
        result: dict[str, Any] = {
            "name": current.name,
            "type": "directory",
            "children": [],
        }
        if current.is_dir():
            try:
                for child in sorted(current.iterdir()):
                    if counter["count"] >= max_entries:
                        counter["truncated"] = True
                        break
                    if child.name.startswith(".") and child.name != ".gm":
                        continue
                    if child.name == "node_modules":
                        continue
                    counter["count"] += 1
                    if child.is_dir():
                        result["children"].append(build(child))
                    else:
                        size = child.stat().st_size if child.exists() else 0
                        result["children"].append(
                            {"name": child.name, "type": "file", "size": size}
                        )
            except PermissionError:
                pass
        return result

    tree = build(path)
    tree["entry_count"] = counter["count"]
    tree["truncated"] = counter["truncated"]
    tree["max_entries"] = max_entries
    return tree
