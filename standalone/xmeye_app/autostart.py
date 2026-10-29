"""Start the app when the user logs in (per user, no admin rights needed)."""

from __future__ import annotations

import contextlib
import platform
import plistlib
import sys
from pathlib import Path

from . import APP_NAME

LABEL = "io.github.kasik96.xmeye-full-nvr"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def command() -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, "--background"]
    return [sys.executable, "-m", "xmeye_app", "--background"]


def _mac_plist() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def _linux_desktop() -> Path:
    return Path.home() / ".config" / "autostart" / "xmeye-full-nvr.desktop"


def is_enabled() -> bool:
    system = platform.system()
    if system == "Windows":
        import winreg  # noqa: PLC0415

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
                winreg.QueryValueEx(key, APP_NAME)
            return True
        except OSError:
            return False
    if system == "Darwin":
        return _mac_plist().is_file()
    return _linux_desktop().is_file()


def set_enabled(enabled: bool) -> None:
    system = platform.system()
    cmd = command()
    if system == "Windows":
        import subprocess  # noqa: PLC0415
        import winreg  # noqa: PLC0415

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, subprocess.list2cmdline(cmd))
            else:
                with contextlib.suppress(OSError):
                    winreg.DeleteValue(key, APP_NAME)
    elif system == "Darwin":
        path = _mac_plist()
        if enabled:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(
                plistlib.dumps({"Label": LABEL, "ProgramArguments": cmd, "RunAtLoad": True})
            )
        else:
            path.unlink(missing_ok=True)
    else:
        path = _linux_desktop()
        if enabled:
            import shlex  # noqa: PLC0415

            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                "[Desktop Entry]\nType=Application\n"
                f"Name={APP_NAME}\nExec={shlex.join(cmd)}\nX-GNOME-Autostart-enabled=true\n"
            )
        else:
            path.unlink(missing_ok=True)
