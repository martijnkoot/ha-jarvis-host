"""Base entity for Jarvis Host."""

from __future__ import annotations

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from . import JarvisHostData
from .const import CONF_MODEL, DOMAIN


class JarvisHostEntity(Entity):
    """An entity that follows the reports of one Mac."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    # The "reporting" and "last report" entities must stay visible when reports stop.
    _always_available = False

    def __init__(self, data: JarvisHostData, key: str) -> None:
        self._data = data
        self._attr_unique_id = f"{data.entry.entry_id}_{key}"
        self._attr_translation_key = key

    @property
    def device_info(self) -> DeviceInfo:
        report = self._data.report
        entry = self._data.entry
        return DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Apple",
            model=entry.data.get(CONF_MODEL) or (report.hardware_model if report else None) or "Mac",
            sw_version=report.macos_version if report and report.macos_version else None,
        )

    @property
    def available(self) -> bool:
        return self._always_available or self._data.fresh

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(self.hass, self._data.signal, self._handle_update)
        )

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()
