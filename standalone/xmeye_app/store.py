"""JSON files with the part of Home Assistant's Store API the shared modules use."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any


class JsonStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._delayed: asyncio.TimerHandle | None = None
        self._data_func: Callable[[], Any] | None = None

    async def async_load(self) -> Any:
        def _read() -> Any:
            try:
                return json.loads(self.path.read_text("utf-8"))
            except (OSError, ValueError):
                return None

        return await asyncio.to_thread(_read)

    async def async_save(self, data: Any) -> None:
        if self._delayed:
            self._delayed.cancel()
            self._delayed = None
        await asyncio.to_thread(write_private, self.path, json.dumps(data, indent=1))

    def async_delay_save(self, data_func: Callable[[], Any], delay: float = 0) -> None:
        self._data_func = data_func
        if self._delayed:
            self._delayed.cancel()
        loop = asyncio.get_running_loop()
        self._delayed = loop.call_later(
            delay, lambda: loop.create_task(self.async_save(data_func()))
        )

    async def flush(self) -> None:
        if self._delayed and self._data_func:
            await self.async_save(self._data_func())


def write_private(path: Path, text: str) -> None:
    """Write a file only the user can read, atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    with contextlib.suppress(OSError):
        os.chmod(tmp, 0o600)
    tmp.replace(path)
