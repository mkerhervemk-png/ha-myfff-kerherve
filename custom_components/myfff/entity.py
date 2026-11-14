"""Entité de base MyFFF."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import BASE_URL
from .const import DOMAIN, MANUFACTURER
from .coordinator import MyFFFCoordinator


class MyFFFEntity(CoordinatorEntity[MyFFFCoordinator]):
    """Rattache toutes les entités à un appareil « service » par compte."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: MyFFFCoordinator, key: str) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        uid = entry.unique_id or entry.entry_id
        self._attr_unique_id = f"{uid}_{key}"
        self._attr_translation_key = key
        first_name = coordinator.data.dashboard.first_name if coordinator.data else ""
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, uid)},
            name=f"MyFFF {first_name}".strip(),
            manufacturer=MANUFACTURER,
            model="Portail des Officiels",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url=BASE_URL,
        )
