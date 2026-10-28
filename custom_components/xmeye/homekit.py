"""HomeKit cameras through a dedicated go2rtc instance.

Home Assistant's own go2rtc runs without the HomeKit module, so the
integration starts a second go2rtc (the same binary) that only serves HomeKit.
It reads the cameras from HA's go2rtc RTSP restream, so the NVR still sees one
connection per stream and nothing is transcoded. Pairings are kept by go2rtc
in its config file, which this module regenerates without losing them.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import logging
import os
import platform
import secrets
import shutil
from pathlib import Path
from typing import Any

import yaml

from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store

_LOGGER = logging.getLogger(__name__)

HOMEKIT_PORT = 51830
SRTP_PORT = 51831
RTSP_PORT = 51832
RESPAWN = 10
# HAP endpoints; everything else of go2rtc's API stays closed on the LAN
HAP_PATHS = ["/pair-setup", "/pair-verify", "/pairings", "/accessories", "/characteristics"]
# Used when the system has no go2rtc (e.g. Home Assistant Core in a venv):
# a pinned release from GitHub, checked against these hashes.
GO2RTC_VERSION = "1.9.14"
GO2RTC_URL = "https://github.com/AlexxIT/go2rtc/releases/download/v{version}/go2rtc_linux_{arch}"
GO2RTC_SHA256 = {
    "amd64": "32d616af226bd731678ffde328b94cfb94e30339bfefc469cfb76323144615a6",
    "arm64": "359fabade8a7a51e81a55fe6df6b0ef81764a5e1d63179577534eaaa71904b50",
    "arm": "4d7e1639af5a2722a28e864468fd8099b3c1682565446c798bf9e3b38fde12e4",
}
ARCHES = {"x86_64": "amd64", "amd64": "amd64", "aarch64": "arm64", "arm64": "arm64",
          "armv7l": "arm", "armv6l": "arm"}
# Trivial codes Apple rejects
BAD_PINS = {f"{d}" * 8 for d in range(10)} | {"12345678", "87654321"}


class _Dumper(yaml.SafeDumper):
    """YAML the way go2rtc writes it: indented lists, no line wrapping.

    go2rtc patches pairings into this file in place; with PyYAML's default
    (lists at the key's indent, long keys wrapped) its patch breaks the file.
    """

    def increase_indent(self, flow: bool = False, indentless: bool = False) -> None:
        return super().increase_indent(flow, False)


def _dump(data: dict) -> str:
    return yaml.dump(data, Dumper=_Dumper, sort_keys=False, width=1 << 20, indent=2)


def _new_pin() -> str:
    while True:
        pin = f"{secrets.randbelow(10**8):08d}"
        if pin not in BAD_PINS:
            return pin


def format_pin(pin: str) -> str:
    return f"{pin[:3]}-{pin[3:5]}-{pin[5:]}"


class HomeKitManager:
    """Owns the HomeKit go2rtc process for all NVRs."""

    def __init__(self, hass: HomeAssistant, ffmpeg: str) -> None:
        self.hass = hass
        self._ffmpeg = ffmpeg
        self._store: Store[dict] = Store(hass, 1, "xmeye.homekit")
        # stream name -> {"enabled", "pin", "name", "source", "entry_id", "channel"}
        self.cameras: dict[str, dict[str, Any]] = {}
        self._config = Path(hass.config.path(".storage", "xmeye_homekit_go2rtc.yaml"))
        self._proc: asyncio.subprocess.Process | None = None
        self._runner: asyncio.Task | None = None
        self._binary: str | None = None
        self.error: str | None = None
        self._lock = asyncio.Lock()

    async def async_setup(self) -> None:
        stored = await self._store.async_load() or {}
        self.cameras = stored.get("cameras", {})
        self._binary = await self.hass.async_add_executor_job(shutil.which, "go2rtc")
        if not self._binary:
            cached = Path(self.hass.config.path(".storage", f"xmeye_go2rtc_{GO2RTC_VERSION}"))
            if await self.hass.async_add_executor_job(cached.is_file):
                self._binary = str(cached)

        async def _stop(_event: Event) -> None:
            await self._stop_process()

        self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _stop)

    @staticmethod
    def stream_name(serial: str, channel: int) -> str:
        return f"hk_{serial}_{channel + 1}"

    async def register(
        self, entry_id: str, serial: str, channel: int, name: str, source: str | None
    ) -> None:
        """Called by each NVR at setup with its cameras' restream URLs."""
        key = self.stream_name(serial, channel)
        cam = self.cameras.setdefault(key, {"enabled": False, "pin": _new_pin()})
        cam.update(entry_id=entry_id, channel=channel + 1, name=name, source=source)

    async def apply(self) -> None:
        """Write the config and (re)start go2rtc for the enabled cameras.

        go2rtc is only restarted when its config changes: a restart drops
        running HomeKit sessions and any pairing in progress.
        """
        async with self._lock:
            await self._store.async_save({"cameras": self.cameras})
            enabled = {k: c for k, c in self.cameras.items() if c["enabled"] and c.get("source")}
            if not enabled:
                await self._stop_process()
                return
            if not self._binary:
                self._binary = await self._download()
            if not self._binary:
                _LOGGER.warning(self.error)
                return
            changed = await self.hass.async_add_executor_job(self._write_config, enabled)
            running = self._proc is not None and self._proc.returncode is None
            if running and not changed:
                return
            await self._stop_process()
            self.error = None
            self._runner = self.hass.async_create_background_task(
                self._run(), "xmeye homekit go2rtc"
            )

    async def set_enabled(self, key: str, enabled: bool) -> None:
        self.cameras[key]["enabled"] = enabled
        await self.apply()

    async def reset_pairing(self, key: str) -> None:
        """Forget the Apple Home pairing and use a new code."""
        self.cameras[key]["pin"] = _new_pin()
        await self.hass.async_add_executor_job(self._drop_pairings, key)
        await self.apply()

    async def _download(self) -> str | None:
        """Fetch the pinned go2rtc release for this machine (systems without one)."""
        arch = ARCHES.get(platform.machine().lower())
        if platform.system() != "Linux" or arch not in GO2RTC_SHA256:
            self.error = f"no go2rtc for {platform.system()} {platform.machine()}"
            return None
        target = Path(self.hass.config.path(".storage", f"xmeye_go2rtc_{GO2RTC_VERSION}"))
        url = GO2RTC_URL.format(version=GO2RTC_VERSION, arch=arch)
        _LOGGER.info("Downloading go2rtc %s for HomeKit from %s", GO2RTC_VERSION, url)
        try:
            async with async_get_clientsession(self.hass).get(url, timeout=120) as resp:
                resp.raise_for_status()
                data = await resp.read()
        except Exception as err:  # noqa: BLE001
            self.error = f"could not download go2rtc: {err}"
            return None
        if hashlib.sha256(data).hexdigest() != GO2RTC_SHA256[arch]:
            self.error = "downloaded go2rtc has the wrong checksum"
            return None

        def _save() -> None:
            tmp = target.with_suffix(".tmp")
            tmp.write_bytes(data)
            os.chmod(tmp, 0o755)
            tmp.replace(target)

        await self.hass.async_add_executor_job(_save)
        return str(target)

    async def status(self) -> dict[str, Any]:
        paired = await self.hass.async_add_executor_job(self._read_pairings)
        return {
            "available": bool(self._binary) or platform.system() == "Linux",
            "running": self._proc is not None and self._proc.returncode is None,
            "error": self.error,
            "port": HOMEKIT_PORT,
            "cameras": [
                {
                    "key": key,
                    "entry_id": cam.get("entry_id"),
                    "channel": cam.get("channel"),
                    "name": cam.get("name"),
                    "enabled": cam["enabled"],
                    "pin": format_pin(cam["pin"]),
                    "paired": bool(paired.get(key)),
                }
                for key, cam in self.cameras.items()
                if cam.get("source")
            ],
        }

    # --- config file ------------------------------------------------------

    def _load(self) -> dict:
        try:
            return yaml.safe_load(self._config.read_text()) or {}
        except (OSError, yaml.YAMLError):
            return {}

    def _read_pairings(self) -> dict[str, list]:
        homekit = self._load().get("homekit") or {}
        return {k: (v or {}).get("pairings") or [] for k, v in homekit.items()}

    def _drop_pairings(self, key: str) -> None:
        config = self._load()
        with contextlib.suppress(KeyError, TypeError):
            config["homekit"][key].pop("pairings", None)
            self._config.write_text(_dump(config))

    def _write_config(self, enabled: dict[str, dict[str, Any]]) -> bool:
        """Returns whether the file changed."""
        old = self._load().get("homekit") or {}
        homekit = {}
        for key, cam in enabled.items():
            item = {"pin": cam["pin"], "name": cam["name"]}
            # keep what go2rtc wrote back (pairings, device keys)
            for field in ("device_id", "device_private", "pairings"):
                if (old.get(key) or {}).get(field):
                    item[field] = old[key][field]
            homekit[key] = item
        config = {
            "app": {"modules": ["api", "homekit", "rtsp", "srtp", "ffmpeg", "exec"]},
            "api": {"listen": f":{HOMEKIT_PORT}", "allow_paths": HAP_PATHS},
            # ffmpeg only runs when HomeKit needs it: H.265 cameras (HomeKit takes H.264
            # only) and audio (Opus); H.264 video is passed through untouched
            "exec": {"allow_paths": [self._ffmpeg]},
            "ffmpeg": {"bin": self._ffmpeg},
            # ffmpeg sources (H.265 → H.264, audio → Opus) read the stream back over
            # go2rtc's own RTSP server; localhost only
            "rtsp": {"listen": f"127.0.0.1:{RTSP_PORT}"},
            # HA's own go2rtc has SRTP on the default 8443
            "srtp": {"listen": f":{SRTP_PORT}"},
            "log": {"level": "info"},
            "streams": {
                key: [
                    cam["source"],
                    f"ffmpeg:{key}#video=h264",
                    f"ffmpeg:{key}#audio=opus",
                ]
                for key, cam in enabled.items()
            },
            "homekit": homekit,
        }
        text = "# Managed by the XMeye Full NVR integration\n" + _dump(config)
        try:
            if self._config.read_text() == text:
                return False
        except OSError:
            pass
        self._config.parent.mkdir(parents=True, exist_ok=True)
        self._config.write_text(text)
        return True

    # --- process ----------------------------------------------------------

    async def _run(self) -> None:
        while True:
            assert self._binary
            self._proc = await asyncio.create_subprocess_exec(
                self._binary,
                "-config",
                str(self._config),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            assert self._proc.stdout
            async for line in self._proc.stdout:
                text = line.decode(errors="replace").rstrip()
                if " ERR " in text or " WRN " in text:
                    _LOGGER.warning("go2rtc (HomeKit): %s", text)
                else:
                    _LOGGER.debug("go2rtc (HomeKit): %s", text)
            code = await self._proc.wait()
            self.error = f"go2rtc exited with code {code}"
            _LOGGER.warning("HomeKit go2rtc exited (%s), restarting in %d s", code, RESPAWN)
            await asyncio.sleep(RESPAWN)

    async def _stop_process(self) -> None:
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
