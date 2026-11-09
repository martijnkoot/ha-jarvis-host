"""Binary sensors of a Jarvis Host."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import JarvisHostConfigEntry, JarvisHostData
from .entity import JarvisHostEntity


@dataclass(frozen=True, kw_only=True)
class JarvisHostBinarySensorDescription(BinarySensorEntityDescription):
    value_fn: Callable[[JarvisHostData], bool | None]
    always_available: bool = False


BINARY_SENSORS: tuple[JarvisHostBinarySensorDescription, ...] = (
    JarvisHostBinarySensorDescription(
        key="reporting",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        always_available=True,
        value_fn=lambda data: data.fresh,
    ),
    JarvisHostBinarySensorDescription(
        key="vm_running",
        device_class=BinarySensorDeviceClass.RUNNING,
        value_fn=lambda data: data.report.vm_running if data.report else None,
    ),
    # No device class: FileVault should be off on a Mac that has to start without anyone logging
    # in, and on elsewhere, so on is neither good nor bad.
    JarvisHostBinarySensorDescription(
        key="filevault",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.report.filevault_on if data.report else None,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: JarvisHostConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities(JarvisHostBinarySensor(entry.runtime_data, d) for d in BINARY_SENSORS)


class JarvisHostBinarySensor(JarvisHostEntity, BinarySensorEntity):
    entity_description: JarvisHostBinarySensorDescription

    def __init__(
        self, data: JarvisHostData, description: JarvisHostBinarySensorDescription
    ) -> None:
        super().__init__(data, description.key)
        self.entity_description = description
        self._always_available = description.always_available

    @property
    def is_on(self) -> bool | None:
        return self.entity_description.value_fn(self._data)
