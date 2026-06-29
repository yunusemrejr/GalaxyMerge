import hashlib
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from galaxy_merge.core.locks import atomic_write
from galaxy_merge.core.opencode_import import import_opencode_providers

APP_CONFIG_DIR = Path.home() / ".config" / "galaxy-merge"
APP_DATA_DIR = Path.home() / ".local" / "share" / "galaxy-merge"


class AppConfig(BaseModel):
    schema_version: int = 1
    install_dir: str = ""
    default_port: int = 0
    no_browser: bool = False


def load_app_config() -> AppConfig:
    path = APP_CONFIG_DIR / "config.json"
    if path.exists():
        data = json.loads(path.read_text())
        return AppConfig(**data)
    return AppConfig()


def save_app_config(config: AppConfig) -> None:
    APP_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    path = APP_CONFIG_DIR / "config.json"
    atomic_write(path, config.model_dump_json(indent=2))


def load_json(path: Path) -> dict[str, Any]:
    if path.exists():
        return json.loads(path.read_text())
    return {}


def save_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, json.dumps(data, indent=2, default=str))


def compute_config_hash(config_dir: Path) -> str:
    parts = []
    for name in (
        "providers.json",
        "models.json",
        "fusion.json",
        "routing.json",
        "safety.json",
    ):
        p = config_dir / name
        if p.exists():
            parts.append(p.read_text())
    raw = "".join(parts)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]
