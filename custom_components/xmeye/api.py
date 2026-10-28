"""WebSocket commands and the thumbnail endpoint used by the viewer panel."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from aiohttp import web
import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from . import XMeyeConfigEntry, as_dict, loaded_entries
from .const import DOMAIN
from .dvrip import DVRIPError
from .playback import FAST_SPEED, PLAYLIST

TIME_FORMAT = "%Y-%m-%d %H:%M:%S"


class APIError(HomeAssistantError):
    """Sent to the panel as the error message."""


@callback
def async_setup(hass: HomeAssistant) -> None:
    websocket_api.async_register_command(hass, ws_cameras)
    websocket_api.async_register_command(hass, ws_day)
    websocket_api.async_register_command(hass, ws_events)
    websocket_api.async_register_command(hass, ws_play)
    websocket_api.async_register_command(hass, ws_nvr)
    websocket_api.async_register_command(hass, ws_probe)
    websocket_api.async_register_command(hass, ws_settings_set)
    websocket_api.async_register_command(hass, ws_homekit)
    websocket_api.async_register_command(hass, ws_homekit_set)
    hass.http.register_view(ThumbnailView())


def _entry(hass: HomeAssistant, entry_id: str) -> XMeyeConfigEntry:
    for entry in loaded_entries(hass):
        if entry.entry_id == entry_id:
            return entry
    raise APIError("NVR not loaded")


def _channel(entry: XMeyeConfigEntry, channel: int) -> int:
    if channel - 1 not in entry.runtime_data.channels:
        raise APIError("unknown channel")
    return channel - 1


@websocket_api.websocket_command({vol.Required("type"): "xmeye/cameras"})
@callback
def ws_cameras(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    registry = er.async_get(hass)
    cameras = []
    for entry in loaded_entries(hass):
        data = entry.runtime_data
        for ch, name in data.channels.items():
            uid = f"{data.serial}_{ch + 1}"
            cameras.append(
                {
                    "entry_id": entry.entry_id,
                    "channel": ch + 1,
                    "name": name,
                    "entity_id": registry.async_get_entity_id("camera", DOMAIN, uid),
                    "sub_entity_id": registry.async_get_entity_id(
                        "camera", DOMAIN, f"{uid}_sub"
                    ),
                }
            )
    connection.send_result(msg["id"], {"cameras": cameras})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "xmeye/day",
        vol.Required("entry_id"): str,
        vol.Required("channel"): int,
        vol.Optional("date"): str,
    }
)
@websocket_api.async_response
async def ws_day(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Recordings and motion events of one camera on one day."""
    entry = _entry(hass, msg["entry_id"])
    data = entry.runtime_data
    channel = _channel(entry, msg["channel"])
    day = date.fromisoformat(msg["date"]) if msg.get("date") else dt_util.now().date()
    try:
        recs = await data.recordings(channel, day)
        events = await data.events(channel, day)
        days = await data.days()
    except DVRIPError as err:
        raise APIError(str(err)) from err
    connection.send_result(
        msg["id"],
        {
            "date": day.isoformat(),
            "days": [d.isoformat() for d in days],
            "recordings": [as_dict(r) for r in recs],
            "events": [as_dict(e) for e in reversed(events)],
        },
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): "xmeye/events",
        vol.Optional("hours", default=24): vol.All(int, vol.Range(min=1, max=72)),
        vol.Optional("limit", default=40): vol.All(int, vol.Range(min=1, max=500)),
    }
)
@websocket_api.async_response
async def ws_events(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Recent motion events of all cameras, newest first."""
    now = dt_util.now().replace(tzinfo=None)
    since = now - timedelta(hours=msg["hours"])
    days = sorted({since.date(), now.date()})
    events = []
    for entry in loaded_entries(hass):
        data = entry.runtime_data
        for ch in data.channels:
            for day in days:
                try:
                    found = await data.events(ch, day)
                except DVRIPError:
                    continue
                events += [
                    {**as_dict(e), "entry_id": entry.entry_id}
                    for e in found
                    if e.end >= since
                ]
    events.sort(key=lambda e: e["begin"], reverse=True)
    connection.send_result(msg["id"], {"events": events[: msg["limit"]]})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "xmeye/play",
        vol.Required("entry_id"): str,
        vol.Required("channel"): int,
        vol.Required("time"): str,
        vol.Optional("speed", default=1): vol.In([1, 2, 4, 6, 12, 24]),
        # the browser can decode H.265 (Safari, Chrome with hardware decoding)
        vol.Optional("hevc", default=False): bool,
    }
)
@websocket_api.async_response
async def ws_play(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Start playback at a time; plays to the end of that file."""
    entry = _entry(hass, msg["entry_id"])
    data = entry.runtime_data
    channel = _channel(entry, msg["channel"])
    when = datetime.strptime(msg["time"], TIME_FORMAT)
    try:
        rec = await data.recording_at(channel, when)
    except DVRIPError as err:
        raise APIError(str(err)) from err
    if rec is None:
        connection.send_result(msg["id"], None)
        return
    start = max(when, rec.begin)
    part = type(rec)(rec.channel, start, rec.end, rec.file_name, rec.size_kb)
    # 1-2x: the browser speeds up; faster: key frames only, made by the server
    speed = msg["speed"] if msg["speed"] >= FAST_SPEED else 1
    transcode = data.transcode_h265 and not msg["hevc"]
    session = await hass.data[DOMAIN]["playback"].start(
        data.client, part, transcode, speed
    )
    connection.send_result(
        msg["id"],
        {
            "url": f"/api/xmeye/hls/{session.token}/{PLAYLIST}",
            "begin": start.strftime(TIME_FORMAT),
            "end": rec.end.strftime(TIME_FORMAT),
            "kind": rec.kind,
            "speed": speed,
        },
    )


class ThumbnailView(HomeAssistantView):
    url = "/api/xmeye/thumb/{entry_id}/{channel}/{stamp}"
    name = "api:xmeye:thumb"
    requires_auth = True

    async def get(
        self, request: web.Request, entry_id: str, channel: str, stamp: str
    ) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        try:
            entry = _entry(hass, entry_id)
            ch = _channel(entry, int(channel))
            begin = datetime.strptime(stamp.removesuffix(".jpg"), "%Y%m%d%H%M%S")
        except (APIError, ValueError) as err:
            raise web.HTTPNotFound from err
        image = await hass.data[DOMAIN]["thumbs"].get(entry.runtime_data, ch, begin)
        if image is None:
            raise web.HTTPNotFound
        return web.Response(
            body=image,
            content_type="image/jpeg",
            headers={"Cache-Control": "private, max-age=86400"},
        )


@websocket_api.require_admin
@websocket_api.websocket_command(
    {vol.Required("type"): "xmeye/nvr", vol.Required("entry_id"): str}
)
@websocket_api.async_response
async def ws_nvr(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """NVR state for the settings page."""
    data = _entry(hass, msg["entry_id"]).runtime_data
    client = data.client
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
    connection.send_result(msg["id"], out)


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): "xmeye/probe",
        vol.Required("entry_id"): str,
        vol.Required("channel"): int,
        vol.Required("time"): str,
        vol.Optional("action", default="DownloadStart"): str,
        vol.Optional("control"): dict,
        vol.Optional("seconds", default=10): int,
    }
)
@websocket_api.async_response
async def ws_probe(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Diagnostics: read a recording for a while and report its real frame timing."""
    import asyncio  # noqa: PLC0415

    from .dvrip import FRAME_I, FRAME_P, FrameParser, stamp_seconds  # noqa: PLC0415

    entry = _entry(hass, msg["entry_id"])
    data = entry.runtime_data
    when = datetime.strptime(msg["time"], TIME_FORMAT)
    rec = await data.recording_at(_channel(entry, msg["channel"]), when)
    if rec is None:
        connection.send_result(msg["id"], None)
        return
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
    connection.send_result(
        msg["id"],
        {
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
        },
    )



RECORD_MASKS = {"always": "0x00000007", "motion": "0x00000006"}


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): "xmeye/settings_set",
        vol.Required("entry_id"): str,
        vol.Required("channel"): int,
        vol.Optional("record"): vol.In(["always", "motion", "off"]),
        vol.Optional("motion_enabled"): bool,
        vol.Optional("motion_level"): vol.All(int, vol.Range(min=1, max=6)),
    }
)
@websocket_api.async_response
async def ws_settings_set(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Change one channel's recording mode and motion detection on the NVR."""
    entry = _entry(hass, msg["entry_id"])
    client = entry.runtime_data.client
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
                for day in record["Mask"]:
                    day[0] = RECORD_MASKS[msg["record"]]
                for day in record["TimeSection"]:
                    day[0] = "1 00:00:00-24:00:00"
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
    connection.send_result(msg["id"], None)


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required("type"): "xmeye/homekit"})
@websocket_api.async_response
async def ws_homekit(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    connection.send_result(msg["id"], await hass.data[DOMAIN]["homekit"].status())


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): "xmeye/homekit_set",
        vol.Required("key"): str,
        vol.Optional("enabled"): bool,
        vol.Optional("reset"): bool,
        vol.Optional("stream"): vol.In(["main", "sub"]),
        vol.Optional("preload"): bool,
    }
)
@websocket_api.async_response
async def ws_homekit_set(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    manager = hass.data[DOMAIN]["homekit"]
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
    connection.send_result(msg["id"], await manager.status())

