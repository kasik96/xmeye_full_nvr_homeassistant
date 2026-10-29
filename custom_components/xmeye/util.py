"""Small helpers shared by the integration and the standalone app."""

from __future__ import annotations

import asyncio
import hashlib
import io
import os
import zipfile
from collections.abc import Coroutine
from pathlib import Path
from typing import Any, Protocol

import aiohttp

_TASKS: set[asyncio.Task] = set()


def background(coro: Coroutine[Any, Any, Any], name: str) -> asyncio.Task:
    """A task that is kept referenced until it ends."""
    task = asyncio.get_running_loop().create_task(coro, name=name)
    _TASKS.add(task)
    task.add_done_callback(_TASKS.discard)
    return task


class Store(Protocol):
    """What is used of Home Assistant's Store (the standalone app has its own)."""

    async def async_load(self) -> Any: ...

    async def async_save(self, data: Any) -> None: ...

    def async_delay_save(self, data_func: Any, delay: float = 0) -> None: ...


async def download_binary(
    session: aiohttp.ClientSession,
    url: str,
    sha256: str,
    target: Path,
    member: str | None = None,
) -> None:
    """Fetch an executable, check its hash and save it as `target`.

    For a zip (a release archive or a wheel), `member` is the prefix of the
    path inside it to extract.
    """
    async with session.get(url, timeout=aiohttp.ClientTimeout(total=600)) as resp:
        resp.raise_for_status()
        data = await resp.read()
    if hashlib.sha256(data).hexdigest() != sha256:
        raise ValueError(f"{url} has the wrong checksum")

    def _save() -> None:
        body = data
        if member is not None:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                name = next(n for n in archive.namelist() if n.startswith(member))
                body = archive.read(name)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(target.name + ".tmp")
        tmp.write_bytes(body)
        os.chmod(tmp, 0o755)
        tmp.replace(target)

    await asyncio.to_thread(_save)
