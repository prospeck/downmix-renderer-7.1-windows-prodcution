from __future__ import annotations

import os
import sys
from pathlib import Path

APP_STARTUP_FILE = "TaranDownmixRendererSuite.cmd"


def startup_script_path() -> Path | None:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return None
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / APP_STARTUP_FILE


def is_system_autostart_enabled() -> bool:
    path = startup_script_path()
    return bool(path and path.exists())


def set_system_autostart(enabled: bool, app_root: Path) -> tuple[bool, str]:
    path = startup_script_path()
    if path is None:
        return False, "APPDATA is unavailable"

    try:
        if enabled:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(_startup_command(app_root), encoding="utf-8")
            return True, str(path)
        if path.exists():
            path.unlink()
        return True, "disabled"
    except Exception as exc:
        return False, str(exc)


def _startup_command(app_root: Path) -> str:
    if getattr(sys, "frozen", False):
        executable = Path(sys.executable)
        return f'@echo off\nstart "" "{executable}"\n'

    pythonw = Path(sys.executable).with_name("pythonw.exe")
    runner = pythonw if pythonw.exists() else Path(sys.executable)
    script = app_root / "renderer_app.py"
    return f'@echo off\ncd /d "{app_root}"\nstart "" "{runner}" "{script}"\n'
