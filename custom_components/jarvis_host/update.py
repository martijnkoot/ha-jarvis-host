"""The macOS update entity of a Jarvis Host."""

from __future__ import annotations

from homeassistant.components.update import UpdateEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import JarvisHostConfigEntry, JarvisHostData
from .entity import JarvisHostEntity
from .report import latest_macos_version


async def async_setup_entry(
    hass: HomeAssistant,
    entry: JarvisHostConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([MacOSUpdate(entry.runtime_data)])


class MacOSUpdate(JarvisHostEntity, UpdateEntity):
    """Shows a pending macOS update next to Home Assistant's own updates. It only reports:
    installing is done on the Mac itself."""

    _attr_title = "macOS"

    def __init__(self, data: JarvisHostData) -> None:
        super().__init__(data, "macos")

    @property
    def installed_version(self) -> str | None:
        report = self._data.report
        return report.macos_version or None if report else None

    @property
    def latest_version(self) -> str | None:
        report = self._data.report
        if report is None:
            return None
        # With only non-macOS updates pending (Command Line Tools, Safari) there is no newer
        # macOS version; they still show in the summary and in the pending updates sensor.
        return latest_macos_version(report.updates) or self.installed_version

    @property
    def release_summary(self) -> str | None:
        report = self._data.report
        if report is None or not report.updates:
            return None
        return ", ".join(report.updates)[:255]
