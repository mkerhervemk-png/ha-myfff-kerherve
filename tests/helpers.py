"""Pages simulées du Portail des Officiels (données fictives)."""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from yarl import URL

FIX = Path(__file__).parent / "fixtures"


def fx(name: str) -> str:
    return (FIX / f"{name}.html").read_text()


def row(did: str, when: datetime, match: str, comp: str = "U15 DISTRICT 2", role: str = "Arbitre centre") -> str:
    return (
        fx("row")
        .replace("__ID__", did)
        .replace("__DATE__", when.strftime("%d/%m/%Y - %HH%M"))
        .replace("__MATCH__", match)
        .replace("__COMP__", comp)
        .replace("__ROLE__", role)
    )


def designations_page(upcoming: list[str], history: list[str]) -> str:
    return fx("designations").replace("__UPCOMING__", "".join(upcoming)).replace(
        "__HISTORY__", "".join(history)
    )


def detail_page(did: str, home: str, away: str, venue: str = "STADE TEST 1") -> str:
    return (
        fx("detail")
        .replace("__ID__", did)
        .replace("__HOME__", home)
        .replace("__AWAY__", away)
        .replace("__VENUE__", venue)
    )


def home_page(messages: int = 0) -> str:
    if messages:
        body = "<table><tbody>" + "<tr><td>Sujet</td></tr>" * messages + "</tbody></table>"
    else:
        body = '<p class="fade">Vous n\'avez pas de nouveaux messages.</p>'
    return fx("home").replace("__MESSAGES__", body)


class FakeResponse:
    def __init__(self, url: str, text: str, status: int = 200) -> None:
        self.url, self._text, self.status = URL(url), text, status
        self.headers = {"Server": "AkamaiGHost", "x-reference-error": "test-akamai-reference"}

    async def text(self) -> str:
        return self._text

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class FakePortal:
    """Imite officiels.fff.fr + sso.fff.fr : session par cookie, login par formulaire."""

    BASE = "https://officiels.fff.fr"
    SSO = "https://sso.fff.fr/oauth/v2/login"

    def __init__(self, password: str = "bon-mdp") -> None:
        self.password = password
        self.logged_in = False
        self.pages: dict[str, str] = {}
        self.calls: list[tuple[str, str]] = []
        self.posted: dict[str, str] | None = None
        self.status = 200

    def request(self, method, url, data=None, **kwargs):
        self.calls.append((method, url))
        if self.status != 200:
            return FakeResponse(url, "", self.status)
        if method == "POST":
            self.posted = dict(data)
            if data.get("password") == self.password and data.get("_csrf_token") == "tok-123":
                self.logged_in = True
                return FakeResponse(self.BASE + "/", self.pages["/"])
            return FakeResponse(self.SSO, fx("login"))
        if not self.logged_in:
            return FakeResponse(self.SSO, fx("login"))
        path = url[len(self.BASE):]
        return FakeResponse(url, self.pages[path])


def standard_portal(now: datetime) -> FakePortal:
    """1 match demain, 2 matchs passés, 1 rapport à saisir."""
    portal = FakePortal()
    tomorrow = (now + timedelta(days=1)).replace(hour=15, minute=0, second=0, microsecond=0)
    portal.pages = {
        "/": home_page(),
        "/designations": designations_page(
            [row("900", tomorrow, "FC ALPHA - AS BETA")],
            [
                row("800", tomorrow - timedelta(days=8), "US GAMMA - FC DELTA"),
                row("700", tomorrow - timedelta(days=50, minutes=-30), "ES EPSILON - AS ZETA"),
            ],
        ),
        "/designation/900": detail_page("900", "FC ALPHA", "AS BETA"),
        "/designation/800": detail_page("800", "US GAMMA", "FC DELTA", "STADE TEST 2"),
        "/designation/700": detail_page("700", "ES EPSILON", "AS ZETA", "STADE TEST 3"),
        "/rapports": fx("reports"),
    }
    return portal
