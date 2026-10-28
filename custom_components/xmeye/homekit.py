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
import logging
import secrets
import shutil
from pathlib import Path
from typing import Any

import yaml

from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers.storage import Store

_LOGGER = logging.getLogger(__name__)

HOMEKIT_PORT = 51830
SRTP_PORT = 51831
RESPAWN = 10
# HAP endpoints; everything else of go2rtc's API stays closed on the LAN
HAP_PATHS = ["/pair-setup", "/pair-verify", "/pairings", "/accessories", "/characteristics"]
# Trivial codes Apple rejects
BAD_PINS = {f"{d}" * 8 for d in range(10)} | {"12345678", "87654321"}


def _new_pin() -> str:
    while True:
        pin = f"{secrets.randbelow(10**8):08d}"
        if pin not in BAD_PINS:
            return pin


def format_pin(pin: str) -> str:
    return f"{pin[:3]}-{pin[3:5]}-{pin[5:]}"


class HomeKitManager:
    """Owns the HomeKit go2rtc process for all NVRs."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
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
        """Write the config and (re)start go2rtc for the enabled cameras."""
        async with self._lock:
            await self._store.async_save({"cameras": self.cameras})
            enabled = {k: c for k, c in self.cameras.items() if c["enabled"] and c.get("source")}
            await self._stop_process()
            if not enabled:
                return
            if not self._binary:
                self.error = "go2rtc binary not found (needs Home Assistant OS or the container image)"
                _LOGGER.warning(self.error)
                return
            await self.hass.async_add_executor_job(self._write_config, enabled)
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

    def status(self) -> dict[str, Any]:
        paired = self._read_pairings()
        return {
            "available": bool(self._binary),
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
            self._config.write_text(yaml.safe_dump(config, sort_keys=False))

    def _write_config(self, enabled: dict[str, dict[str, Any]]) -> None:
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
            "app": {"modules": ["api", "homekit", "rtsp", "srtp"]},
            "api": {"listen": f":{HOMEKIT_PORT}", "allow_paths": HAP_PATHS},
            "rtsp": {"listen": ""},
            # HA's own go2rtc has SRTP on the default 8443
            "srtp": {"listen": f":{SRTP_PORT}"},
            "log": {"level": "info"},
            "streams": {key: cam["source"] for key, cam in enabled.items()},
            "homekit": homekit,
        }
        self._config.parent.mkdir(parents=True, exist_ok=True)
        self._config.write_text(
            "# Managed by the XMeye Full NVR integration\n"
            + yaml.safe_dump(config, sort_keys=False)
        )

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
