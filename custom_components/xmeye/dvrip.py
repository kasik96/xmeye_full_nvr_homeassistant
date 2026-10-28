"""Async client for the Xiongmai DVRIP ("Sofia") protocol, port 34567.

Only what is needed to list and download recordings. Verified against an
NBD88X16S-KL-V3 NVR (firmware V4.03.R11), see NOTES.md.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import logging
import re
import struct
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime
from typing import Any

_LOGGER = logging.getLogger(__name__)

HEADER = struct.Struct("<BB2xIIBBHI")

MSG_LOGIN = 1000
MSG_KEEPALIVE = 1006
MSG_INFO = 1020
MSG_CONFIG_GET = 1042
MSG_CHANNEL_TITLE = 1048
MSG_PLAYBACK = 1420
MSG_PLAYBACK_CLAIM = 1424
MSG_PLAYBACK_DATA = 1422
MSG_DOWNLOAD_DATA = 1426
MSG_FILE_QUERY = 1440
MSG_CALENDAR = 1446

RET_OK = (100, 515)
RET_NO_FILES = (109, 119)
RET_BAD_PASSWORD = (203, 205, 206)

TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
FILE_PAGE = 64
TIMEOUT = 10
SOFIA_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"

# Recording kinds from the "[X]" tag in file names.
KINDS = {"R": "regular", "M": "motion", "A": "alarm", "H": "manual"}
_KIND_RE = re.compile(r"\[([A-Z])\]")


class DVRIPError(Exception):
    """Protocol or connection error."""


class DVRIPAuthError(DVRIPError):
    """Wrong user name or password."""


def sofia_hash(password: str) -> str:
    digest = hashlib.md5(password.encode()).digest()
    return "".join(
        SOFIA_CHARS[(digest[i] + digest[i + 1]) % 62] for i in range(0, 16, 2)
    )


def _hex(value: Any) -> int:
    if isinstance(value, int):
        return value
    return int(str(value), 16)


@dataclass(frozen=True)
class Recording:
    """One file on the NVR disk."""

    channel: int  # 0-based
    begin: datetime
    end: datetime
    file_name: str
    size_kb: int

    @property
    def duration(self) -> int:
        return max(0, int((self.end - self.begin).total_seconds()))

    @property
    def kind(self) -> str:
        match = _KIND_RE.search(self.file_name)
        return KINDS.get(match.group(1), "regular") if match else "regular"

    @classmethod
    def from_json(cls, channel: int, item: dict[str, Any]) -> Recording:
        return cls(
            channel=channel,
            begin=datetime.strptime(item["BeginTime"], TIME_FORMAT),
            end=datetime.strptime(item["EndTime"], TIME_FORMAT),
            file_name=item["FileName"],
            size_kb=_hex(item.get("FileLength", 0)),
        )


class Connection:
    """One TCP connection: DVRIP framing only."""

    def __init__(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        self._reader = reader
        self._writer = writer
        self.session = 0
        self._seq = 0

    @classmethod
    async def open(cls, host: str, port: int) -> Connection:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port), TIMEOUT
            )
        except (OSError, TimeoutError) as err:
            raise DVRIPError(f"cannot connect to {host}:{port}: {err}") from err
        return cls(reader, writer)

    async def send(self, msg_id: int, payload: dict[str, Any] | None) -> None:
        body = b""
        if payload is not None:
            if self.session:
                payload = {**payload, "SessionID": f"0x{self.session:08X}"}
            body = json.dumps(payload, separators=(",", ":")).encode() + b"\n\0"
        header = HEADER.pack(0xFF, 1, self.session, self._seq, 0, 0, msg_id, len(body))
        self._seq += 1
        self._writer.write(header + body)
        await self._writer.drain()

    async def read(self, timeout: float = TIMEOUT) -> tuple[int, bytes]:
        try:
            header = await asyncio.wait_for(self._reader.readexactly(20), timeout)
            magic, _, session, _, _, _, msg_id, length = HEADER.unpack(header)
            if magic != 0xFF:
                raise DVRIPError(f"bad packet header {header.hex()}")
            body = await asyncio.wait_for(self._reader.readexactly(length), timeout)
        except (OSError, TimeoutError, asyncio.IncompleteReadError) as err:
            raise DVRIPError(f"read failed: {err!r}") from err
        if session:
            self.session = session
        return msg_id, body

    async def request(
        self, msg_id: int, payload: dict[str, Any] | None
    ) -> dict[str, Any]:
        """Send and wait for the reply (reply id = request id + 1)."""
        await self.send(msg_id, payload)
        while True:
            reply_id, body = await self.read()
            if reply_id == msg_id + 1:
                break
            _LOGGER.debug("Ignoring message %s while waiting for %s", reply_id, msg_id + 1)
        text = body.rstrip(b"\n\0").decode("utf-8", "replace")
        try:
            return json.loads(text)
        except ValueError as err:
            raise DVRIPError(f"bad JSON reply to {msg_id}: {text[:200]}") from err

    async def login(self, username: str, password: str) -> dict[str, Any]:
        reply = await self.request(
            MSG_LOGIN,
            {
                "EncryptType": "MD5",
                "LoginType": "DVRIP-Web",
                "PassWord": sofia_hash(password),
                "UserName": username,
            },
        )
        ret = reply.get("Ret")
        if ret in RET_BAD_PASSWORD:
            raise DVRIPAuthError(f"login rejected (Ret {ret})")
        if ret not in RET_OK:
            raise DVRIPError(f"login failed (Ret {ret})")
        self.session = _hex(reply["SessionID"])
        return reply

    async def close(self) -> None:
        self._writer.close()
        with contextlib.suppress(Exception):
            await self._writer.wait_closed()

    @property
    def closed(self) -> bool:
        return self._writer.is_closing()


class DVRIPClient:
    """Logged-in control connection, opened on demand and closed when idle."""

    IDLE_CLOSE = 120

    def __init__(self, host: str, port: int, username: str, password: str) -> None:
        self.host = host
        self.port = port
        self._username = username
        self._password = password
        self._conn: Connection | None = None
        self._lock = asyncio.Lock()
        self._alive_interval = 20
        self._keepalive: asyncio.Task | None = None
        self._last_used = 0.0
        self.login_info: dict[str, Any] = {}

    async def _connect(self) -> Connection:
        conn = await Connection.open(self.host, self.port)
        try:
            self.login_info = await conn.login(self._username, self._password)
        except BaseException:
            await conn.close()
            raise
        self._alive_interval = int(self.login_info.get("AliveInterval") or 20)
        return conn

    async def open_session(self) -> Connection:
        """A separate logged-in control connection (used per playback)."""
        return await self._connect()

    async def request(self, msg_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        async with self._lock:
            loop = asyncio.get_running_loop()
            for attempt in (1, 2):
                if self._conn is None or self._conn.closed:
                    self._conn = await self._connect()
                    self._keepalive = loop.create_task(self._keepalive_loop())
                try:
                    reply = await self._conn.request(msg_id, payload)
                except DVRIPError:
                    await self._drop()
                    if attempt == 2:
                        raise
                    continue
                self._last_used = loop.time()
                return reply
        raise AssertionError

    async def _keepalive_loop(self) -> None:
        loop = asyncio.get_running_loop()
        while True:
            await asyncio.sleep(self._alive_interval)
            async with self._lock:
                if self._conn is None:
                    return
                if loop.time() - self._last_used > self.IDLE_CLOSE:
                    await self._drop(cancel=False)
                    return
                try:
                    await self._conn.request(MSG_KEEPALIVE, {"Name": "KeepAlive"})
                except DVRIPError:
                    await self._drop(cancel=False)
                    return

    async def _drop(self, cancel: bool = True) -> None:
        if cancel and self._keepalive:
            self._keepalive.cancel()
        self._keepalive = None
        if self._conn:
            await self._conn.close()
        self._conn = None

    async def close(self) -> None:
        async with self._lock:
            await self._drop()

    # --- API ---------------------------------------------------------------

    async def system_info(self) -> dict[str, Any]:
        reply = await self.request(MSG_INFO, {"Name": "SystemInfo"})
        return reply.get("SystemInfo") or {}

    async def channel_titles(self) -> list[str]:
        reply = await self.request(MSG_CHANNEL_TITLE, {"Name": "ChannelTitle"})
        return [str(t).strip() for t in reply.get("ChannelTitle") or []]

    async def channel_status(self) -> list[dict[str, Any]]:
        reply = await self.request(MSG_CONFIG_GET, {"Name": "NetWork.ChnStatus"})
        return reply.get("NetWork.ChnStatus") or []

    async def calendar(self, year: int, month: int) -> list[int]:
        """Days of the month (1-based) that have recordings on any channel."""
        reply = await self.request(
            MSG_CALENDAR,
            {
                "Name": "OPSCalendar",
                "OPSCalendar": {
                    "Year": year,
                    "Month": month,
                    "Event": "*",
                    "FileType": "h264",
                    "Rev": "",
                },
            },
        )
        if reply.get("Ret") not in RET_OK:
            return []
        mask = _hex((reply.get("OPSCalendar") or {}).get("Mask", 0))
        return [day for day in range(1, 32) if mask & (1 << (day - 1))]

    async def recordings(
        self, channel: int, begin: datetime, end: datetime
    ) -> list[Recording]:
        """All files of a channel (0-based) overlapping [begin, end]."""
        found: dict[str, Recording] = {}
        start = begin
        while True:
            reply = await self.request(
                MSG_FILE_QUERY,
                {
                    "Name": "OPFileQuery",
                    "OPFileQuery": {
                        "BeginTime": start.strftime(TIME_FORMAT),
                        "EndTime": end.strftime(TIME_FORMAT),
                        "Channel": channel,
                        "DriverTypeMask": "0x0000FFFF",
                        "Event": "*",
                        "Type": "h264",
                        "StreamType": "0x00000000",
                    },
                },
            )
            ret = reply.get("Ret")
            if ret in RET_NO_FILES:
                break
            if ret not in RET_OK + (110, 111):
                raise DVRIPError(f"file query failed (Ret {ret})")
            page = [Recording.from_json(channel, i) for i in reply.get("OPFileQuery") or []]
            new = [r for r in page if r.file_name not in found]
            for rec in new:
                found[rec.file_name] = rec
            if len(page) < FILE_PAGE or not new:
                break
            start = max(r.end for r in page)
            if start >= end:
                break
        return sorted(found.values(), key=lambda r: r.begin)

    @contextlib.asynccontextmanager
    async def download(
        self, rec: Recording, start: datetime | None = None
    ) -> AsyncIterator[AsyncIterator[bytes]]:
        """Stream a recording's raw bytes (Xiongmai frame format).

        Uses its own login: second TCP connection claims the playback with
        the session id, the control connection starts it (DVRIP-Web clients
        do the same). An empty data packet ends the file.
        """
        control = await self.open_session()
        data: Connection | None = None
        params = {
            "PlayMode": "ByName",
            "FileName": rec.file_name,
            "StreamType": 0,
            "Value": 0,
            "TransMode": "TCP",
        }
        body = {
            "StartTime": (start or rec.begin).strftime(TIME_FORMAT),
            "EndTime": rec.end.strftime(TIME_FORMAT),
            "Parameter": params,
        }
        keepalive: asyncio.Task | None = None
        try:
            data = await Connection.open(self.host, self.port)
            data.session = control.session
            reply = await data.request(
                MSG_PLAYBACK_CLAIM,
                {"Name": "OPPlayBack", "OPPlayBack": {"Action": "Claim", **body}},
            )
            if reply.get("Ret") not in RET_OK:
                raise DVRIPError(f"playback claim failed (Ret {reply.get('Ret')})")
            reply = await control.request(
                MSG_PLAYBACK,
                {"Name": "OPPlayBack", "OPPlayBack": {"Action": "DownloadStart", **body}},
            )
            if reply.get("Ret") not in RET_OK:
                raise DVRIPError(f"download start failed (Ret {reply.get('Ret')})")

            async def _keepalive() -> None:
                while True:
                    await asyncio.sleep(self._alive_interval)
                    await control.send(MSG_KEEPALIVE, {"Name": "KeepAlive"})
                    # Replies are not read; the NVR does not need us to.

            keepalive = asyncio.get_running_loop().create_task(_keepalive())

            async def _chunks() -> AsyncIterator[bytes]:
                assert data is not None
                while True:
                    msg_id, chunk = await data.read(timeout=30)
                    if msg_id not in (MSG_DOWNLOAD_DATA, MSG_PLAYBACK_DATA):
                        _LOGGER.debug("Ignoring message %s on data connection", msg_id)
                        continue
                    if not chunk:
                        return
                    yield chunk

            yield _chunks()
        finally:
            if keepalive:
                keepalive.cancel()
            with contextlib.suppress(Exception):
                await control.send(
                    MSG_PLAYBACK,
                    {"Name": "OPPlayBack", "OPPlayBack": {"Action": "DownloadStop", **body}},
                )
            if data:
                await data.close()
            await control.close()


# --- Media frames -----------------------------------------------------------

FRAME_I = (0xFC, 0xFE)
FRAME_P = 0xFD
FRAME_AUDIO = 0xFA
FRAME_INFO = 0xF9
_FRAME_TYPES = bytes(range(0xF9, 0xFF))

CODEC_H264 = 2
CODEC_H265 = 3
AUDIO_ALAW = 0x0E
AUDIO_ULAW = 0x0A


@dataclass(frozen=True, slots=True)
class Frame:
    kind: int
    data: bytes  # payload without the Xiongmai header
    codec: int = 0  # video codec (I-frames) or audio codec
    fps: int = 0  # I-frames only


class FrameParser:
    """Splits the joined media bytes into frames, resyncing on garbage."""

    def __init__(self) -> None:
        self._buf = bytearray()
        self.skipped = 0

    def feed(self, chunk: bytes) -> list[Frame]:
        buf = self._buf
        buf += chunk
        frames: list[Frame] = []
        pos = 0
        while True:
            if len(buf) - pos < 16:
                break
            if buf[pos : pos + 3] != b"\0\0\1" or buf[pos + 3] not in _FRAME_TYPES:
                nxt = self._resync(buf, pos + 1)
                self.skipped += nxt - pos
                pos = nxt
                continue
            kind = buf[pos + 3]
            if kind in FRAME_I:
                hdr, size = 16, int.from_bytes(buf[pos + 12 : pos + 16], "little")
            elif kind == FRAME_P:
                hdr, size = 8, int.from_bytes(buf[pos + 4 : pos + 8], "little")
            else:
                hdr, size = 8, int.from_bytes(buf[pos + 6 : pos + 8], "little")
            if size > 8 * 1024 * 1024:
                self.skipped += 1
                pos += 1
                continue
            if len(buf) - pos < hdr + size:
                break
            payload = bytes(buf[pos + hdr : pos + hdr + size])
            if kind in FRAME_I:
                frame = Frame(kind, payload, buf[pos + 4] & 0x0F, buf[pos + 5])
            elif kind in (FRAME_AUDIO, FRAME_INFO):
                frame = Frame(kind, payload, buf[pos + 4])
            else:
                frame = Frame(kind, payload)
            frames.append(frame)
            pos += hdr + size
        del buf[:pos]
        return frames

    @staticmethod
    def _resync(buf: bytearray, start: int) -> int:
        while True:
            idx = buf.find(b"\0\0\1", start)
            if idx < 0:
                return max(start, len(buf) - 3)
            if idx + 3 < len(buf) and buf[idx + 3] in _FRAME_TYPES:
                return idx
            if idx + 3 >= len(buf):
                return idx
            start = idx + 1
