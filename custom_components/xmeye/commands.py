"""The panel's commands, shared by the integration (HA WebSocket API) and the
standalone app (its own WebSocket). No Home Assistant imports."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from aiohttp import web
import voluptuous as vol

from .alarm import KINDS
from .dvrip import FRAME_I, FRAME_P, DVRIPError, FrameParser, stamp_seconds
from .homekit import HomeKitManager
from .nvr import XMeyeData, as_dict
from .playback import FAST_SPEED, PLAYLIST, PlaybackManager
from .thumbnails import ThumbnailCache

TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
RECORD_MASKS = {"always": "0x00000007", "motion": "0x00000006"}


class APIError(Exception):
    """Sent to the panel as the error message."""


@dataclass
class Services:
    # loaded NVRs by entry id
    nvrs: Callable[[], dict[str, XMeyeData]]
    playback: PlaybackManager
    thumbs: ThumbnailCache
    homekit: HomeKitManager
    # camera unique id → entity id the panel streams through
    entity_id: Callable[[str], str | None]
    # URL prefix of the HLS sessions
    hls_url: str = "/api/xmeye/hls"
    now: Callable[[], datetime] = field(default=datetime.now)
    # the NVR's address or our user's password changed: {"host", "port"} / {"password"}
    credentials_changed: Callable[[str, dict[str, Any]], Awaitable[None]] | None = None


Handler = Callable[[Services, dict[str, Any]], Awaitable[Any]]


@dataclass
class Command:
    name: str
    schema: dict
    handler: Handler
    admin: bool = False


COMMANDS: list[Command] = []


def command(name: str, schema: dict | None = None, admin: bool = False):
    def wrap(handler: Handler) -> Handler:
        COMMANDS.append(Command(name, schema or {}, handler, admin))
        return handler

    return wrap


def _nvr(svc: Services, entry_id: str) -> XMeyeData:
    data = svc.nvrs().get(entry_id)
    if data is None:
        raise APIError("NVR not loaded")
    return data


def _channel(data: XMeyeData, channel: int) -> int:
    if channel - 1 not in data.channels:
        raise APIError("unknown channel")
    return channel - 1


@command("cameras")
async def cameras(svc: Services, msg: dict[str, Any]) -> Any:
    out = []
    for entry_id, data in svc.nvrs().items():
        for ch, name in data.channels.items():
            uid = f"{data.serial}_{ch + 1}"
            out.append(
                {
                    "entry_id": entry_id,
                    "channel": ch + 1,
                    "name": name,
                    "entity_id": svc.entity_id(uid),
                    "sub_entity_id": svc.entity_id(f"{uid}_sub"),
                }
            )
    return {"cameras": out}


@command("day", {vol.Required("entry_id"): str, vol.Required("channel"): int, vol.Optional("date"): str})
async def day(svc: Services, msg: dict[str, Any]) -> Any:
    """Recordings and motion events of one camera on one day."""
    data = _nvr(svc, msg["entry_id"])
    channel = _channel(data, msg["channel"])
    when = date.fromisoformat(msg["date"]) if msg.get("date") else data.now().date()
    try:
        recs = await data.recordings(channel, when)
        events = await data.events(channel, when)
        days = await data.days()
    except DVRIPError as err:
        raise APIError(str(err)) from err
    return {
        "date": when.isoformat(),
        "days": [d.isoformat() for d in days],
        "recordings": [as_dict(r) for r in recs],
        "events": [as_dict(e) for e in reversed(events)],
    }


@command(
    "events",
    {
        vol.Optional("hours", default=24): vol.All(int, vol.Range(min=1, max=72)),
        vol.Optional("limit", default=40): vol.All(int, vol.Range(min=1, max=500)),
        # only events where the NVR detected this
        vol.Optional("kind"): vol.In(KINDS),
    },
)
async def events(svc: Services, msg: dict[str, Any]) -> Any:
    """Recent motion events of all cameras, newest first."""
    kind = msg.get("kind")
    now = svc.now()
    since = now - timedelta(hours=msg["hours"])
    days = sorted({since.date(), now.date()})
    found_all = []
    for entry_id, data in svc.nvrs().items():
        for ch in data.channels:
            for day_ in days:
                try:
                    found = await data.events(ch, day_)
                except DVRIPError:
                    continue
                found_all += [
                    {**as_dict(e), "entry_id": entry_id}
                    for e in found
                    if e.end >= since and (kind is None or kind in e.kinds)
                ]
    found_all.sort(key=lambda e: e["begin"], reverse=True)
    return {"events": found_all[: msg["limit"]]}


@command(
    "play",
    {
        vol.Required("entry_id"): str,
        vol.Required("channel"): int,
        vol.Required("time"): str,
        vol.Optional("speed", default=1): vol.In([1, 2, 4, 6, 12, 24]),
        # the browser can decode H.265 (Safari, Chrome with hardware decoding)
        vol.Optional("hevc", default=False): bool,
    },
)
async def play(svc: Services, msg: dict[str, Any]) -> Any:
    """Start playback at a time; plays to the end of that file."""
    data = _nvr(svc, msg["entry_id"])
    channel = _channel(data, msg["channel"])
    when = datetime.strptime(msg["time"], TIME_FORMAT)
    try:
        rec = await data.recording_at(channel, when)
    except DVRIPError as err:
        raise APIError(str(err)) from err
    if rec is None:
        return None
    start = max(when, rec.begin)
    part = type(rec)(rec.channel, start, rec.end, rec.file_name, rec.size_kb)
    # 1-2x: the browser speeds up; faster: key frames only, made by the server
    speed = msg["speed"] if msg["speed"] >= FAST_SPEED else 1
    transcode = data.transcode_h265 and not msg["hevc"]
    session = await svc.playback.start(data.client, part, transcode, speed)
    return {
        "url": f"{svc.hls_url}/{session.token}/{PLAYLIST}",
        "begin": start.strftime(TIME_FORMAT),
        "end": rec.end.strftime(TIME_FORMAT),
        "kind": rec.kind,
        "speed": speed,
    }


async def thumbnail(svc: Services, entry_id: str, channel: str, stamp: str) -> web.Response:
    try:
        data = _nvr(svc, entry_id)
        ch = _channel(data, int(channel))
        begin = datetime.strptime(stamp.removesuffix(".jpg"), "%Y%m%d%H%M%S")
    except (APIError, ValueError) as err:
        raise web.HTTPNotFound from err
    image = await svc.thumbs.get(data, ch, begin)
    if image is None:
        raise web.HTTPNotFound
    return web.Response(
        body=image,
        content_type="image/jpeg",
        headers={"Cache-Control": "private, max-age=86400"},
    )


@command("nvr", {vol.Required("entry_id"): str}, admin=True)
async def nvr(svc: Services, msg: dict[str, Any]) -> Any:
    """NVR state for the settings page."""
    client = _nvr(svc, msg["entry_id"]).client
    out: dict[str, Any] = {}
    for key, call in (
        ("system", lambda: client.info("SystemInfo")),
        ("storage", lambda: client.info("StorageInfo")),
        ("work", lambda: client.info("WorkState")),
        ("record", lambda: client.config_get("Record")),
        ("motion", lambda: client.config_get("Detect.MotionDetect")),
        ("general", lambda: client.config_get("General.General")),
        ("titles", client.channel_titles),
    ):
        try:
            out[key] = await call()
        except DVRIPError as err:
            out[key] = {"error": str(err)}
    return out


@command(
    "probe",
    {
        vol.Required("entry_id"): str,
        vol.Required("channel"): int,
        vol.Required("time"): str,
        vol.Optional("action", default="DownloadStart"): str,
        vol.Optional("control"): dict,
        vol.Optional("seconds", default=10): int,
    },
    admin=True,
)
async def probe(svc: Services, msg: dict[str, Any]) -> Any:
    """Diagnostics: read a recording for a while and report its real frame timing."""
    data = _nvr(svc, msg["entry_id"])
    when = datetime.strptime(msg["time"], TIME_FORMAT)
    rec = await data.recording_at(_channel(data, msg["channel"]), when)
    if rec is None:
        return None
    part = type(rec)(rec.channel, max(when, rec.begin), rec.end, rec.file_name, rec.size_kb)
    loop = asyncio.get_running_loop()
    t0 = loop.time()
    parser = FrameParser()
    frames = received = 0
    first = last = None
    header_fps = 0
    codec = None
    iframes: list[int] = []
    async with data.client.download(part, action=msg["action"], then=msg.get("control")) as chunks:
        async for chunk in chunks:
            received += len(chunk)
            for f in parser.feed(chunk):
                if f.kind in FRAME_I:
                    s = stamp_seconds(f.stamp)
                    header_fps = f.fps
                    codec = f.codec
                    iframes.append(frames)
                    if first is None:
                        first = (frames, s)
                    last = (frames, s)
                if f.kind in FRAME_I or f.kind == FRAME_P:
                    frames += 1
            if loop.time() - t0 > msg["seconds"]:
                break
    wall = loop.time() - t0
    span = (last[1] - first[1]) if first and last else 0
    return {
        "file": rec.file_name,
        "wall": round(wall, 2),
        "bytes": received,
        "frames": frames,
        "header_fps": header_fps,
        "codec": {2: "h264", 3: "h265"}.get(codec, codec),
        # frames between key frames
        "gop": [b - a for a, b in zip(iframes, iframes[1:])][:12],
        "stamp_span": span,
        "measured_fps": round((last[0] - first[0]) / span, 2) if span else None,
        "speed_vs_wall": round(span / wall, 2) if wall else None,
    }


@command(
    "settings_set",
    {
        vol.Required("entry_id"): str,
        vol.Required("channel"): int,
        vol.Optional("record"): vol.In(["always", "motion", "off"]),
        vol.Optional("motion_enabled"): bool,
        vol.Optional("motion_level"): vol.All(int, vol.Range(min=1, max=6)),
    },
    admin=True,
)
async def settings_set(svc: Services, msg: dict[str, Any]) -> Any:
    """Change one channel's recording mode and motion detection on the NVR."""
    client = _nvr(svc, msg["entry_id"]).client
    index = msg["channel"] - 1
    if not 0 <= index < 64:
        raise APIError("unknown channel")
    try:
        if "record" in msg:
            name = f"Record.[{index}]"
            record = await client.config_get(name)
            if msg["record"] == "off":
                record["RecordMode"] = "ClosedRecord"
            else:
                record["RecordMode"] = "ConfigRecord"
                for day_ in record["Mask"]:
                    day_[0] = RECORD_MASKS[msg["record"]]
                for day_ in record["TimeSection"]:
                    day_[0] = "1 00:00:00-24:00:00"
            await client.config_set(name, record)
        if "motion_enabled" in msg or "motion_level" in msg:
            name = f"Detect.MotionDetect.[{index}]"
            motion = await client.config_get(name)
            if "motion_enabled" in msg:
                motion["Enable"] = msg["motion_enabled"]
            if "motion_level" in msg:
                motion["Level"] = msg["motion_level"]
            await client.config_set(name, motion)
    except DVRIPError as err:
        raise APIError(str(err)) from err
    return None


@command("homekit", admin=True)
async def homekit(svc: Services, msg: dict[str, Any]) -> Any:
    return await svc.homekit.status()


@command(
    "homekit_set",
    {
        vol.Required("key"): str,
        vol.Optional("enabled"): bool,
        vol.Optional("reset"): bool,
        vol.Optional("stream"): vol.In(["main", "sub"]),
        vol.Optional("preload"): bool,
    },
    admin=True,
)
async def homekit_set(svc: Services, msg: dict[str, Any]) -> Any:
    manager = svc.homekit
    if msg["key"] not in manager.cameras:
        raise APIError("unknown camera")
    if msg.get("reset"):
        await manager.reset_pairing(msg["key"])
    if "stream" in msg:
        await manager.set_stream(msg["key"], msg["stream"])
    if "preload" in msg:
        await manager.set_preload(msg["key"], msg["preload"])
    if "enabled" in msg:
        await manager.set_enabled(msg["key"], msg["enabled"])
    return await manager.status()


# registers the NVR configuration commands
from . import nvrconfig  # noqa: E402, F401
