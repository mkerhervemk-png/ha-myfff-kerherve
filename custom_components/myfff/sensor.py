"""Capteurs MyFFF."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfLength
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import MyFFFConfigEntry
from .api import Designation
from .coordinator import MyFFFCoordinator, MyFFFData, designation_attrs, local_start
from .entity import MyFFFEntity


@dataclass(frozen=True, kw_only=True)
class MyFFFSensorDescription(SensorEntityDescription):
    value_fn: Callable[[MyFFFData], Any]
    attrs_fn: Callable[[MyFFFData], dict[str, Any]] | None = None


def _next_attrs(data: MyFFFData) -> dict[str, Any]:
    attrs = designation_attrs(data.next)
    attrs["a_venir"] = [designation_attrs(d) for d in data.upcoming]
    return attrs


def _venue(d: Designation | None) -> str | None:
    if d is None:
        return None
    return d.venue or d.address or None


SENSORS: tuple[MyFFFSensorDescription, ...] = (
    MyFFFSensorDescription(
        key="next_designation",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:whistle",
        value_fn=lambda d: local_start(d.next) if d.next else None,
        attrs_fn=_next_attrs,
    ),
    MyFFFSensorDescription(
        key="next_match",
        icon="mdi:soccer",
        value_fn=lambda d: d.next.match if d.next else None,
        attrs_fn=lambda d: designation_attrs(d.next),
    ),
    MyFFFSensorDescription(
        key="next_venue",
        icon="mdi:stadium",
        value_fn=lambda d: _venue(d.next),
        attrs_fn=lambda d: {"adresse": d.next.address, "installation": d.next.surface}
        if d.next
        else {},
    ),
    MyFFFSensorDescription(
        key="next_distance",
        icon="mdi:map-marker-distance",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        value_fn=lambda d: d.next.distance_km if d.next else None,
    ),
    MyFFFSensorDescription(
        key="upcoming_count",
        icon="mdi:calendar-clock",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: len(d.upcoming),
    ),
    MyFFFSensorDescription(
        key="refereed_count",
        icon="mdi:counter",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: len(d.past),
        attrs_fn=lambda d: {"matchs": [designation_attrs(x) for x in d.past[:10]]},
    ),
    MyFFFSensorDescription(
        key="last_designation",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:history",
        value_fn=lambda d: local_start(d.last) if d.last else None,
        attrs_fn=lambda d: designation_attrs(d.last),
    ),
    MyFFFSensorDescription(
        key="new_messages",
        icon="mdi:email-outline",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.dashboard.new_messages,
    ),
    MyFFFSensorDescription(
        key="reports_pending",
        icon="mdi:file-document-edit-outline",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: len(d.reports.pending),
        attrs_fn=lambda d: {"rapports": d.reports.pending},
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MyFFFConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(MyFFFSensor(coordinator, desc) for desc in SENSORS)


class MyFFFSensor(MyFFFEntity, SensorEntity):
    entity_description: MyFFFSensorDescription

    def __init__(self, coordinator: MyFFFCoordinator, description: MyFFFSensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        fn = self.entity_description.attrs_fn
        return fn(self.coordinator.data) if fn else None
