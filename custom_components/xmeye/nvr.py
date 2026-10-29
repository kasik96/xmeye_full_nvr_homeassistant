"""One NVR: connection details, cached file lists and motion events.

No Home Assistant imports: the standalone app uses this module too.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

from .const import CACHE_PAST, CACHE_TODAY, EVENT_MERGE_GAP, FILE_TAIL, MOTION_FILE_MAX
from .dvrip import DVRIPClient, Recording

if TYPE_CHECKING:
    from .alarm import AlarmListener
    from .go2rtc import Go2rtc


@dataclass
class Event:
    """Motion: adjacent motion files merged."""

    channel: int
    begin: datetime
    end: datetime


@dataclass
class XMeyeData:
    entry_id: str
    client: DVRIPClient
    serial: str
    model: str
    host: str
    rtsp_port: int
    username: str
    password: str
    # 0-based channel → name, only channels with a camera configured
    channels: dict[int, str]
    # all configured channels with their NVR titles
    nvr_channels: dict[int, str]
    transcode_h265: bool
    go2rtc: Go2rtc | None = None
    alarms: AlarmListener = None  # type: ignore[assignment]
    # local wall time (naive), like the NVR's file times
    now: Callable[[], datetime] = datetime.now
    _cache: dict[tuple[int, date], tuple[float, list[Recording]]] = field(
        default_factory=dict
    )
    _locks: dict[tuple[int, date], asyncio.Lock] = field(default_factory=dict)

    def rtsp_url(self, channel: int, sub: bool) -> str:
        user = quote(self.username, safe="")
        password = quote(self.password, safe="")
        return (
            f"rtsp://{self.host}:{self.rtsp_port}/user={user}&password={password}"
            f"&channel={channel + 1}&stream={1 if sub else 0}.sdp?"
        )

    def stream_name(self, channel: int, sub: bool) -> str:
        # Not "xmeye_<unique id>": HA's go2rtc provider uses that for the camera itself.
        return f"xmeye-nvr-{self.serial}-{channel + 1}{'-sub' if sub else ''}"

    async def recordings(self, channel: int, day: date) -> list[Recording]:
        key = (channel, day)
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            now = asyncio.get_running_loop().time()
            cached = self._cache.get(key)
            ttl = CACHE_TODAY if day >= self.now().date() else CACHE_PAST
            if cached and now - cached[0] < ttl:
                return cached[1]
            recs = await self.client.recordings(
                channel,
                datetime.combine(day, time.min),
                datetime.combine(day, time.max),
            )
            # Files spanning midnight show up on both days; keep them on the start day.
            recs = [r for r in recs if r.begin.date() == day]
            self._cache[key] = (now, recs)
            return recs

    async def events(self, channel: int, day: date) -> list[Event]:
        """Motion periods of a day.

        Exact times come from the live alarm stream (since the integration
        started listening). Before that, and as a fallback, short files the NVR
        tagged as motion; long [M] files (continuous recording with motion
        somewhere in it) say nothing about when it happened.
        """
        day_begin = datetime.combine(day, time.min)
        day_end = datetime.combine(day, time.max)
        periods = [
            (b, e) for b, e, kind in self.alarms.periods(channel, day_begin, day_end)
        ]
        live_since = self.alarms.history_start or datetime.max
        for rec in await self.recordings(channel, day):
            if (
                rec.kind in ("motion", "alarm")
                and rec.duration <= MOTION_FILE_MAX
                and rec.begin < live_since
            ):
                periods.append((rec.begin, rec.end))
        events: list[Event] = []
        for begin, end in sorted(periods):
            if events and begin - events[-1].end <= EVENT_MERGE_GAP:
                events[-1].end = max(events[-1].end, end)
            else:
                events.append(Event(channel, begin, end))
        return events

    async def recording_at(self, channel: int, when: datetime) -> Recording | None:
        """The file containing `when`, else the next one on the same day."""
        candidates: list[Recording] = []
        for day in (when.date() - timedelta(days=1), when.date()):
            candidates += await self.recordings(channel, day)
        for i, rec in enumerate(candidates):
            if rec.begin <= when < rec.end:
                after = candidates[i + 1] if i + 1 < len(candidates) else None
                if (
                    after
                    and rec.end - when < FILE_TAIL
                    and after.begin - rec.end < FILE_TAIL
                ):
                    return after
                return rec
        for rec in candidates:
            if rec.begin > when and rec.begin.date() == when.date():
                return rec
        return None

    async def days(self) -> list[date]:
        """Days with footage on any channel, newest first (this and last month)."""
        today = self.now().date()
        last_month = today.replace(day=1) - timedelta(days=1)
        result: set[date] = set()
        for month in (today, last_month):
            for day in await self.client.calendar(month.year, month.month):
                result.add(month.replace(day=day))
        return sorted((d for d in result if d <= today), reverse=True)


def channel_name(title: str, index: int) -> str:
    """Channel title as set on the NVR; "D06" style defaults become "Channel 6"."""
    title = title.strip()
    if not title or re.fullmatch(rf"[Dd]0*{index + 1}", title):
        return f"Channel {index + 1}"
    return title


def nvr_channels(titles: list[str], status: list[dict]) -> dict[int, str]:
    """Channels with a camera configured, with their NVR titles."""
    out: dict[int, str] = {}
    for index, title in enumerate(titles):
        state = status[index].get("Status") if index < len(status) else None
        if state == "NoConfig":
            continue
        out[index] = channel_name(title, index)
    return out


def visible_channels(nvr: dict[int, str], names: dict[str, str]) -> dict[int, str]:
    """Names from the options override the NVR's titles; an empty name hides a channel."""
    return {
        index: names.get(str(index + 1), title).strip()
        for index, title in nvr.items()
        if names.get(str(index + 1), title).strip()
    }


def serial_of(info: dict, fallback: str) -> str:
    return re.sub(r"\W", "", str(info.get("SerialNo") or fallback))


def as_dict(item: Recording | Event) -> dict[str, Any]:
    out: dict[str, Any] = {
        "begin": item.begin.strftime("%Y-%m-%d %H:%M:%S"),
        "end": item.end.strftime("%Y-%m-%d %H:%M:%S"),
    }
    if isinstance(item, Recording):
        out["kind"] = item.kind
    else:
        out["channel"] = item.channel + 1
    return out
