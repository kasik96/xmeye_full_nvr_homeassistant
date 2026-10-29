"""The app's state: settings, the NVR connection and the shared services."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from pathlib import Path
from typing import Any

import aiohttp

from xmeye_core.alarm import AlarmListener
from xmeye_core.commands import Services
from xmeye_core.dvrip import DVRIPAuthError, DVRIPClient, DVRIPError
from xmeye_core.homekit import HomeKitManager
from xmeye_core.nvr import XMeyeData, nvr_channels, serial_of, visible_channels
from xmeye_core.playback import PlaybackManager
from xmeye_core.thumbnails import ThumbnailCache
from xmeye_core.util import background

from . import binaries
from .live import LiveServer
from .settings import Settings, SettingsFile
from .store import JsonStore

_LOGGER = logging.getLogger(__name__)

ENTRY_ID = "nvr"
RETRY = 30
PREPARE_RETRY = 60
SNAPSHOT_MAX_AGE = 10


class App:
    def __init__(self, data_dir: Path) -> None:
        self.dir = data_dir
        self.bin_dir = data_dir / "bin"
        self.config = SettingsFile(data_dir)
        self.status = "Starting…"
        self.error: str | None = None
        self.services: Services | None = None
        self.nvr: XMeyeData | None = None
        self.live: LiveServer | None = None
        # camera entity id the panel uses → go2rtc stream name
        self.streams: dict[str, str] = {}
        self.session: aiohttp.ClientSession | None = None
        self._lock = asyncio.Lock()
        self._task: asyncio.Task | None = None
        self._alarm_store = JsonStore(data_dir / "events.json")
        self._homekit_store = JsonStore(data_dir / "homekit.json")
        self._snapshots: dict[str, tuple[float, bytes]] = {}

    @property
    def settings(self) -> Settings:
        return self.config.settings

    async def start(self) -> None:
        self.session = aiohttp.ClientSession()
        self._task = background(self._prepare_and_connect(), "xmeye start")

    async def _prepare_and_connect(self) -> None:
        """Get ffmpeg and go2rtc (the first run downloads them), then connect."""
        assert self.session
        while True:
            try:
                self.status = "Getting ffmpeg (first start: about 30 MB)…"
                ffmpeg = await binaries.ffmpeg(self.session, self.bin_dir)
                self.status = "Getting go2rtc…"
                go2rtc = await binaries.go2rtc_binary(self.session, self.bin_dir)
                break
            except Exception as err:  # noqa: BLE001
                self.error = f"Could not download the video tools: {err}"
                _LOGGER.warning(self.error)
                await asyncio.sleep(PREPARE_RETRY)
        self.error = None
        playback = PlaybackManager(ffmpeg)
        await playback.async_setup()
        homekit = HomeKitManager(
            ffmpeg,
            self._homekit_store,
            self.dir / "homekit_go2rtc.yaml",
            self.bin_dir,
            self.session,
        )
        await homekit.async_setup()
        self.services = Services(
            nvrs=lambda: {ENTRY_ID: self.nvr} if self.nvr else {},
            playback=playback,
            thumbs=ThumbnailCache(ffmpeg),
            homekit=homekit,
            entity_id=lambda uid: f"camera.xmeye_{uid.lower()}",
        )
        self.live = LiveServer(go2rtc, ffmpeg, self.dir / "live_go2rtc.yaml", self.session)
        await self._connect_loop()

    async def _connect_loop(self) -> None:
        while self.settings.configured:
            try:
                async with self._lock:
                    await self._connect()
                return
            except DVRIPAuthError:
                self.error = "The NVR rejected the user name or password."
                self.status = "Not connected"
                return
            except (DVRIPError, OSError, TimeoutError) as err:
                self.error = f"Cannot reach the NVR at {self.settings.host}: {err}"
                self.status = f"Not connected, retrying every {RETRY} s"
                _LOGGER.warning(self.error)
            await asyncio.sleep(RETRY)
        self.status = "Not set up"

    async def _connect(self) -> None:
        assert self.services and self.live
        s = self.settings
        self.status = f"Connecting to {s.host}…"
        password = await asyncio.to_thread(self.config.password)
        client = DVRIPClient(s.host, s.port, s.username, password)
        try:
            info = await client.system_info()
            titles = await client.channel_titles()
            status = await client.channel_status()
        except BaseException:
            await client.close()
            raise
        all_channels = nvr_channels(titles, status)
        data = XMeyeData(
            entry_id=ENTRY_ID,
            client=client,
            serial=serial_of(info, ENTRY_ID),
            model=str(info.get("HardWare") or "NVR"),
            host=s.host,
            rtsp_port=s.rtsp_port,
            username=s.username,
            password=password,
            channels=visible_channels(all_channels, s.names),
            nvr_channels=all_channels,
            transcode_h265=s.transcode_h265,
        )
        streams = {}
        self.streams = {}
        for ch in data.channels:
            for sub in (False, True):
                name = data.stream_name(ch, sub)
                streams[name] = data.rtsp_url(ch, sub)
                uid = f"{data.serial}_{ch + 1}{'_sub' if sub else ''}"
                self.streams[self.services.entity_id(uid)] = name
        await self.live.start(streams)
        data.go2rtc = self.live.client
        homekit = self.services.homekit
        for ch, name in data.channels.items():
            sources = [data.go2rtc.rtsp_url(data.stream_name(ch, sub)) for sub in (False, True)]
            await homekit.register(ENTRY_ID, data.serial, ch, name, *sources)
        await homekit.apply()
        data.alarms = AlarmListener(client, self._alarm_store)
        await data.alarms.async_start()
        self.nvr = data
        self.error = None
        self.status = f"Connected to {data.model} at {s.host}"
        _LOGGER.info(self.status)

    async def _disconnect(self) -> None:
        data, self.nvr = self.nvr, None
        self.streams = {}
        if data is None:
            return
        await data.alarms.async_stop()
        if self.services:
            await self.services.playback.close_client(data.client)
        await data.client.close()
        if self.live:
            await self.live.stop()

    async def reconnect(self) -> None:
        if self._task and not self._task.done() and self.services is None:
            return  # still preparing; it connects with the new settings
        if self._task and not self._task.done():
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        async with self._lock:
            await self._disconnect()
        self.error = None
        self._task = background(self._connect_loop(), "xmeye connect")

    async def test(self, host: str, port: int, username: str, password: str | None) -> dict[str, Any]:
        """Log in with these details; the NVR's model and channels."""
        if password is None:
            password = await asyncio.to_thread(self.config.password)
        client = DVRIPClient(host, port, username, password)
        try:
            info = await client.system_info()
            titles = await client.channel_titles()
            status = await client.channel_status()
        finally:
            await client.close()
        return {
            "model": str(info.get("HardWare") or "NVR"),
            "channels": [
                {"channel": ch + 1, "title": title}
                for ch, title in nvr_channels(titles, status).items()
            ],
        }

    async def snapshot(self, entity_id: str) -> bytes | None:
        stream = self.streams.get(entity_id)
        if not stream or not self.nvr or not self.nvr.go2rtc:
            return None
        loop = asyncio.get_running_loop()
        cached = self._snapshots.get(stream)
        if cached and loop.time() - cached[0] < SNAPSHOT_MAX_AGE:
            return cached[1]
        image = await self.nvr.go2rtc.snapshot(stream, 640)
        if image:
            self._snapshots[stream] = (loop.time(), image)
        return image or (cached[1] if cached else None)

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
        async with self._lock:
            await self._disconnect()
        if self.services:
            await self.services.playback.close()
            await self.services.homekit.async_stop()
        await self._alarm_store.flush()
        if self.session:
            await self.session.close()
