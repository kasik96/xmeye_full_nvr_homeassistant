"""Where the app keeps its settings, stores and downloaded binaries."""

from __future__ import annotations

import os
import platform
import sys
from pathlib import Path

from . import APP_NAME


def data_dir() -> Path:
    if override := os.environ.get("XMEYE_DATA_DIR"):
        path = Path(override)
    elif platform.system() == "Windows":
        path = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / APP_NAME
    elif platform.system() == "Darwin":
        path = Path.home() / "Library" / "Application Support" / APP_NAME
    else:
        path = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "xmeye-full-nvr"
    path.mkdir(parents=True, exist_ok=True)
    return path


def resource(*parts: str) -> Path:
    """A file shipped with the app (web/ next to this module)."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).parent.parent))
    return base.joinpath("xmeye_app", *parts)
