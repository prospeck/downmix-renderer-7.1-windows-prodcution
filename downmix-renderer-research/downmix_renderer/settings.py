from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def default_settings_path() -> Path:
    return Path.cwd() / "settings.json"


def load_settings(path: Path | None = None) -> dict[str, Any]:
    settings_path = path or default_settings_path()
    if not settings_path.exists():
        return {}
    try:
        return json.loads(settings_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_settings(data: dict[str, Any], path: Path | None = None) -> None:
    settings_path = path or default_settings_path()
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = settings_path.with_suffix(settings_path.suffix + ".tmp")
    temp_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    temp_path.replace(settings_path)
