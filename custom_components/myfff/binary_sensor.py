"""Capteurs binaires MyFFF."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import MyFFFConfigEntry
from .coordinator import MyFFFCoordinator, designation_attrs
from .entity import MyFFFEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MyFFFConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities([RefereeTodaySensor(coordinator), ReportPendingSensor(coordinator)])


class RefereeTodaySensor(MyFFFEntity, BinarySensorEntity):
    """Vrai si une désignation a lieu aujourd'hui."""

    _attr_icon = "mdi:whistle"

    def __init__(self, coordinator: MyFFFCoordinator) -> None:
        super().__init__(coordinator, "referee_today")

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.data.today)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"matchs": [designation_attrs(d) for d in self.coordinator.data.today]}


class ReportPendingSensor(MyFFFEntity, BinarySensorEntity):
    """Vrai si un rapport reste à saisir sur le portail."""

    _attr_icon = "mdi:file-document-alert-outline"

    def __init__(self, coordinator: MyFFFCoordinator) -> None:
        super().__init__(coordinator, "report_pending")

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.data.reports.pending)
