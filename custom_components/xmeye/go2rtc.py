"""Streams in Home Assistant's own go2rtc server.

Each NVR stream is added once; WebRTC in the browser, HomeKit (through HA's
RTSP restream) and snapshots then share a single connection to the NVR.
Only used when HA manages go2rtc itself (HA OS / container).
"""

from __future__ import annotations

import logging

from aiohttp import ClientError, ClientSession, ClientTimeout

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

HA_MANAGED_URL = "http://localhost:11984/"
RTSP_RESTREAM = "rtsp://127.0.0.1:18554/"
TIMEOUT = ClientTimeout(total=10)


class Go2rtc:
    def __init__(self, url: str, session: ClientSession) -> None:
        self._url = url
        self._session = session
        self._streams: dict[str, str] = {}

    @classmethod
    def from_hass(cls, hass: HomeAssistant) -> Go2rtc | None:
        config = hass.data.get("go2rtc")
        url = getattr(config, "url", None)
        session = getattr(config, "session", None)
        if url != HA_MANAGED_URL or session is None:
            return None
        return cls(url, session)

    @staticmethod
    def rtsp_url(name: str) -> str:
        return RTSP_RESTREAM + name

    async def add_streams(self, streams: dict[str, str]) -> bool:
        self._streams.update(streams)
        return await self.ensure_streams()

    async def ensure_streams(self) -> bool:
        """(Re-)add streams go2rtc does not have, e.g. after it restarted."""
        try:
            async with self._session.get(
                self._url + "api/streams", timeout=TIMEOUT
            ) as resp:
                resp.raise_for_status()
                existing = await resp.json(content_type=None) or {}
            for name, src in self._streams.items():
                if name in existing:
                    continue
                async with self._session.put(
                    self._url + "api/streams",
                    params={"name": name, "src": src},
                    timeout=TIMEOUT,
                ) as resp:
                    resp.raise_for_status()
        except (ClientError, TimeoutError, ValueError) as err:
            _LOGGER.warning("Could not add streams to go2rtc: %s", err)
            return False
        return True

    async def snapshot(self, name: str, width: int | None = None) -> bytes | None:
        params = {"src": name}
        if width:
            params["width"] = str(width)
        try:
            async with self._session.get(
                self._url + "api/frame.jpeg", params=params, timeout=TIMEOUT
            ) as resp:
                if resp.status != 200:
                    return None
                return await resp.read()
        except (ClientError, TimeoutError) as err:
            _LOGGER.debug("go2rtc snapshot of %s failed: %s", name, err)
            return None
