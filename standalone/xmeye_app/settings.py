"""Settings in settings.json; the NVR password and the Cloudflare tunnel token
in the system keychain.

The keychain is the Windows Credential Manager, the macOS Keychain or the
Secret Service on Linux. Without one (a Linux box without a desktop) the
secrets go to files only the user can read (also with XMEYE_NO_KEYRING=1,
for tests).
"""

from __future__ import annotations

import contextlib
import dataclasses
import hashlib
import hmac
import json
import logging
import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import APP_NAME
from .store import write_private

_LOGGER = logging.getLogger(__name__)

KEYRING_ACCOUNT = "nvr"
TUNNEL_ACCOUNT = "tunnel"
HASH_ITERATIONS = 240_000


@dataclass
class Settings:
    host: str = ""
    port: int = 34567
    rtsp_port: int = 554
    username: str = "admin"
    # {"<1-based channel>": name}; "" hides the channel
    names: dict[str, str] = field(default_factory=dict)
    transcode_h265: bool = True
    # reachable from other devices on the network (needs web_password)
    lan: bool = False
    web_password: str = ""  # PBKDF2 hash
    http_port: int = 18765
    # remote access through Cloudflare: "off", "quick" or "token" (needs web_password)
    tunnel: str = "off"
    tunnel_hostname: str = ""  # the public hostname of the user's own tunnel

    @property
    def configured(self) -> bool:
        return bool(self.host)

    def public(self) -> dict[str, Any]:
        """For the settings page: no secrets."""
        out = dataclasses.asdict(self)
        out["web_password"] = bool(self.web_password)
        return out


class SettingsFile:
    def __init__(self, directory: Path) -> None:
        self.path = directory / "settings.json"
        self._files = {
            KEYRING_ACCOUNT: directory / "nvr_password",
            TUNNEL_ACCOUNT: directory / "tunnel_token",
        }
        self.settings = self._read()

    def _read(self) -> Settings:
        try:
            raw = json.loads(self.path.read_text("utf-8"))
        except (OSError, ValueError):
            return Settings()
        known = {f.name for f in dataclasses.fields(Settings)}
        return Settings(**{k: v for k, v in raw.items() if k in known})

    def save(self) -> None:
        write_private(self.path, json.dumps(dataclasses.asdict(self.settings), indent=1))

    # --- secrets -------------------------------------------------------------

    def password(self) -> str:
        return self._secret(KEYRING_ACCOUNT)

    def set_password(self, value: str) -> None:
        self._set_secret(KEYRING_ACCOUNT, value)

    def tunnel_token(self) -> str:
        return self._secret(TUNNEL_ACCOUNT)

    def set_tunnel_token(self, value: str) -> None:
        self._set_secret(TUNNEL_ACCOUNT, value)

    def _secret(self, account: str) -> str:
        if os.environ.get("XMEYE_NO_KEYRING"):
            return self._read_file(account)
        try:
            import keyring  # noqa: PLC0415

            value = keyring.get_password(APP_NAME, account)
            if value is not None:
                return value
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("No keychain: %s", err)
        return self._read_file(account)

    def _read_file(self, account: str) -> str:
        try:
            return self._files[account].read_text("utf-8")
        except OSError:
            return ""

    def _set_secret(self, account: str, value: str) -> None:
        path = self._files[account]
        if os.environ.get("XMEYE_NO_KEYRING"):
            write_private(path, value)
            return
        try:
            import keyring  # noqa: PLC0415

            keyring.set_password(APP_NAME, account, value)
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("No keychain (%s), keeping the %s in a private file", err, account)
            write_private(path, value)
        else:
            with contextlib.suppress(OSError):
                path.unlink()


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, HASH_ITERATIONS)
    return f"pbkdf2${HASH_ITERATIONS}${salt.hex()}${digest.hex()}"


def check_password(password: str, stored: str) -> bool:
    try:
        _, iterations, salt, digest = stored.split("$")
        mine = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iterations))
    except ValueError:
        return False
    return hmac.compare_digest(mine.hex(), digest)
