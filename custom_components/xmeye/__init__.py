"""XMeye / Xiongmai NVR: live cameras, recordings on the NVR and a viewer panel."""

from __future__ import annotations

from pathlib import Path

from homeassistant.components.ffmpeg import get_ffmpeg_manager
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_USERNAME,
    EVENT_HOMEASSISTANT_STOP,
    Platform,
)
from homeassistant.core import Event, HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import dt as dt_util

from .alarm import AlarmListener
from .const import (
    CONF_NAMES,
    CONF_RTSP_PORT,
    CONF_TRANSCODE_H265,
    DEFAULT_RTSP_PORT,
    DEFAULT_TRANSCODE_H265,
    DOMAIN,
)
from .dvrip import DVRIPAuthError, DVRIPClient, DVRIPError
from .go2rtc import Go2rtc
from .homekit import HomeKitManager
from .nvr import XMeyeData, nvr_channels, serial_of, visible_channels
from .playback import PlaybackManager
from .thumbnails import ThumbnailCache

PLATFORMS = [Platform.BINARY_SENSOR, Platform.CAMERA]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


type XMeyeConfigEntry = ConfigEntry[XMeyeData]


def _now():
    return dt_util.now().replace(tzinfo=None)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    ffmpeg = get_ffmpeg_manager(hass).binary
    manager = PlaybackManager(ffmpeg)
    await manager.async_setup()
    homekit = HomeKitManager(
        ffmpeg,
        Store(hass, 1, "xmeye.homekit"),
        Path(hass.config.path(".storage", "xmeye_homekit_go2rtc.yaml")),
        Path(hass.config.path(".storage")),
        async_get_clientsession(hass),
    )
    await homekit.async_setup()
    hass.data[DOMAIN] = {
        "playback": manager,
        "thumbs": ThumbnailCache(ffmpeg),
        "homekit": homekit,
    }

    async def _on_stop(_event: Event) -> None:
        await manager.close()
        await homekit.async_stop()

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _on_stop)

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

    all_channels = nvr_channels(titles, status)
    channels = visible_channels(all_channels, entry.options.get(CONF_NAMES, {}))

    data = entry.runtime_data = XMeyeData(
        entry_id=entry.entry_id,
        client=client,
        serial=serial_of(info, entry.entry_id),
        model=str(info.get("HardWare") or "NVR"),
        host=entry.data[CONF_HOST],
        rtsp_port=entry.data.get(CONF_RTSP_PORT, DEFAULT_RTSP_PORT),
        username=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
        channels=channels,
        nvr_channels=all_channels,
        transcode_h265=entry.options.get(CONF_TRANSCODE_H265, DEFAULT_TRANSCODE_H265),
        now=_now,
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

    data.alarms = AlarmListener(client, Store(hass, 1, f"xmeye.events.{entry.entry_id}"))
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
