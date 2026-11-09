"""Config flow for Jarvis Host: name the Mac, then show the webhook URL it has to post to."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components import webhook
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.network import NoURLAvailableError, get_url

from .const import CONF_MODEL, CONF_WEBHOOK_ID, DOMAIN


def webhook_url(hass: HomeAssistant, webhook_id: str) -> str:
    """The address the Mac posts to. Local only, so the internal address is the right one."""
    try:
        base = get_url(hass, allow_external=False, allow_cloud=False, prefer_external=False)
    except NoURLAvailableError:
        base = "http://<home-assistant-address>"
    return f"{base}{webhook.async_generate_path(webhook_id)}"


class JarvisHostConfigFlow(ConfigFlow, domain=DOMAIN):
    """Add one Mac. Add the integration again for a second Mac."""

    VERSION = 1

    def __init__(self) -> None:
        self._name = ""
        self._model = ""
        self._webhook_id = ""

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return JarvisHostOptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._name = user_input[CONF_NAME].strip()
            self._model = (user_input.get(CONF_MODEL) or "").strip()
            self._webhook_id = webhook.async_generate_id()
            await self.async_set_unique_id(self._webhook_id)
            self._abort_if_unique_id_configured()
            return await self.async_step_url()

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default="Mac mini"): vol.All(str, vol.Length(min=1)),
                vol.Optional(CONF_MODEL): str,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)

    async def async_step_url(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(
                title=self._name,
                data={CONF_WEBHOOK_ID: self._webhook_id, CONF_MODEL: self._model},
            )
        return self.async_show_form(
            step_id="url",
            description_placeholders={"url": webhook_url(self.hass, self._webhook_id)},
        )


class JarvisHostOptionsFlow(OptionsFlow):
    """Shows the webhook URL again; nothing to configure."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data={})
        return self.async_show_form(
            step_id="init",
            description_placeholders={
                "url": webhook_url(self.hass, self.config_entry.data[CONF_WEBHOOK_ID])
            },
        )
