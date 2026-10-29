"""Event thumbnails: the first I-frame a few seconds into a recording.

Each thumbnail costs a short download from the NVR, so they are made on
demand, two at a time, and kept in memory.
"""

from __future__ import annotations

import asyncio
import logging
from collections import OrderedDict
from dataclasses import replace
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from .const import THUMB_CACHE, THUMB_OFFSET, THUMB_WIDTH
from .dvrip import CODEC_H265, FRAME_I, DVRIPError, Frame, FrameParser

if TYPE_CHECKING:
    from .nvr import XMeyeData

_LOGGER = logging.getLogger(__name__)

TIMEOUT = 20


class ThumbnailCache:
    def __init__(self, ffmpeg: str) -> None:
        self._ffmpeg = ffmpeg
        self._cache: OrderedDict[tuple, bytes | None] = OrderedDict()
        self._pending: dict[tuple, asyncio.Future] = {}
        self._sem = asyncio.Semaphore(2)

    async def get(self, data: XMeyeData, channel: int, begin: datetime) -> bytes | None:
        key = (data.entry_id, channel, begin)
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        if key in self._pending:
            return await asyncio.shield(self._pending[key])
        future = asyncio.get_running_loop().create_future()
        self._pending[key] = future
        image = None
        try:
            async with asyncio.timeout(TIMEOUT):
                image = await self._make(data, channel, begin)
        except (DVRIPError, OSError, TimeoutError) as err:
            _LOGGER.debug("Thumbnail ch%d %s failed: %s", channel + 1, begin, err)
        finally:
            del self._pending[key]
            future.set_result(image)
        self._cache[key] = image
        while len(self._cache) > THUMB_CACHE:
            self._cache.popitem(last=False)
        return image

    async def _make(self, data: XMeyeData, channel: int, begin: datetime) -> bytes | None:
        start = begin + timedelta(seconds=THUMB_OFFSET)
        rec = await data.recording_at(channel, start)
        if rec is None:
            rec = await data.recording_at(channel, begin)
        if rec is None:
            return None
        start = min(max(start, rec.begin), rec.end)
        part = replace(rec, begin=start, end=min(rec.end, start + timedelta(seconds=30)))
        frame: Frame | None = None
        async with self._sem, data.client.download(part) as chunks:
            parser = FrameParser()
            async for chunk in chunks:
                frame = next((f for f in parser.feed(chunk) if f.kind in FRAME_I), None)
                if frame:
                    break
        if frame is None:
            return None
        return await self._decode(frame)

    async def _decode(self, frame: Frame) -> bytes | None:
        proc = await asyncio.create_subprocess_exec(
            self._ffmpeg, "-hide_banner", "-loglevel", "error",
            "-f", "hevc" if frame.codec == CODEC_H265 else "h264", "-i", "pipe:0",
            "-frames:v", "1", "-vf", f"scale={THUMB_WIDTH}:-2", "-q:v", "5",
            "-f", "mjpeg", "pipe:1",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )  # fmt: skip
        out, _ = await proc.communicate(frame.data)
        return out or None
