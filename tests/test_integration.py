"""Tests de bout en bout dans Home Assistant, sur un portail simulé."""
from datetime import timedelta
from unittest.mock import patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_capture_events

from custom_components.myfff.api import OfficielsClient
from custom_components.myfff.const import (
    DOMAIN,
    EVENT_DESIGNATION_CHANGED,
    EVENT_DESIGNATION_REMOVED,
    EVENT_NEW_DESIGNATION,
)

from .helpers import designations_page, detail_page, row, standard_portal

CREDS = {"email": "Arbitre@Exemple.fr", "password": "bon-mdp"}


@pytest.fixture
def portal(hass: HomeAssistant):
    hass.config.language = "fr"  # comme la maison : noms d'entités en français
    p = standard_portal(dt_util.now().replace(tzinfo=None))
    make = lambda hass, email, password: OfficielsClient(p, email, password)  # noqa: E731
    with patch("custom_components.myfff.create_client", make), patch(
        "custom_components.myfff.config_flow.create_client", make
    ):
        yield p


async def _setup(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, data=CREDS, unique_id="arbitre@exemple.fr", title="MyFFF — Camille")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_config_flow(hass: HomeAssistant, portal):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] is FlowResultType.FORM

    bad = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"email": CREDS["email"], "password": "mauvais"}
    )
    assert bad["errors"] == {"base": "invalid_auth"}

    ok = await hass.config_entries.flow.async_configure(result["flow_id"], CREDS)
    await hass.async_block_till_done()
    assert ok["type"] is FlowResultType.CREATE_ENTRY
    assert ok["title"] == "MyFFF — Camille"
    assert ok["result"].unique_id == "arbitre@exemple.fr"

    dup = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    dup = await hass.config_entries.flow.async_configure(dup["flow_id"], CREDS)
    assert dup["type"] is FlowResultType.ABORT


async def test_entities(hass: HomeAssistant, portal):
    await _setup(hass)
    tomorrow = (dt_util.now() + timedelta(days=1)).replace(hour=15, minute=0, second=0, microsecond=0)

    nxt = hass.states.get("sensor.myfff_camille_prochaine_designation")
    assert dt_util.parse_datetime(nxt.state) == tomorrow
    assert nxt.attributes["stade"] == "STADE TEST 1"
    assert nxt.attributes["adresse"] == "RUE DU STADE, 22000 VILLE TEST"
    assert nxt.attributes["poste"] == "Arbitre centre"
    assert len(nxt.attributes["a_venir"]) == 1

    assert hass.states.get("sensor.myfff_camille_prochain_match").state == "FC ALPHA - AS BETA"
    assert hass.states.get("sensor.myfff_camille_prochain_stade").state == "STADE TEST 1"
    assert hass.states.get("sensor.myfff_camille_distance_du_prochain_match").state == "25.0"
    assert hass.states.get("sensor.myfff_camille_designations_a_venir").state == "1"
    assert hass.states.get("sensor.myfff_camille_matchs_arbitres_cette_saison").state == "2"
    assert hass.states.get("sensor.myfff_camille_nouveaux_messages").state == "0"
    assert hass.states.get("sensor.myfff_camille_rapports_a_saisir").state == "1"
    assert hass.states.get("binary_sensor.myfff_camille_arbitre_aujourd_hui").state == "off"
    assert hass.states.get("binary_sensor.myfff_camille_rapport_a_saisir").state == "on"

    cal = hass.states.get("calendar.myfff_camille_arbitrage")
    assert cal.attributes["message"] == "🟨 FC ALPHA - AS BETA"
    assert cal.attributes["location"] == "STADE TEST 1, RUE DU STADE, 22000 VILLE TEST"
    events = await hass.services.async_call(
        "calendar", "get_events",
        {"entity_id": "calendar.myfff_camille_arbitrage",
         "start_date_time": (tomorrow - timedelta(days=60)).isoformat(),
         "end_date_time": (tomorrow + timedelta(days=2)).isoformat()},
        blocking=True, return_response=True,
    )
    assert len(events["calendar.myfff_camille_arbitrage"]["events"]) == 3


async def test_events_new_changed_removed(hass: HomeAssistant, portal):
    new = async_capture_events(hass, EVENT_NEW_DESIGNATION)
    changed = async_capture_events(hass, EVENT_DESIGNATION_CHANGED)
    removed = async_capture_events(hass, EVENT_DESIGNATION_REMOVED)
    entry = await _setup(hass)
    coordinator = entry.runtime_data
    assert not new  # premier chargement : pas d'événement

    base = dt_util.now().replace(tzinfo=None, hour=14, minute=0, second=0, microsecond=0)
    later = base + timedelta(days=7)
    r900 = row("900", base + timedelta(days=1, hours=1), "FC ALPHA - AS BETA")
    portal.pages["/designations"] = designations_page([r900, row("950", later, "AS ETA - FC THETA")], [])
    portal.pages["/designation/950"] = detail_page("950", "AS ETA", "FC THETA", "STADE TEST 9")
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert [e.data["id"] for e in new] == ["950"]
    assert new[0].data["stade"] == "STADE TEST 9"
    assert new[0].data["debut"] == later.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE).isoformat()
    assert new[0].data["officiel"] == "Camille"
    assert not changed and not removed

    # Changement d'horaire du 950, retrait du 900
    portal.pages["/designations"] = designations_page(
        [row("950", later + timedelta(hours=2), "AS ETA - FC THETA")], []
    )
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert [e.data["id"] for e in changed] == ["950"]
    assert [e.data["id"] for e in removed] == ["900"]
    assert len(new) == 1


async def test_known_designations_survive_restart(hass: HomeAssistant, portal):
    new = async_capture_events(hass, EVENT_NEW_DESIGNATION)
    entry = await _setup(hass)
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    later = dt_util.now().replace(tzinfo=None) + timedelta(days=5)
    portal.pages["/designations"] = designations_page([row("960", later, "FC IOTA - US KAPPA")], [])
    portal.pages["/designation/960"] = detail_page("960", "FC IOTA", "US KAPPA")
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert [e.data["id"] for e in new] == ["960"]  # arrivée pendant l'arrêt : signalée


async def test_bad_password_starts_reauth(hass: HomeAssistant, portal):
    portal.password = "change"
    entry = MockConfigEntry(domain=DOMAIN, data=CREDS, unique_id="arbitre@exemple.fr")
    entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert flows and flows[0]["context"]["source"] == "reauth"

    done = await hass.config_entries.flow.async_configure(flows[0]["flow_id"], {"password": "change"})
    await hass.async_block_till_done()
    assert done["reason"] == "reauth_successful"
    assert entry.data["password"] == "change"
    assert entry.state is ConfigEntryState.LOADED


async def test_portal_down_keeps_retrying(hass: HomeAssistant, portal):
    portal.status = 503
    entry = MockConfigEntry(domain=DOMAIN, data=CREDS, unique_id="arbitre@exemple.fr")
    entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_RETRY
