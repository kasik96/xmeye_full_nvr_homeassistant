"""Live video: a go2rtc process with one stream per NVR channel.

The browser gets WebRTC through the app's own WebSocket, which relays the
offer, answer and ICE candidates to go2rtc's WebSocket API. go2rtc's API and
RTSP server listen on localhost only; the NVR's RTSP URLs (with the password)
are added over the API, so they are never written to disk.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import aiohttp
import yaml

from xmeye_core.go2rtc import Go2rtc
from xmeye_core.util import background

from .store import write_private

_LOGGER = logging.getLogger(__name__)

API_PORT = 11985
RTSP_PORT = 18555
WEBRTC_PORT = 18556
RESPAWN = 5
CHECK = 60


class LiveServer:
    def __init__(
        self, binary: str, ffmpeg: str, config: Path, session: aiohttp.ClientSession
    ) -> None:
        self._binary = binary
        self._ffmpeg = ffmpeg
        self._config = config
        self._session = session
        self._proc: asyncio.subprocess.Process | None = None
        self._runner: asyncio.Task | None = None
        self._streams: dict[str, str] = {}
        self.client = self._new_client()

    def _new_client(self) -> Go2rtc:
        return Go2rtc(
            f"http://127.0.0.1:{API_PORT}/", self._session, rtsp=f"rtsp://127.0.0.1:{RTSP_PORT}/"
        )

    async def start(self, streams: dict[str, str]) -> None:
        """(Re)start go2rtc with these streams (name → source)."""
        await self.stop()
        self._streams = streams
        self.client = self._new_client()
        config = {
            "app": {"modules": ["api", "ws", "rtsp", "webrtc", "mjpeg", "ffmpeg"]},
            "api": {"listen": f"127.0.0.1:{API_PORT}"},
            "rtsp": {"listen": f"127.0.0.1:{RTSP_PORT}"},
            "webrtc": {"listen": f":{WEBRTC_PORT}"},
            "ffmpeg": {"bin": self._ffmpeg},
            "log": {"level": "info"},
        }
        text = "# Managed by XMeye Full NVR\n" + yaml.safe_dump(config, sort_keys=False)
        await asyncio.to_thread(write_private, self._config, text)
        self._runner = background(self._run(), "xmeye live go2rtc")

    async def _run(self) -> None:
        while True:
            self._proc = await asyncio.create_subprocess_exec(
                self._binary,
                "-config",
                str(self._config),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            keeper = background(self._keep_streams(), "xmeye live streams")
            assert self._proc.stdout
            try:
                async for line in self._proc.stdout:
                    text = line.decode(errors="replace").rstrip()
                    if " ERR " in text or " WRN " in text:
                        _LOGGER.warning("go2rtc: %s", text)
                    else:
                        _LOGGER.debug("go2rtc: %s", text)
                code = await self._proc.wait()
            finally:
                keeper.cancel()
            _LOGGER.warning("go2rtc exited (%s), restarting in %d s", code, RESPAWN)
            await asyncio.sleep(RESPAWN)

    async def _keep_streams(self) -> None:
        """Add the streams once the API is up, and again if go2rtc lost them."""
        await asyncio.sleep(1)
        while not await self.client.add_streams(self._streams):
            await asyncio.sleep(2)
        while True:
            await asyncio.sleep(CHECK)
            await self.client.ensure_streams()

    async def stop(self) -> None:
        if self._runner:
            self._runner.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._runner
            self._runner = None
        if self._proc and self._proc.returncode is None:
            self._proc.terminate()
            try:
                await asyncio.wait_for(self._proc.wait(), 5)
            except TimeoutError:
                self._proc.kill()
        self._proc = None

    async def webrtc(
        self, stream: str, offer: str, send: Callable[[dict[str, Any]], Awaitable[None]]
    ) -> WebRTCSession:
        """Start a WebRTC session; `send` gets HA-style answer/candidate/error messages."""
        ws = await self._session.ws_connect(
            f"http://127.0.0.1:{API_PORT}/api/ws", params={"src": stream}
        )
        session = WebRTCSession(ws, send)
        await ws.send_json({"type": "webrtc/offer", "value": offer})
        session.task = background(session.relay(), "xmeye webrtc")
        return session


class WebRTCSession:
    def __init__(
        self,
        ws: aiohttp.ClientWebSocketResponse,
        send: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        self._ws = ws
        self._send = send
        self.task: asyncio.Task | None = None

    async def relay(self) -> None:
        try:
            async for msg in self._ws:
                if msg.type != aiohttp.WSMsgType.TEXT:
                    continue
                data = json.loads(msg.data)
                kind, value = data.get("type"), data.get("value")
                if kind == "webrtc/answer":
                    await self._send({"type": "answer", "answer": value})
                elif kind == "webrtc/candidate":
                    await self._send(
                        {"type": "candidate", "candidate": {"candidate": value, "sdpMLineIndex": 0}}
                    )
                elif kind == "error":
                    await self._send({"type": "error", "code": "go2rtc", "message": str(value)})
        except (aiohttp.ClientError, ConnectionError, ValueError) as err:
            _LOGGER.debug("WebRTC relay ended: %s", err)

    async def candidate(self, candidate: dict[str, Any]) -> None:
        value = candidate.get("candidate")
        if value and not self._ws.closed:
            await self._ws.send_json({"type": "webrtc/candidate", "value": value})

    async def close(self) -> None:
        if self.task:
            self.task.cancel()
        await self._ws.close()
