"""Remote access through a Cloudflare Tunnel (cloudflared).

cloudflared connects out to Cloudflare and forwards the requests for a public
https address to this app on localhost, so nothing has to be opened on the
router. Two kinds:

- quick: a random *.trycloudflare.com address, no account; it changes every
  time the tunnel starts.
- token: the user's own tunnel from the Cloudflare dashboard, with a fixed
  hostname. The token goes to cloudflared in its environment, not on the
  command line (other users could read that).

Requests through the tunnel carry Cloudflare's headers; the server treats them
as remote, so they always need the web password.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import platform
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

import aiohttp

from xmeye_core import go2rtc
from xmeye_core.util import background, download_binary

_LOGGER = logging.getLogger(__name__)

VERSION = "2026.10.0"
_URL = f"https://github.com/cloudflare/cloudflared/releases/download/{VERSION}/"
# (system, arch) → (asset, sha256 of the asset, member of a .tgz)
DOWNLOADS = {
    ("Darwin", "arm64"): ("cloudflared-darwin-arm64.tgz", "a2f79ff7b9420aa537d74af239f376da170bbabeb529aec416002adac6a72e70", "cloudflared"),
    ("Darwin", "amd64"): ("cloudflared-darwin-amd64.tgz", "903845b81828c8cb3c5d13d816a2de71c06a3da5785469df8eb0e1b736d92f9f", "cloudflared"),
    ("Linux", "amd64"): ("cloudflared-linux-amd64", "d33ff2d14475178d2012c2c56beba87389ac5ded27649519f198a7d3134a99db", None),
    ("Linux", "arm64"): ("cloudflared-linux-arm64", "e6422b9d4f72d3194bc5a38676f13667c06666523217b842a877d72a80b5ac08", None),
    # also for Windows on ARM, which runs x64 programs
    ("Windows", "amd64"): ("cloudflared-windows-amd64.exe", "86aee4017b26625cee8484c113558f48effa4cd47f7aa05fcf425604e5d2b23c", None),
}  # fmt: skip
QUICK_URL = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
CONNECTED = re.compile(r"Registered tunnel connection|Connection [0-9a-f-]+ registered")
RESPAWN = 10


@dataclass(frozen=True)
class TunnelConfig:
    mode: str  # "off", "quick" or "token"
    port: int
    token: str = ""
    hostname: str = ""


async def binary(session: aiohttp.ClientSession, cache_dir: Path) -> str:
    found = shutil.which("cloudflared")
    if found:
        return found
    target = cache_dir / f"cloudflared_{VERSION}{'.exe' if platform.system() == 'Windows' else ''}"
    if target.is_file():
        return str(target)
    system, arch = go2rtc.platform_key()
    if system == "Windows":
        arch = "amd64"
    if (system, arch) not in DOWNLOADS:
        raise RuntimeError(f"no cloudflared download for {platform.system()} {platform.machine()}")
    asset, sha256, member = DOWNLOADS[(system, arch)]
    _LOGGER.info("Downloading cloudflared %s", VERSION)
    await download_binary(session, _URL + asset, sha256, target, member)
    return str(target)


class Tunnel:
    def __init__(self, cache_dir: Path) -> None:
        self._cache_dir = cache_dir
        self._config = TunnelConfig("off", 0)
        self._task: asyncio.Task | None = None
        self._proc: asyncio.subprocess.Process | None = None
        self.state = "off"  # off, starting, connected, error
        self.error = ""
        self.url = ""

    def status(self) -> dict[str, str]:
        return {"mode": self._config.mode, "state": self.state, "error": self.error, "url": self.url}

    async def apply(self, config: TunnelConfig) -> None:
        """Start, restart or stop cloudflared to match `config`."""
        if config == self._config and (self._task or config.mode == "off"):
            return
        await self.stop()
        self._config = config
        if config.mode == "off":
            return
        self.state, self.error = "starting", ""
        self.url = f"https://{config.hostname}" if config.mode == "token" and config.hostname else ""
        self._task = background(self._run(config), "xmeye tunnel")

    async def _run(self, config: TunnelConfig) -> None:
        async with aiohttp.ClientSession() as session:
            while True:
                try:
                    exe = await binary(session, self._cache_dir)
                    break
                except Exception as err:  # noqa: BLE001
                    self.state, self.error = "error", f"Could not download cloudflared: {err}"
                    _LOGGER.warning(self.error)
                    await asyncio.sleep(60)
        env = dict(os.environ)
        args = [exe, "tunnel", "--no-autoupdate"]
        if config.mode == "quick":
            args += ["--url", f"http://127.0.0.1:{config.port}"]
        else:
            args += ["run"]
            env["TUNNEL_TOKEN"] = config.token
        while True:
            self.state, self.error = "starting", ""
            self._proc = await asyncio.create_subprocess_exec(
                *args,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env=env,
            )
            assert self._proc.stdout
            last = ""
            async for raw in self._proc.stdout:
                line = raw.decode(errors="replace").rstrip()
                if config.token:
                    line = line.replace(config.token, "***")
                if config.mode == "quick" and (found := QUICK_URL.search(line)):
                    if "api.trycloudflare.com" not in found[0]:
                        self.url = found[0]
                if CONNECTED.search(line):
                    self.state, self.error = "connected", ""
                if " ERR " in line:
                    last = line.split(" ERR ", 1)[1].strip()
                    _LOGGER.warning("cloudflared: %s", line)
                else:
                    _LOGGER.debug("cloudflared: %s", line)
            code = await self._proc.wait()
            self.state, self.error = "error", last or f"cloudflared exited ({code})"
            if config.mode == "quick":
                self.url = ""
            _LOGGER.warning("cloudflared exited (%s), restarting in %d s", code, RESPAWN)
            await asyncio.sleep(RESPAWN)

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        if self._proc and self._proc.returncode is None:
            self._proc.terminate()
            try:
                await asyncio.wait_for(self._proc.wait(), 5)
            except TimeoutError:
                self._proc.kill()
        self._proc = None
        self.state, self.error, self.url = "off", "", ""
        self._config = TunnelConfig("off", 0)
