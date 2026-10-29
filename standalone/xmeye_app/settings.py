"""Settings in settings.json; the NVR password in the system keychain.

The keychain is the Windows Credential Manager, the macOS Keychain or the
Secret Service on Linux. Without one (a Linux box without a desktop) the
password goes to a file only the user can read (also with XMEYE_NO_KEYRING=1,
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
        self._password_file = directory / "nvr_password"
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

    # --- NVR password --------------------------------------------------------

    def password(self) -> str:
        if os.environ.get("XMEYE_NO_KEYRING"):
            return self._read_password_file()
        try:
            import keyring  # noqa: PLC0415

            value = keyring.get_password(APP_NAME, KEYRING_ACCOUNT)
            if value is not None:
                return value
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("No keychain: %s", err)
        return self._read_password_file()

    def _read_password_file(self) -> str:
        try:
            return self._password_file.read_text("utf-8")
        except OSError:
            return ""

    def set_password(self, value: str) -> None:
        if os.environ.get("XMEYE_NO_KEYRING"):
            write_private(self._password_file, value)
            return
        try:
            import keyring  # noqa: PLC0415

            keyring.set_password(APP_NAME, KEYRING_ACCOUNT, value)
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("No keychain (%s), keeping the NVR password in a private file", err)
            write_private(self._password_file, value)
        else:
            with contextlib.suppress(OSError):
                self._password_file.unlink()


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
