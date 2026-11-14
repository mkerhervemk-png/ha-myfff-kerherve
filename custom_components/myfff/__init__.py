"""Intégration MyFFF (Portail des Officiels FFF) pour Home Assistant."""

from __future__ import annotations

import logging

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .api import OfficielsClient
from .coordinator import MyFFFCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.CALENDAR]

type MyFFFConfigEntry = ConfigEntry[MyFFFCoordinator]


def create_client(hass: HomeAssistant, email: str, password: str) -> OfficielsClient:
    """Un client avec son propre pot de cookies (une session FFF par compte)."""
    session = async_create_clientsession(hass, cookie_jar=aiohttp.CookieJar())
    return OfficielsClient(session, email, password)


async def async_setup_entry(hass: HomeAssistant, entry: MyFFFConfigEntry) -> bool:
    client = create_client(hass, entry.data[CONF_EMAIL], entry.data[CONF_PASSWORD])
    coordinator = MyFFFCoordinator(hass, entry, client)
    # Lève ConfigEntryAuthFailed (reconnexion) ou ConfigEntryNotReady (réessai) si besoin.
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload_on_options))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: MyFFFConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload_on_options(hass: HomeAssistant, entry: MyFFFConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
