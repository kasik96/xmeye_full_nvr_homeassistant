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
from .playback import PLAYLIST

TIME_FORMAT = "%Y-%m-%d %H:%M:%S"


class APIError(HomeAssistantError):
    """Sent to the panel as the error message."""


@callback
def async_setup(hass: HomeAssistant) -> None:
    websocket_api.async_register_command(hass, ws_cameras)
    websocket_api.async_register_command(hass, ws_day)
    websocket_api.async_register_command(hass, ws_events)
    websocket_api.async_register_command(hass, ws_play)
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
    session = await hass.data[DOMAIN]["playback"].start(
        data.client, part, data.transcode_h265
    )
    connection.send_result(
        msg["id"],
        {
            "url": f"/api/xmeye/hls/{session.token}/{PLAYLIST}",
            "begin": start.strftime(TIME_FORMAT),
            "end": rec.end.strftime(TIME_FORMAT),
            "kind": rec.kind,
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
