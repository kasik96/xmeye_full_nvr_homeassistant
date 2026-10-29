"""Streams in Home Assistant's own go2rtc server.

Each NVR stream is added once; WebRTC in the browser, HomeKit (through HA's
RTSP restream) and snapshots then share a single connection to the NVR.
In Home Assistant only used when HA manages go2rtc itself (HA OS /
container); the standalone app runs its own.
"""

from __future__ import annotations

import logging
import platform
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from aiohttp import ClientError, ClientSession, ClientTimeout

from .util import download_binary

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

HA_MANAGED_URL = "http://localhost:11984/"
RTSP_RESTREAM = "rtsp://127.0.0.1:18554/"
TIMEOUT = ClientTimeout(total=10)

# Used when the system has no go2rtc (e.g. Home Assistant Core in a venv, the
# standalone app): a pinned release from GitHub, checked against these hashes.
GO2RTC_VERSION = "1.9.14"
GO2RTC_URL = "https://github.com/AlexxIT/go2rtc/releases/download/v{version}/{asset}"
GO2RTC_ASSETS = {
    ("Linux", "amd64"): ("go2rtc_linux_amd64", "32d616af226bd731678ffde328b94cfb94e30339bfefc469cfb76323144615a6"),
    ("Linux", "arm64"): ("go2rtc_linux_arm64", "359fabade8a7a51e81a55fe6df6b0ef81764a5e1d63179577534eaaa71904b50"),
    ("Linux", "arm"): ("go2rtc_linux_arm", "4d7e1639af5a2722a28e864468fd8099b3c1682565446c798bf9e3b38fde12e4"),
    ("Darwin", "amd64"): ("go2rtc_mac_amd64.zip", "9b0b9a27a4dc3a5b8b93376e7e8fc2787c6af624a512842622be84aec0171c7a"),
    ("Darwin", "arm64"): ("go2rtc_mac_arm64.zip", "919b78adc759d6b3883d1e1b2ac915ac0985bb903ff1897b4d228527bd64690c"),
    ("Windows", "amd64"): ("go2rtc_win64.zip", "dd4167d75cb04abe618855b7c71f8658bd009f60c1a71835d134d2c11c939907"),
    ("Windows", "arm64"): ("go2rtc_win_arm64.zip", "814be0f6d8669025c7bccdd1f026ffaf613abae5352239f4ec84de543b94594a"),
}  # fmt: skip
ARCHES = {"x86_64": "amd64", "amd64": "amd64", "aarch64": "arm64", "arm64": "arm64",
          "armv7l": "arm", "armv6l": "arm"}  # fmt: skip


def platform_key() -> tuple[str, str | None]:
    return platform.system(), ARCHES.get(platform.machine().lower())


def can_download() -> bool:
    return platform_key() in GO2RTC_ASSETS


def find_binary(cache_dir: Path) -> str | None:
    """go2rtc on the PATH, else a copy downloaded earlier."""
    found = shutil.which("go2rtc")
    if found:
        return found
    cached = cache_dir / _cached_name()
    return str(cached) if cached.is_file() else None


def _cached_name() -> str:
    exe = ".exe" if platform.system() == "Windows" else ""
    return f"xmeye_go2rtc_{GO2RTC_VERSION}{exe}"


async def download(session: ClientSession, cache_dir: Path) -> str:
    """Fetch the pinned go2rtc release for this machine into `cache_dir`."""
    key = platform_key()
    if key not in GO2RTC_ASSETS:
        raise ValueError(f"no go2rtc for {platform.system()} {platform.machine()}")
    asset, sha256 = GO2RTC_ASSETS[key]
    url = GO2RTC_URL.format(version=GO2RTC_VERSION, asset=asset)
    _LOGGER.info("Downloading go2rtc %s from %s", GO2RTC_VERSION, url)
    target = cache_dir / _cached_name()
    member = "go2rtc" if asset.endswith(".zip") else None
    await download_binary(session, url, sha256, target, member)
    return str(target)


class Go2rtc:
    def __init__(self, url: str, session: ClientSession, rtsp: str = RTSP_RESTREAM) -> None:
        self._url = url
        self._rtsp = rtsp
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

    def rtsp_url(self, name: str) -> str:
        return self._rtsp + name

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
