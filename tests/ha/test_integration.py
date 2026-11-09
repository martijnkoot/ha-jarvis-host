"""The integration inside a real Home Assistant: setup flow, webhook, device, entities."""

import json
from datetime import timedelta
from pathlib import Path

from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.jarvis_host.const import CONF_MODEL, CONF_WEBHOOK_ID, DOMAIN

SAMPLE = {
    "boot_time": "2026-10-27T16:24:21Z",
    "cpu_cores": 14,
    "cpu_percent": 3.7,
    "disk_free_gb": 531.1,
    "disk_free_percent": 57.3,
    "filevault_on": True,
    "hardware_model": "Mac16,10",
    "hostname": "Mac-mini",
    "load_15m": 2.27,
    "load_1m": 2.88,
    "load_5m": 2.25,
    "macos_version": "27.2",
    "memory_used_percent": 42,
    "reported_at": "2026-11-09T20:53:53Z",
    "updates": ["macOS 27.2.1-26B131"],
    "updates_checked_epoch": 1794257893,
    "updates_count": 1,
    "vm_running": True,
}
WEBHOOK_ID = "test-webhook-id"
URL = f"/api/webhook/{WEBHOOK_ID}"


async def _setup(hass: HomeAssistant) -> MockConfigEntry:
    assert await async_setup_component(hass, "http", {})
    entry = MockConfigEntry(
        domain=DOMAIN, title="Mac mini", data={CONF_WEBHOOK_ID: WEBHOOK_ID, CONF_MODEL: ""}
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_unavailable_until_the_first_report(hass: HomeAssistant) -> None:
    await _setup(hass)
    assert hass.states.get("sensor.mac_mini_cpu").state == "unavailable"
    assert hass.states.get("binary_sensor.mac_mini_reporting").state == "off"
    assert hass.states.get("sensor.mac_mini_last_report").state == "unknown"


async def test_report_fills_device_and_entities(hass: HomeAssistant, hass_client_no_auth) -> None:
    entry = await _setup(hass)
    client = await hass_client_no_auth()
    response = await client.post(URL, json=SAMPLE)
    assert response.status == 200
    await hass.async_block_till_done()

    assert hass.states.get("sensor.mac_mini_cpu").state == "3.7"
    assert hass.states.get("sensor.mac_mini_cpu").attributes["cores"] == 14
    assert hass.states.get("sensor.mac_mini_load").state == "2.88"
    assert hass.states.get("sensor.mac_mini_load").attributes["load_15m"] == 2.27
    assert hass.states.get("sensor.mac_mini_memory_used").state == "42.0"
    assert hass.states.get("sensor.mac_mini_pending_updates").state == "1"
    assert hass.states.get("sensor.mac_mini_pending_updates").attributes["updates"] == [
        "macOS 27.2.1-26B131"
    ]
    assert hass.states.get("binary_sensor.mac_mini_reporting").state == "on"
    assert hass.states.get("binary_sensor.mac_mini_home_assistant_vm").state == "on"
    assert hass.states.get("binary_sensor.mac_mini_filevault").state == "on"
    update = hass.states.get("update.mac_mini_macos")
    assert update.state == "on"
    assert update.attributes["installed_version"] == "27.2"
    assert update.attributes["latest_version"] == "27.2.1"

    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, entry.entry_id)})
    assert device.name == "Mac mini"
    assert device.manufacturer == "Apple"
    assert device.model == "Mac16,10"
    assert device.sw_version == "27.2"
    entities = [e for e in hass.states.async_all() if e.entity_id.startswith(("sensor.mac_mini", "binary_sensor.mac_mini", "update.mac_mini"))]
    assert len(entities) == 12


async def test_bad_reports_are_rejected(hass: HomeAssistant, hass_client_no_auth) -> None:
    await _setup(hass)
    client = await hass_client_no_auth()
    assert (await client.post(URL, json={"cpu_percent": 5})).status == 400
    assert (await client.post(URL, json={**SAMPLE, "cpu_percent": 500})).status == 400
    assert (await client.post(URL, data="not json", headers={"Content-Type": "application/json"})).status == 400
    assert hass.states.get("sensor.mac_mini_cpu").state == "unavailable"


async def test_goes_unavailable_when_reports_stop(
    hass: HomeAssistant, hass_client_no_auth, freezer
) -> None:
    await _setup(hass)
    client = await hass_client_no_auth()
    await client.post(URL, json=SAMPLE)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.mac_mini_cpu").state == "3.7"

    freezer.tick(timedelta(minutes=16))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.mac_mini_cpu").state == "unavailable"
    assert hass.states.get("update.mac_mini_macos").state == "unavailable"
    assert hass.states.get("binary_sensor.mac_mini_reporting").state == "off"
    assert hass.states.get("sensor.mac_mini_last_report").state not in ("unknown", "unavailable")

    await client.post(URL, json=SAMPLE)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.mac_mini_cpu").state == "3.7"
    assert hass.states.get("binary_sensor.mac_mini_reporting").state == "on"


async def test_values_survive_a_reload(hass: HomeAssistant, hass_client_no_auth, freezer) -> None:
    entry = await _setup(hass)
    client = await hass_client_no_auth()
    await client.post(URL, json=SAMPLE)
    await hass.async_block_till_done()

    freezer.tick(timedelta(seconds=61))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.mac_mini_cpu").state == "3.7"
    assert hass.states.get("binary_sensor.mac_mini_reporting").state == "on"


async def test_webhook_is_removed_on_unload(hass: HomeAssistant, hass_client_no_auth) -> None:
    entry = await _setup(hass)
    client = await hass_client_no_auth()
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    # An unknown webhook id answers 200 and does nothing; the state must not change.
    await client.post(URL, json=SAMPLE)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.mac_mini_cpu").state == "unavailable"


async def test_config_flow_shows_the_webhook_url(hass: HomeAssistant) -> None:
    assert await async_setup_component(hass, "http", {})
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"name": "Mac mini", "model": "Mac mini (M4)"}
    )
    assert result["step_id"] == "url"
    assert "/api/webhook/" in result["description_placeholders"]["url"]

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] == "create_entry"
    assert result["title"] == "Mac mini"
    assert result["data"][CONF_MODEL] == "Mac mini (M4)"
    assert len(result["data"][CONF_WEBHOOK_ID]) > 20


async def test_options_flow_shows_the_url_again(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["step_id"] == "init"
    assert WEBHOOK_ID in result["description_placeholders"]["url"]


def test_translations_cover_the_same_keys() -> None:
    base = Path(__file__).resolve().parents[2] / "custom_components" / DOMAIN

    def keys(node, prefix=""):
        for key, value in node.items():
            if isinstance(value, dict):
                yield from keys(value, f"{prefix}{key}.")
            else:
                yield f"{prefix}{key}"

    english = set(keys(json.loads((base / "translations" / "en.json").read_text())))
    for name in ("nl.json",):
        assert set(keys(json.loads((base / "translations" / name).read_text()))) == english
    assert set(keys(json.loads((base / "strings.json").read_text()))) == english
