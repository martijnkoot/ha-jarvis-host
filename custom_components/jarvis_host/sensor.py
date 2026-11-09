"""Sensors of a Jarvis Host."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfInformation
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import JarvisHostConfigEntry, JarvisHostData
from .entity import JarvisHostEntity
from .report import HostReport


@dataclass(frozen=True, kw_only=True)
class JarvisHostSensorDescription(SensorEntityDescription):
    value_fn: Callable[[JarvisHostData], Any]
    attrs_fn: Callable[[HostReport], dict[str, Any]] | None = None
    always_available: bool = False


def _from_report(getter: Callable[[HostReport], Any]) -> Callable[[JarvisHostData], Any]:
    return lambda data: getter(data.report) if data.report else None


SENSORS: tuple[JarvisHostSensorDescription, ...] = (
    JarvisHostSensorDescription(
        key="cpu",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=_from_report(lambda r: r.cpu_percent),
        attrs_fn=lambda r: {"cores": r.cpu_cores},
    ),
    JarvisHostSensorDescription(
        key="load",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=_from_report(lambda r: r.load_1m),
        attrs_fn=lambda r: {"load_5m": r.load_5m, "load_15m": r.load_15m},
    ),
    JarvisHostSensorDescription(
        key="memory_used",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=_from_report(lambda r: r.memory_used_percent),
    ),
    JarvisHostSensorDescription(
        key="disk_free",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.GIGABYTES,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=_from_report(lambda r: r.disk_free_gb),
    ),
    JarvisHostSensorDescription(
        key="disk_free_percent",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=_from_report(lambda r: r.disk_free_percent),
    ),
    JarvisHostSensorDescription(
        key="pending_updates",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_from_report(lambda r: r.updates_count),
        attrs_fn=lambda r: {"updates": list(r.updates), "checked": r.updates_checked},
    ),
    JarvisHostSensorDescription(
        key="last_boot",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_from_report(lambda r: r.boot_time),
    ),
    JarvisHostSensorDescription(
        key="last_report",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        always_available=True,
        value_fn=lambda data: data.received_at,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: JarvisHostConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities(JarvisHostSensor(entry.runtime_data, d) for d in SENSORS)


class JarvisHostSensor(JarvisHostEntity, SensorEntity):
    entity_description: JarvisHostSensorDescription

    def __init__(self, data: JarvisHostData, description: JarvisHostSensorDescription) -> None:
        super().__init__(data, description.key)
        self.entity_description = description
        self._always_available = description.always_available

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self._data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        attrs_fn = self.entity_description.attrs_fn
        if attrs_fn is None or self._data.report is None:
            return None
        return attrs_fn(self._data.report)
