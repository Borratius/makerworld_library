"""UI configuration for MakerWorld Library."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import MakerWorldApiClient
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_COLLECTION_ID,
    CONF_COLLECTION_SLUG,
    CONF_PRINTER_DEVICE_ID,
    CONF_SCAN_INTERVAL,
    DEFAULT_COLLECTION_ID,
    DEFAULT_COLLECTION_NAME,
    DEFAULT_COLLECTION_SLUG,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)
from .exceptions import MakerWorldAuthenticationError, MakerWorldError


class MakerWorldLibraryConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Configure one MakerWorld collection."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            error = await self._async_validate(user_input)
            if error is None:
                collection_id = str(user_input[CONF_COLLECTION_ID]).strip()
                await self.async_set_unique_id(collection_id)
                self._abort_if_unique_id_configured()
                data = {
                    CONF_COLLECTION_ID: collection_id,
                    CONF_COLLECTION_SLUG: str(user_input[CONF_COLLECTION_SLUG]).strip(),
                    CONF_PRINTER_DEVICE_ID: user_input[CONF_PRINTER_DEVICE_ID],
                }
                token = str(user_input.get(CONF_ACCESS_TOKEN, "")).strip()
                if token:
                    data[CONF_ACCESS_TOKEN] = token
                return self.async_create_entry(title=DEFAULT_COLLECTION_NAME, data=data)
            errors["base"] = error

        return self.async_show_form(
            step_id="user",
            data_schema=_collection_schema(user_input),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]):
        self._reauth_entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            candidate = dict(self._reauth_entry.data)
            token = str(user_input.get(CONF_ACCESS_TOKEN, "")).strip()
            if token:
                candidate[CONF_ACCESS_TOKEN] = token
            else:
                candidate.pop(CONF_ACCESS_TOKEN, None)
            error = await self._async_validate(candidate)
            if error is None:
                self.hass.config_entries.async_update_entry(self._reauth_entry, data=candidate)
                await self.hass.config_entries.async_reload(self._reauth_entry.entry_id)
                return self.async_abort(reason="reauth_successful")
            errors["base"] = error

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_ACCESS_TOKEN, default=""): selector.TextSelector(
                        selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                    )
                }
            ),
            errors=errors,
        )

    async def _async_validate(self, values: dict[str, Any]) -> str | None:
        collection_id = str(values[CONF_COLLECTION_ID]).strip()
        if not collection_id.isdecimal():
            return "invalid_collection_id"

        client = MakerWorldApiClient(
            async_get_clientsession(self.hass), values.get(CONF_ACCESS_TOKEN)
        )
        try:
            await client.async_validate_collection(
                collection_id,
                str(values[CONF_COLLECTION_SLUG]).strip(),
            )
        except MakerWorldAuthenticationError:
            return "invalid_auth"
        except MakerWorldError:
            return "cannot_connect"
        return None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        return MakerWorldLibraryOptionsFlow(config_entry)


class MakerWorldLibraryOptionsFlow(config_entries.OptionsFlow):
    """Change polling without re-entering credentials."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        current = self._entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SCAN_INTERVAL, default=current): vol.All(
                        vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL)
                    )
                }
            ),
        )


def _collection_schema(values: dict[str, Any] | None) -> vol.Schema:
    values = values or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_COLLECTION_ID, default=values.get(CONF_COLLECTION_ID, DEFAULT_COLLECTION_ID)
            ): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
            ),
            vol.Required(
                CONF_COLLECTION_SLUG,
                default=values.get(CONF_COLLECTION_SLUG, DEFAULT_COLLECTION_SLUG),
            ): str,
            vol.Required(CONF_PRINTER_DEVICE_ID): selector.DeviceSelector(
                selector.DeviceSelectorConfig(integration="bambu_lab")
            ),
            vol.Optional(CONF_ACCESS_TOKEN, default=""): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
            ),
        }
    )
