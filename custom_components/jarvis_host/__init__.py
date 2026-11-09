"""Jarvis Host: the Mac that runs Home Assistant, as a device with sensors.

The Mac pushes a JSON report to a webhook every few minutes. Nothing here connects to the Mac.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from aiohttp import web
from homeassistant.components import webhook
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import CONF_MODEL, CONF_WEBHOOK_ID, DOMAIN, MAX_BODY_BYTES, STORAGE_VERSION
from .report import HostReport, ReportError, is_fresh, parse_report

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.BINARY_SENSOR, Platform.SENSOR, Platform.UPDATE]

type JarvisHostConfigEntry = ConfigEntry[JarvisHostData]


class JarvisHostData:
    """The latest report of one Mac, shared by its entities."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.report: HostReport | None = None
        self.received_at: datetime | None = None
        self.signal = f"{DOMAIN}_update_{entry.entry_id}"
        self._store: Store = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}")

    async def async_load(self) -> None:
        """Restore the last report, so values survive a restart of Home Assistant."""
        stored = await self._store.async_load()
        if not stored:
            return
        try:
            report = parse_report(stored["payload"])
            received_at = dt_util.parse_datetime(stored["received_at"])
        except (ReportError, KeyError, TypeError, ValueError) as err:
            _LOGGER.warning("Ignoring the stored report of %s: %s", self.entry.title, err)
            return
        if received_at is not None:
            self.report = report
            self.received_at = received_at

    @property
    def fresh(self) -> bool:
        return self.report is not None and is_fresh(self.received_at, dt_util.utcnow())

    @callback
    def async_update(self, payload: dict[str, Any], report: HostReport) -> None:
        self.report = report
        self.received_at = dt_util.utcnow()
        received_at = self.received_at.isoformat()
        self._store.async_delay_save(lambda: {"received_at": received_at, "payload": payload}, 60)
        self._sync_device(report)
        async_dispatcher_send(self.hass, self.signal)

    @callback
    def async_tick(self, _now: datetime) -> None:
        """Every minute, so entities notice that reports stopped."""
        async_dispatcher_send(self.hass, self.signal)

    def _sync_device(self, report: HostReport) -> None:
        registry = dr.async_get(self.hass)
        device = registry.async_get_device(identifiers={(DOMAIN, self.entry.entry_id)})
        if device is None:
            return
        changes: dict[str, str] = {}
        if report.macos_version and device.sw_version != report.macos_version:
            changes["sw_version"] = report.macos_version
        if (
            not self.entry.data.get(CONF_MODEL)
            and report.hardware_model
            and device.model != report.hardware_model
        ):
            changes["model"] = report.hardware_model
        if changes:
            registry.async_update_device(device.id, **changes)


async def async_setup_entry(hass: HomeAssistant, entry: JarvisHostConfigEntry) -> bool:
    data = JarvisHostData(hass, entry)
    await data.async_load()
    entry.runtime_data = data

    async def handle_webhook(
        hass: HomeAssistant, webhook_id: str, request: web.Request
    ) -> web.Response:
        if request.content_length is not None and request.content_length > MAX_BODY_BYTES:
            return web.Response(status=413)
        try:
            payload = await request.json()
        except ValueError:
            return web.Response(status=400)
        try:
            report = parse_report(payload)
        except ReportError as err:
            _LOGGER.warning("Rejected a report for %s: %s", entry.title, err)
            return web.Response(status=400)
        data.async_update(payload, report)
        return web.Response(status=200)

    webhook_id = entry.data[CONF_WEBHOOK_ID]
    webhook.async_register(
        hass,
        DOMAIN,
        entry.title,
        webhook_id,
        handle_webhook,
        local_only=True,
        allowed_methods=["POST"],
    )
    entry.async_on_unload(lambda: webhook.async_unregister(hass, webhook_id))
    entry.async_on_unload(async_track_time_interval(hass, data.async_tick, timedelta(minutes=1)))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: JarvisHostConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: JarvisHostConfigEntry) -> None:
    await Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}").async_remove()
