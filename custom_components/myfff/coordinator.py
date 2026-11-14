"""Coordinateur MyFFF : lit le portail et détecte les nouveautés."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import (
    Dashboard,
    Designation,
    FFFAuthError,
    FFFError,
    OfficielsClient,
    Reports,
)
from .const import (
    CONF_MATCH_DURATION,
    CONF_SCAN_INTERVAL,
    DEFAULT_MATCH_DURATION_MIN,
    DEFAULT_SCAN_INTERVAL_H,
    DOMAIN,
    EVENT_DESIGNATION_CHANGED,
    EVENT_DESIGNATION_REMOVED,
    EVENT_NEW_DESIGNATION,
    HISTORY_DETAILS,
    STORAGE_VERSION,
)

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

_LOGGER = logging.getLogger(__name__)


def local_start(d: Designation) -> datetime | None:
    """Heure du match avec le fuseau de Home Assistant."""
    if d.start is None:
        return None
    return d.start.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)


def designation_attrs(d: Designation | None) -> dict[str, Any]:
    """Attributs en français, lisibles dans les automatisations et par ADRIA."""
    if d is None:
        return {}
    start = local_start(d)
    return {
        "id": d.id,
        "debut": start.isoformat() if start else None,
        "match": d.match,
        "equipe_domicile": d.home,
        "equipe_exterieur": d.away,
        "competition": d.competition,
        "poste": d.role,
        "organisateur": d.organizer,
        "stade": d.venue,
        "adresse": d.address,
        "distance_km": d.distance_km,
        "installation": d.surface,
        "officiels": d.officials,
        "url": d.url,
    }


@dataclass
class MyFFFData:
    dashboard: Dashboard = field(default_factory=Dashboard)
    designations: list[Designation] = field(default_factory=list)
    reports: Reports = field(default_factory=Reports)
    match_duration: timedelta = timedelta(minutes=DEFAULT_MATCH_DURATION_MIN)

    def _sorted(self, items: list[Designation], reverse: bool = False) -> list[Designation]:
        return sorted(
            (d for d in items if d.start is not None), key=lambda d: d.start, reverse=reverse
        )

    @property
    def upcoming(self) -> list[Designation]:
        """Désignations dont le match n'est pas terminé."""
        now = dt_util.now()
        return self._sorted(
            [
                d
                for d in self.designations
                if d.start is not None and local_start(d) + self.match_duration >= now
            ]
        )

    @property
    def past(self) -> list[Designation]:
        now = dt_util.now()
        return self._sorted(
            [
                d
                for d in self.designations
                if d.start is not None and local_start(d) + self.match_duration < now
            ],
            reverse=True,
        )

    @property
    def next(self) -> Designation | None:
        up = self.upcoming
        return up[0] if up else None

    @property
    def last(self) -> Designation | None:
        past = self.past
        return past[0] if past else None

    @property
    def today(self) -> list[Designation]:
        today = dt_util.now().date()
        return self._sorted(
            [d for d in self.designations if d.start is not None and d.start.date() == today]
        )


class MyFFFCoordinator(DataUpdateCoordinator[MyFFFData]):
    """Un coordinateur par compte FFF."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: OfficielsClient) -> None:
        hours = int(entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_H))
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=timedelta(hours=hours),
        )
        self.client = client
        self._duration = timedelta(
            minutes=int(entry.options.get(CONF_MATCH_DURATION, DEFAULT_MATCH_DURATION_MIN))
        )
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}"
        )
        # id -> signature des désignations à venir déjà vues (None = jamais chargé)
        self._known: dict[str, str] | None = None
        self._details: dict[str, Designation] = {}

    async def _async_setup(self) -> None:
        stored = await self._store.async_load()
        if stored and isinstance(stored.get("known"), dict):
            self._known = dict(stored["known"])

    async def _async_update_data(self) -> MyFFFData:
        try:
            dashboard = await self.client.fetch_dashboard()
            designations = await self.client.fetch_designations()
            await self._add_details(designations)
            reports = await self.client.fetch_reports()
        except FFFAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except FFFError as err:
            raise UpdateFailed(str(err)) from err

        data = MyFFFData(
            dashboard=dashboard,
            designations=designations,
            reports=reports,
            match_duration=self._duration,
        )
        await self._fire_events(data)
        return data

    async def _add_details(self, designations: list[Designation]) -> None:
        """Lit la fiche des matchs à venir (toujours) et des derniers passés (une fois)."""
        past = sorted(
            (d for d in designations if not d.upcoming and d.start is not None),
            key=lambda d: d.start,
            reverse=True,
        )[:HISTORY_DETAILS]
        past_ids = {d.id for d in past}
        for d in designations:
            cached = self._details.get(d.id)
            if d.upcoming or (d.id in past_ids and cached is None):
                try:
                    await self.client.fetch_designation_detail(d)
                    self._details[d.id] = d
                    continue
                except FFFAuthError:
                    raise
                except FFFError as err:
                    _LOGGER.debug("Fiche %s illisible : %s", d.id, err)
            if cached is not None:
                for attr in (
                    "organizer", "home", "away", "venue", "address",
                    "distance_km", "surface", "officials",
                ):
                    setattr(d, attr, getattr(cached, attr))
                if not d.competition:
                    d.competition = cached.competition

    async def _fire_events(self, data: MyFFFData) -> None:
        current = {d.id: d for d in data.designations if d.upcoming}
        signatures = {did: d.signature() for did, d in current.items()}
        if self._known is not None:
            for did, d in current.items():
                if did not in self._known:
                    self._fire(EVENT_NEW_DESIGNATION, d)
                elif self._known[did] != signatures[did]:
                    self._fire(EVENT_DESIGNATION_CHANGED, d)
            history_ids = {d.id for d in data.designations if not d.upcoming}
            for did in self._known:
                if did not in current and did not in history_ids:
                    self.hass.bus.async_fire(
                        EVENT_DESIGNATION_REMOVED,
                        {"config_entry_id": self.config_entry.entry_id, "id": did},
                    )
        if signatures != self._known:
            self._known = signatures
            await self._store.async_save({"known": signatures})

    def _fire(self, event: str, d: Designation) -> None:
        payload = designation_attrs(d)
        payload["config_entry_id"] = self.config_entry.entry_id
        dash = self.client.dashboard
        payload["officiel"] = dash.first_name if dash else ""
        self.hass.bus.async_fire(event, payload)
