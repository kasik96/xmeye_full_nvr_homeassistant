"""Live alarms from the NVR (DVRIP 1500 → 1504) and the motion event history.

The NVR tags recording files with [M] when motion happened somewhere in them,
which is useless for continuous recording (hour-long files). The live alarm
stream has exact start/stop times; they are kept in HA storage for the panel
(only times, no video), and drive the motion binary sensors.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import datetime, timedelta
import json

from .dvrip import (
    MSG_KEEPALIVE,
    Connection,
    DVRIPAuthError,
    DVRIPClient,
    DVRIPError,
)
from .util import Store, background

_LOGGER = logging.getLogger(__name__)

MSG_ALARM_SUBSCRIBE = 1500
MSG_ALARM = 1504
RETRY = 30
KEEP_DAYS = 14
SAVE_DELAY = 30
TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
# NVR event names → our kinds
KINDS = {
    "VideoMotion": "motion",
    "appEventHumanDetectAlarm": "person",
    "HumanDetect": "person",
}


class AlarmListener:
    """Keeps an alarm subscription open and stores motion periods."""

    def __init__(self, client: DVRIPClient, store: Store) -> None:
        self._client = client
        self._store = store
        # finished events: [channel (0-based), kind, begin, end]
        self.events: list[list] = []
        # running: (channel, kind) -> begin
        self.active: dict[tuple[int, str], datetime] = {}
        self._listeners: list[Callable[[], None]] = []
        self._task: asyncio.Task | None = None
        self.connected = False

    async def async_start(self) -> None:
        stored = await self._store.async_load() or {}
        self.events = stored.get("events", [])
        self._task = background(self._run(), "xmeye alarms")

    async def async_stop(self) -> None:
        if self._task:
            self._task.cancel()
        self._close_running(datetime.now())
        await self._store.async_save(self._data())

    def async_add_listener(self, update: Callable[[], None]) -> Callable[[], None]:
        self._listeners.append(update)
        return lambda: self._listeners.remove(update)

    def is_on(self, channel: int, kind: str = "motion") -> bool:
        return (channel, kind) in self.active

    def periods(self, channel: int, begin: datetime, end: datetime) -> list[tuple[datetime, datetime, str]]:
        """Motion periods of a channel overlapping [begin, end], running ones up to now."""
        out = []
        for ch, kind, b, e in self.events:
            if ch != channel:
                continue
            b, e = datetime.strptime(b, TIME_FORMAT), datetime.strptime(e, TIME_FORMAT)
            if e >= begin and b <= end:
                out.append((b, e, kind))
        now = datetime.now()
        for (ch, kind), b in self.active.items():
            if ch == channel and b <= end:
                out.append((b, now, kind))
        return sorted(out)

    @property
    def history_start(self) -> datetime | None:
        if not self.events:
            return None
        return min(datetime.strptime(e[2], TIME_FORMAT) for e in self.events)

    def _data(self) -> dict:
        return {"events": self.events}

    async def _run(self) -> None:
        while True:
            try:
                await self._listen()
            except asyncio.CancelledError:
                raise
            except DVRIPAuthError as err:
                _LOGGER.warning("Alarm subscription rejected: %s", err)
            except (DVRIPError, OSError) as err:
                _LOGGER.debug("Alarm connection lost: %s", err)
            self.connected = False
            self._close_running(datetime.now())
            self._notify()
            await asyncio.sleep(RETRY)

    async def _listen(self) -> None:
        conn: Connection = await self._client.open_session()
        try:
            await conn.send(MSG_ALARM_SUBSCRIBE, {"Name": ""})
            interval = int(self._client.login_info.get("AliveInterval") or 20)
            loop = asyncio.get_running_loop()
            next_alive = loop.time() + interval
            self.connected = True
            _LOGGER.debug("Alarm subscription open")
            while True:
                timeout = max(1.0, next_alive - loop.time())
                try:
                    msg_id, body = await conn.read(timeout=timeout)
                except DVRIPError:
                    if loop.time() < next_alive:
                        raise
                    msg_id, body = 0, b""
                if loop.time() >= next_alive:
                    await conn.send(MSG_KEEPALIVE, {"Name": "KeepAlive"})
                    next_alive = loop.time() + interval
                if msg_id == MSG_ALARM:
                    self._handle(body)
        finally:
            await conn.close()

    def _handle(self, body: bytes) -> None:
        try:
            info = json.loads(body.rstrip(b"\n\0")).get("AlarmInfo") or {}
        except ValueError:
            return
        _LOGGER.debug("Alarm %s", info)
        kind = KINDS.get(info.get("Event", ""))
        if kind is None:
            return
        try:
            channel = int(info.get("Channel", -1))
            when = datetime.strptime(info["StartTime"], TIME_FORMAT)
        except (KeyError, ValueError):
            when = datetime.now()
        key = (channel, kind)
        if info.get("Status") == "Start":
            self.active.setdefault(key, when)
        elif key in self.active:
            begin = self.active.pop(key)
            self._add(channel, kind, begin, max(datetime.now(), begin))
        self._notify()

    def _add(self, channel: int, kind: str, begin: datetime, end: datetime) -> None:
        self.events.append([channel, kind, begin.strftime(TIME_FORMAT), end.strftime(TIME_FORMAT)])
        cutoff = (datetime.now() - timedelta(days=KEEP_DAYS)).strftime(TIME_FORMAT)
        self.events = [e for e in self.events if e[3] >= cutoff]
        self._store.async_delay_save(self._data, SAVE_DELAY)

    def _close_running(self, now: datetime) -> None:
        for (channel, kind), begin in list(self.active.items()):
            self._add(channel, kind, begin, now)
        self.active.clear()

    def _notify(self) -> None:
        for update in list(self._listeners):
            update()
