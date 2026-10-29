"""The panel's commands on HA's WebSocket API, plus the thumbnail and HLS endpoints."""

from __future__ import annotations

from typing import Any

from aiohttp import web
import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from . import loaded_entries
from .commands import COMMANDS, APIError, Command, Services, thumbnail
from .const import DOMAIN
from .playback import hls_response


@callback
def async_setup(hass: HomeAssistant) -> None:
    for cmd in COMMANDS:
        websocket_api.async_register_command(hass, _ws_handler(cmd))
    hass.http.register_view(ThumbnailView())
    hass.http.register_view(PlaybackView())


def services(hass: HomeAssistant) -> Services:
    registry = er.async_get(hass)
    shared = hass.data[DOMAIN]
    return Services(
        nvrs=lambda: {e.entry_id: e.runtime_data for e in loaded_entries(hass)},
        playback=shared["playback"],
        thumbs=shared["thumbs"],
        homekit=shared["homekit"],
        entity_id=lambda uid: registry.async_get_entity_id("camera", DOMAIN, uid),
        now=lambda: dt_util.now().replace(tzinfo=None),
    )


def _ws_handler(cmd: Command):
    @websocket_api.websocket_command({vol.Required("type"): f"xmeye/{cmd.name}", **cmd.schema})
    @websocket_api.async_response
    async def handle(
        hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
    ) -> None:
        try:
            result = await cmd.handler(services(hass), msg)
        except APIError as err:
            connection.send_error(msg["id"], "xmeye_error", str(err))
            return
        connection.send_result(msg["id"], result)

    return websocket_api.require_admin(handle) if cmd.admin else handle


class ThumbnailView(HomeAssistantView):
    url = "/api/xmeye/thumb/{entry_id}/{channel}/{stamp}"
    name = "api:xmeye:thumb"
    requires_auth = True

    async def get(
        self, request: web.Request, entry_id: str, channel: str, stamp: str
    ) -> web.Response:
        return await thumbnail(services(request.app["hass"]), entry_id, channel, stamp)


class PlaybackView(HomeAssistantView):
    """The random session token is the authorization, see hls_response."""

    url = "/api/xmeye/hls/{token}/{name}"
    name = "api:xmeye:hls"
    requires_auth = False

    async def get(self, request: web.Request, token: str, name: str) -> web.StreamResponse:
        hass: HomeAssistant = request.app["hass"]
        return await hls_response(hass.data[DOMAIN]["playback"], token, name)
