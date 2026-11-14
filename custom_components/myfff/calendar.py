"""Calendrier MyFFF : toutes les désignations (passées et à venir)."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from . import MyFFFConfigEntry
from .api import Designation
from .coordinator import MyFFFCoordinator, local_start
from .entity import MyFFFEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MyFFFConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([MyFFFCalendar(entry.runtime_data)])


class MyFFFCalendar(MyFFFEntity, CalendarEntity):
    """Un événement par match arbitré, avec le stade comme lieu."""

    def __init__(self, coordinator: MyFFFCoordinator) -> None:
        super().__init__(coordinator, "calendar")

    def _event(self, d: Designation) -> CalendarEvent | None:
        start = local_start(d)
        if start is None:
            return None
        desc = [
            p
            for p in (
                d.competition,
                d.role and f"Poste : {d.role}",
                d.distance_km is not None and f"Distance : {d.distance_km:g} km",
                d.surface and f"Terrain : {d.surface}",
                d.url,
            )
            if p
        ]
        location = ", ".join(p for p in (d.venue, d.address) if p) or None
        return CalendarEvent(
            start=start,
            end=start + self.coordinator.data.match_duration,
            summary=f"🟨 {d.match}",
            description="\n".join(desc) or None,
            location=location,
            uid=f"designation-{d.id}",
        )

    def _all_events(self) -> list[CalendarEvent]:
        events = [e for e in map(self._event, self.coordinator.data.designations) if e]
        return sorted(events, key=lambda e: e.start_datetime_local)

    @property
    def event(self) -> CalendarEvent | None:
        now = dt_util.now()
        upcoming = [e for e in self._all_events() if e.end_datetime_local >= now]
        return upcoming[0] if upcoming else None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        return [
            e
            for e in self._all_events()
            if e.end_datetime_local > start_date and e.start_datetime_local < end_date
        ]
