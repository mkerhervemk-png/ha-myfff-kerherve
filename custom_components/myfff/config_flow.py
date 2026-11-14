"""Assistant de configuration MyFFF (Portail des Officiels)."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from . import create_client
from .api import Dashboard, FFFAuthError, FFFConnectionError, FFFError
from .const import (
    CONF_MATCH_DURATION,
    CONF_SCAN_INTERVAL,
    DEFAULT_MATCH_DURATION_MIN,
    DEFAULT_SCAN_INTERVAL_H,
    DOMAIN,
    MAX_MATCH_DURATION_MIN,
    MAX_SCAN_INTERVAL_H,
    MIN_MATCH_DURATION_MIN,
    MIN_SCAN_INTERVAL_H,
)

_LOGGER = logging.getLogger(__name__)

PASSWORD_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))
USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): TextSelector(TextSelectorConfig(type=TextSelectorType.EMAIL)),
        vol.Required(CONF_PASSWORD): PASSWORD_SELECTOR,
    }
)


class MyFFFConfigFlow(ConfigFlow, domain=DOMAIN):
    """Gère l'ajout d'un compte FFF d'officiel."""

    VERSION = 1

    def __init__(self) -> None:
        self._email: str = ""

    async def _try_login(self, email: str, password: str) -> tuple[Dashboard | None, str | None]:
        client = create_client(self.hass, email, password)
        try:
            return await client.login(), None
        except FFFAuthError as err:
            _LOGGER.warning("MyFFF : connexion refusée : %s", err)
            return None, "invalid_auth"
        except FFFConnectionError as err:
            _LOGGER.warning("MyFFF : portail injoignable : %s", err)
            return None, "cannot_connect"
        except FFFError as err:
            _LOGGER.warning("MyFFF : portail inaccessible : %s", err)
            return None, "no_portal"
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Erreur MyFFF inattendue")
            return None, "unknown"

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            self._email = user_input[CONF_EMAIL].strip()
            password = user_input[CONF_PASSWORD]
            dashboard, error = await self._try_login(self._email, password)
            if error:
                errors["base"] = error
            elif dashboard is not None:
                await self.async_set_unique_id(self._email.lower())
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"MyFFF — {dashboard.first_name or self._email}",
                    data={CONF_EMAIL: self._email, CONF_PASSWORD: password},
                )

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                USER_SCHEMA, {CONF_EMAIL: self._email}
            ),
            errors=errors,
        )

    # ------------------------------------------------------------- reauth

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        self._email = entry_data[CONF_EMAIL]
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            _, error = await self._try_login(self._email, user_input[CONF_PASSWORD])
            if error:
                errors["base"] = error
            else:
                return self.async_update_reload_and_abort(
                    self._get_reauth_entry(),
                    data_updates={CONF_PASSWORD: user_input[CONF_PASSWORD]},
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): PASSWORD_SELECTOR}),
            description_placeholders={"email": self._email},
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return MyFFFOptionsFlow()


class MyFFFOptionsFlow(OptionsFlow):
    """Fréquence de lecture du portail et durée d'un match au calendrier."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data={k: int(v) for k, v in user_input.items()})

        opts = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=opts.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_H),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_SCAN_INTERVAL_H,
                        max=MAX_SCAN_INTERVAL_H,
                        step=1,
                        unit_of_measurement="h",
                        mode=NumberSelectorMode.BOX,
                    )
                ),
                vol.Required(
                    CONF_MATCH_DURATION,
                    default=opts.get(CONF_MATCH_DURATION, DEFAULT_MATCH_DURATION_MIN),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_MATCH_DURATION_MIN,
                        max=MAX_MATCH_DURATION_MIN,
                        step=5,
                        unit_of_measurement="min",
                        mode=NumberSelectorMode.BOX,
                    )
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
