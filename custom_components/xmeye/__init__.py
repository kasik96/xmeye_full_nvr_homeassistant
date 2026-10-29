"""XMeye / Xiongmai NVR: live cameras, recordings on the NVR and a viewer panel."""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any
from urllib.parse import quote

from homeassistant.components.ffmpeg import get_ffmpeg_manager
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_USERNAME,
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import dt as dt_util

from .const import (
    CACHE_PAST,
    CACHE_TODAY,
    CONF_NAMES,
    CONF_RTSP_PORT,
    CONF_TRANSCODE_H265,
    DEFAULT_RTSP_PORT,
    DEFAULT_TRANSCODE_H265,
    DOMAIN,
    EVENT_MERGE_GAP,
    FILE_TAIL,
    MOTION_FILE_MAX,
)
from .alarm import AlarmListener
from .dvrip import DVRIPAuthError, DVRIPClient, DVRIPError, Recording
from .go2rtc import Go2rtc
from .homekit import HomeKitManager
from .playback import PlaybackManager, PlaybackView
from .thumbnails import ThumbnailCache

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.BINARY_SENSOR, Platform.CAMERA]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


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
            ttl = CACHE_TODAY if day >= dt_util.now().date() else CACHE_PAST
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
        today = dt_util.now().date()
        last_month = today.replace(day=1) - timedelta(days=1)
        result: set[date] = set()
        for month in (today, last_month):
            for day in await self.client.calendar(month.year, month.month):
                result.add(month.replace(day=day))
        return sorted((d for d in result if d <= today), reverse=True)


type XMeyeConfigEntry = ConfigEntry[XMeyeData]


def channel_name(title: str, index: int) -> str:
    """Channel title as set on the NVR; "D06" style defaults become "Channel 6"."""
    title = title.strip()
    if not title or re.fullmatch(rf"[Dd]0*{index + 1}", title):
        return f"Channel {index + 1}"
    return title


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    ffmpeg = get_ffmpeg_manager(hass).binary
    manager = PlaybackManager(hass, ffmpeg)
    await manager.async_setup()
    homekit = HomeKitManager(hass, ffmpeg)
    await homekit.async_setup()
    hass.data[DOMAIN] = {
        "playback": manager,
        "thumbs": ThumbnailCache(hass, ffmpeg),
        "homekit": homekit,
    }
    hass.http.register_view(PlaybackView(manager))

    from . import api, panel  # noqa: PLC0415

    api.async_setup(hass)
    await panel.async_setup(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: XMeyeConfigEntry) -> bool:
    client = DVRIPClient(
        entry.data[CONF_HOST],
        entry.data[CONF_PORT],
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
    )
    try:
        info = await client.system_info()
        titles = await client.channel_titles()
        status = await client.channel_status()
    except DVRIPAuthError as err:
        await client.close()
        raise ConfigEntryAuthFailed(str(err)) from err
    except DVRIPError as err:
        await client.close()
        raise ConfigEntryNotReady(str(err)) from err

    nvr_channels: dict[int, str] = {}
    for index, title in enumerate(titles):
        state = status[index].get("Status") if index < len(status) else None
        if state == "NoConfig":
            continue
        nvr_channels[index] = channel_name(title, index)
    # Names from the options override the NVR's titles; an empty name hides a channel.
    names = entry.options.get(CONF_NAMES, {})
    channels = {
        index: names.get(str(index + 1), title).strip()
        for index, title in nvr_channels.items()
        if names.get(str(index + 1), title).strip()
    }

    data = entry.runtime_data = XMeyeData(
        entry_id=entry.entry_id,
        client=client,
        serial=re.sub(r"\W", "", str(info.get("SerialNo") or entry.entry_id)),
        model=str(info.get("HardWare") or "NVR"),
        host=entry.data[CONF_HOST],
        rtsp_port=entry.data.get(CONF_RTSP_PORT, DEFAULT_RTSP_PORT),
        username=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
        channels=channels,
        nvr_channels=nvr_channels,
        transcode_h265=entry.options.get(CONF_TRANSCODE_H265, DEFAULT_TRANSCODE_H265),
    )

    dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, data.serial)},
        name=f"XMeye {data.model}",
        manufacturer="Xiongmai",
        model=data.model,
        configuration_url=f"http://{data.host}",
    )

    # One NVR connection per stream, shared by WebRTC, HomeKit and snapshots.
    data.go2rtc = Go2rtc.from_hass(hass)
    if data.go2rtc:
        streams = {
            data.stream_name(ch, sub): data.rtsp_url(ch, sub)
            for ch in channels
            for sub in (False, True)
        }
        if not await data.go2rtc.add_streams(streams):
            data.go2rtc = None

    homekit: HomeKitManager = hass.data[DOMAIN]["homekit"]
    for ch, name in channels.items():
        sources = [
            data.go2rtc.rtsp_url(data.stream_name(ch, sub))
            if data.go2rtc
            else data.rtsp_url(ch, sub)
            for sub in (False, True)
        ]
        await homekit.register(entry.entry_id, data.serial, ch, name, *sources)
    await homekit.apply()

    data.alarms = AlarmListener(hass, client, entry.entry_id)
    await data.alarms.async_start()

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(hass: HomeAssistant, entry: XMeyeConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: XMeyeConfigEntry) -> bool:
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    data = entry.runtime_data
    await data.alarms.async_stop()
    await hass.data[DOMAIN]["playback"].close_client(data.client)
    await data.client.close()
    return True


def loaded_entries(hass: HomeAssistant) -> list[XMeyeConfigEntry]:
    return [
        e
        for e in hass.config_entries.async_entries(DOMAIN)
        if e.state is ConfigEntryState.LOADED
    ]


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
