"""Live cameras: one per NVR channel, plus a hidden sub-stream camera."""

from __future__ import annotations

import asyncio
import contextlib

from homeassistant.components.camera import Camera, CameraEntityFeature
from homeassistant.components.ffmpeg import async_get_image
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import XMeyeConfigEntry, XMeyeData
from .const import DOMAIN
from .dvrip import DVRIPError

SNAPSHOT_MAX_AGE = 10  # s
SNAPSHOT_KEYFRAME = 1.5  # s to wait for a snapshot before asking for a key frame


async def async_setup_entry(
    hass: HomeAssistant,
    entry: XMeyeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    data = entry.runtime_data
    async_add_entities(
        XMeyeCamera(data, channel, name, sub)
        for channel, name in data.channels.items()
        for sub in (False, True)
    )


def device_info(data: XMeyeData, channel: int) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, f"{data.serial}_{channel + 1}")},
        name=data.channels[channel],
        manufacturer="Xiongmai",
        model=f"{data.model} channel {channel + 1}",
    )


class XMeyeCamera(Camera):
    _attr_has_entity_name = True
    _attr_supported_features = CameraEntityFeature.STREAM

    def __init__(self, data: XMeyeData, channel: int, name: str, sub: bool) -> None:
        super().__init__()
        self._data = data
        self._channel = channel
        self._sub = sub
        self._attr_unique_id = f"{data.serial}_{channel + 1}{'_sub' if sub else ''}"
        self._attr_name = "Sub-stream" if sub else None
        self._attr_entity_registry_visible_default = not sub
        self._attr_device_info = device_info(data, channel)
        self._attr_extra_state_attributes = {
            "xmeye_entry_id": data.entry_id,
            "xmeye_channel": channel + 1,
            "xmeye_sub_stream": sub,
        }
        self._image: bytes | None = None
        self._image_time = 0.0
        self._image_lock = asyncio.Lock()

    async def stream_source(self) -> str:
        return self._data.rtsp_url(self._channel, self._sub)

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        async with self._image_lock:
            now = asyncio.get_running_loop().time()
            if self._image and now - self._image_time < SNAPSHOT_MAX_AGE:
                return self._image
            image = await self._snapshot(width, height)
            if image:
                self._image, self._image_time = image, now
            return image or self._image

    async def _snapshot(self, width: int | None, height: int | None) -> bytes | None:
        """One picture of the sub stream, straight from the NVR."""
        task = self.hass.async_create_task(
            async_get_image(
                self.hass,
                self._data.rtsp_url(self._channel, sub=True),
                extra_cmd="-rtsp_transport tcp",
                width=width,
                height=height,
            )
        )
        try:
            done, _ = await asyncio.wait({task}, timeout=SNAPSHOT_KEYFRAME)
            if not done:
                # somebody watches the stream, so it did not start with a key frame
                with contextlib.suppress(DVRIPError, OSError):
                    await self._data.request_keyframe(self._channel, True)
            return await task
        finally:
            task.cancel()
