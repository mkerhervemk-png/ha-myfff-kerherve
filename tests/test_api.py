"""Parseurs et connexion, sans Home Assistant."""
from datetime import datetime

import pytest

from custom_components.myfff.api import (
    FFFAuthError,
    FFFConnectionError,
    OfficielsClient,
    parse_dashboard,
    parse_datetime,
    parse_designation_detail,
    parse_designations,
    parse_login_form,
    parse_reports,
)

from .helpers import designations_page, detail_page, fx, home_page, row, standard_portal

NOW = datetime(2026, 11, 13, 10, 0)


def test_parse_datetime():
    assert parse_datetime("14/11/2026 - 15H00") == datetime(2026, 11, 14, 15, 0)
    assert parse_datetime("19/09/2026 - 9h30") == datetime(2026, 9, 19, 9, 30)
    assert parse_datetime("14/11/2026") == datetime(2026, 11, 14)
    assert parse_datetime("bientôt") is None


def test_parse_login_form():
    form = parse_login_form(fx("login"))
    assert form.action == "/oauth/v2/login"
    assert (form.email_field, form.password_field) == ("emailCanonical", "password")
    assert form.fields == {"_csrf_token": "tok-123", "_submit": "Se connecter"}
    assert parse_login_form(home_page()) is None


def test_parse_designations():
    html = designations_page(
        [row("900", datetime(2026, 11, 14, 15, 0), "FC ALPHA - AS BETA")],
        [row("800", datetime(2026, 11, 7, 15, 0), "US GAMMA - FC DELTA", role="Arbitre assistant 1")],
    )
    up, past = parse_designations(html)
    assert (up.id, up.upcoming, up.start) == ("900", True, datetime(2026, 11, 14, 15, 0))
    assert (up.match, up.competition, up.role) == ("FC ALPHA - AS BETA", "U15 DISTRICT 2", "Arbitre centre")
    assert (past.id, past.upcoming, past.role) == ("800", False, "Arbitre assistant 1")
    assert parse_designations(designations_page([], [])) == []


def test_parse_detail():
    d = parse_designations(designations_page([row("900", NOW, "FC ALPHA - AS BETA")], []))[0]
    parse_designation_detail(detail_page("900", "FC ALPHA", "AS BETA"), d)
    assert (d.home, d.away) == ("FC ALPHA", "AS BETA")
    assert d.organizer == "DISTRICT FOOTBALL TEST"
    assert d.competition == "U15 DISTRICT 2 - POULE A"
    assert (d.venue, d.address) == ("STADE TEST 1", "RUE DU STADE, 22000 VILLE TEST")
    assert (d.distance_km, d.surface) == (25.0, "Pelouse Naturelle")
    assert d.officials == [{"poste": "Arbitre centre", "nom": "CAMILLE EXEMPLE"}]
    assert d.url.endswith("/designation/900")


def test_parse_dashboard_and_reports():
    assert parse_dashboard(home_page()).first_name == "Camille"
    assert parse_dashboard(home_page()).new_messages == 0
    assert parse_dashboard(home_page(messages=2)).new_messages == 2
    pending = parse_reports(fx("reports")).pending
    assert pending == [{
        "type": "Rapports de discipline", "match": "FC ALPHA - AS BETA",
        "competition": "U15 DISTRICT 2 - Journée 6", "date": "14/11/2026",
    }]


async def test_login_flow_and_session_reuse():
    portal = standard_portal(NOW)
    client = OfficielsClient(portal, "a@b.fr", "bon-mdp")
    dash = await client.login()
    assert dash.first_name == "Camille"
    assert portal.posted == {
        "emailCanonical": "a@b.fr", "password": "bon-mdp",
        "_csrf_token": "tok-123", "_submit": "Se connecter",
    }
    assert ("POST", "https://sso.fff.fr/oauth/v2/login") in portal.calls
    n = len(portal.calls)
    assert len(await client.fetch_designations()) == 3
    assert len(portal.calls) == n + 1  # session réutilisée : pas de nouveau login

    portal.logged_in = False  # session expirée -> reconnexion transparente
    assert len((await client.fetch_reports()).pending) == 1


async def test_bad_password_and_errors():
    portal = standard_portal(NOW)
    with pytest.raises(FFFAuthError):
        await OfficielsClient(portal, "a@b.fr", "mauvais").login()
    portal.status = 403
    with pytest.raises(FFFConnectionError):
        await OfficielsClient(portal, "a@b.fr", "bon-mdp").login()
