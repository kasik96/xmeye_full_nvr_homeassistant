"""Stop go2rtc processes a previous run left behind (after a crash or a kill),
which would still hold their ports. Only processes started with a config file
from our data directory are touched."""

from __future__ import annotations

import logging
import os
import platform
import signal
import subprocess
from pathlib import Path

_LOGGER = logging.getLogger(__name__)


def _processes() -> list[tuple[int, str]]:
    if platform.system() == "Windows":
        script = (
            "Get-CimInstance Win32_Process -Filter \"Name like '%go2rtc%'\" | "
            "ForEach-Object { \"$($_.ProcessId)`t$($_.CommandLine)\" }"
        )
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True, text=True, timeout=20,
            creationflags=subprocess.CREATE_NO_WINDOW,
        ).stdout  # fmt: skip
        rows = [line.split("\t", 1) for line in out.splitlines() if "\t" in line]
    else:
        out = subprocess.run(
            ["ps", "-axo", "pid=,command="], capture_output=True, text=True, timeout=10
        ).stdout
        rows = [line.strip().split(" ", 1) for line in out.splitlines() if line.strip()]
    procs = []
    for row in rows:
        if len(row) == 2 and row[0].strip().isdigit():
            procs.append((int(row[0]), row[1]))
    return procs


def stop_stale_go2rtc(data_dir: Path) -> None:
    marker = str(data_dir)
    try:
        procs = _processes()
    except (OSError, subprocess.SubprocessError) as err:
        _LOGGER.debug("Cannot list processes: %s", err)
        return
    for pid, command in procs:
        if pid != os.getpid() and "go2rtc" in command and marker in command:
            _LOGGER.info("Stopping go2rtc left from a previous run (pid %d)", pid)
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError as err:
                _LOGGER.debug("Could not stop %d: %s", pid, err)
