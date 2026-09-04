"""Config flow for Cursor Usage."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import CursorApiClient, CursorApiError, CursorAuthError
from .const import CONF_NAME, CONF_SESSION_TOKEN, DEFAULT_NAME, DOMAIN

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_SESSION_TOKEN): str,
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): str,
    }
)


class CursorUsageConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Cursor Usage."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            token = user_input[CONF_SESSION_TOKEN].strip()
            name = user_input.get(CONF_NAME, DEFAULT_NAME).strip() or DEFAULT_NAME

            session = async_get_clientsession(self.hass)
            client = CursorApiClient(session, token)

            try:
                await client.async_get_usage_summary()
            except CursorAuthError:
                errors["base"] = "invalid_auth"
            except CursorApiError:
                errors["base"] = "cannot_connect"
            else:
                # One Cursor account per Home Assistant instance.
                await self.async_set_unique_id(DOMAIN)
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=name,
                    data={
                        CONF_SESSION_TOKEN: token,
                        CONF_NAME: name,
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> config_entries.ConfigFlowResult:
        """Handle reauthentication when the session token expires."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Ask for a new session token during reauth."""
        errors: dict[str, str] = {}
        reauth_entry = self._get_reauth_entry()

        if user_input is not None:
            token = user_input[CONF_SESSION_TOKEN].strip()
            session = async_get_clientsession(self.hass)
            client = CursorApiClient(session, token)

            try:
                await client.async_get_usage_summary()
            except CursorAuthError:
                errors["base"] = "invalid_auth"
            except CursorApiError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_update_reload_and_abort(
                    reauth_entry,
                    data_updates={CONF_SESSION_TOKEN: token},
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_SESSION_TOKEN): str}),
            errors=errors,
        )
