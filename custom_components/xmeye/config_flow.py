"""Config flow for XMeye NVR."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    BooleanSelector,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    CONF_NAMES,
    CONF_RTSP_PORT,
    CONF_TRANSCODE_H265,
    DEFAULT_PORT,
    DEFAULT_RTSP_PORT,
    DEFAULT_TRANSCODE_H265,
    DOMAIN,
)
from .dvrip import DVRIPAuthError, DVRIPClient, DVRIPError

PASSWORD = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))


async def _validate(data: Mapping[str, Any]) -> tuple[dict[str, Any] | None, dict[str, str]]:
    client = DVRIPClient(
        data[CONF_HOST], data[CONF_PORT], data[CONF_USERNAME], data[CONF_PASSWORD]
    )
    try:
        return await client.system_info(), {}
    except DVRIPAuthError:
        return None, {"base": "invalid_auth"}
    except DVRIPError:
        return None, {"base": "cannot_connect"}
    finally:
        await client.close()


class XMeyeConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            info, errors = await _validate(user_input)
            if info is not None:
                await self.async_set_unique_id(str(info.get("SerialNo") or user_input[CONF_HOST]))
                self._abort_if_unique_id_configured(
                    updates={CONF_HOST: user_input[CONF_HOST], CONF_PORT: user_input[CONF_PORT]}
                )
                return self.async_create_entry(
                    title=f"{info.get('HardWare') or 'NVR'} ({user_input[CONF_HOST]})",
                    data=user_input,
                )
        schema = vol.Schema(
            {
                vol.Required(CONF_HOST): str,
                vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
                vol.Required(CONF_RTSP_PORT, default=DEFAULT_RTSP_PORT): int,
                vol.Required(CONF_USERNAME, default="admin"): str,
                vol.Optional(CONF_PASSWORD, default=""): PASSWORD,
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(schema, user_input),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            data = {**entry.data, CONF_PASSWORD: user_input[CONF_PASSWORD]}
            info, errors = await _validate(data)
            if info is not None:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_PASSWORD: user_input[CONF_PASSWORD]}
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Optional(CONF_PASSWORD, default=""): PASSWORD}),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return XMeyeOptionsFlow()


class XMeyeOptionsFlow(OptionsFlow):
    """Channel names (empty hides a channel) and H.265 handling."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self.config_entry
        nvr_channels: dict[int, str] = (
            entry.runtime_data.nvr_channels if hasattr(entry, "runtime_data") else {}
        )
        if user_input is not None:
            names = {
                str(ch + 1): str(user_input.get(f"channel_{ch + 1}", "")).strip()
                for ch in nvr_channels
            }
            return self.async_create_entry(
                data={
                    CONF_TRANSCODE_H265: user_input[CONF_TRANSCODE_H265],
                    CONF_NAMES: names,
                }
            )
        names = entry.options.get(CONF_NAMES, {})
        fields: dict[Any, Any] = {}
        suggested: dict[str, str] = {}
        for ch, title in nvr_channels.items():
            key = f"channel_{ch + 1}"
            fields[vol.Optional(key)] = str
            suggested[key] = names.get(str(ch + 1), title)
        fields[
            vol.Required(
                CONF_TRANSCODE_H265,
                default=entry.options.get(CONF_TRANSCODE_H265, DEFAULT_TRANSCODE_H265),
            )
        ] = BooleanSelector()
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(vol.Schema(fields), suggested),
        )
