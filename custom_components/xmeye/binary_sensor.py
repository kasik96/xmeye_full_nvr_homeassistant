"""Motion sensors from the NVR's live alarm stream."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import XMeyeConfigEntry, XMeyeData
from .camera import device_info


async def async_setup_entry(
    hass: HomeAssistant,
    entry: XMeyeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    data = entry.runtime_data
    async_add_entities(
        XMeyeMotion(data, channel, kind)
        for channel in data.channels
        for kind in ("motion", "person")
    )


class XMeyeMotion(BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, data: XMeyeData, channel: int, kind: str) -> None:
        self._data = data
        self._channel = channel
        self._kind = kind
        self._attr_unique_id = f"{data.serial}_{channel + 1}_{kind}"
        self._attr_translation_key = kind
        self._attr_device_class = (
            BinarySensorDeviceClass.MOTION
            if kind == "motion"
            else BinarySensorDeviceClass.OCCUPANCY
        )
        # person detection only works with cameras that report it to the NVR
        self._attr_entity_registry_enabled_default = kind == "motion"
        self._attr_device_info = device_info(data, channel)

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self._data.alarms.async_add_listener(self.async_write_ha_state))

    @property
    def available(self) -> bool:
        return self._data.alarms.connected

    @property
    def is_on(self) -> bool:
        return self._data.alarms.is_on(self._channel, self._kind)
