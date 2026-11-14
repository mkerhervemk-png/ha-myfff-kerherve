"""Client du Portail des Officiels FFF (officiels.fff.fr).

Le portail n'a pas d'API : on se connecte comme un navigateur (SSO FFF) puis on
lit les pages HTML. Lecture seule : aucune action n'est faite sur le portail.

Les fonctions ``parse_*`` sont pures (HTML -> données) pour être testables.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any
from urllib.parse import urljoin, urlsplit

import aiohttp
from bs4 import BeautifulSoup, Tag

_LOGGER = logging.getLogger(__name__)

BASE_URL = "https://officiels.fff.fr"
PATH_HOME = "/"
PATH_DESIGNATIONS = "/designations"
PATH_DESIGNATION = "/designation/{id}"
PATH_REPORTS = "/rapports"

TIMEOUT = aiohttp.ClientTimeout(total=30)
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/130.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9",
}

_DATE_RE = re.compile(r"(\d{2})/(\d{2})/(\d{4})(?:\s*-\s*(\d{1,2})\s*[Hh:]\s*(\d{2}))?")
_ID_RE = re.compile(r"/designation/(\d+)")
_KM_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*km", re.IGNORECASE)


class FFFError(Exception):
    """Erreur générique du portail."""


class FFFAuthError(FFFError):
    """Identifiants refusés."""


class FFFConnectionError(FFFError):
    """Portail injoignable."""


# --------------------------------------------------------------------- modèles


@dataclass
class Designation:
    """Une désignation d'arbitre (un match)."""

    id: str
    start: datetime | None  # naïf, heure locale française
    match: str
    competition: str = ""
    role: str = ""
    upcoming: bool = True
    # Détails (fiche de la désignation)
    organizer: str = ""
    home: str = ""
    away: str = ""
    venue: str = ""
    address: str = ""
    distance_km: float | None = None
    surface: str = ""
    officials: list[dict[str, str]] = field(default_factory=list)

    @property
    def url(self) -> str:
        return BASE_URL + PATH_DESIGNATION.format(id=self.id)

    def signature(self) -> str:
        """Ce qui, s'il change, mérite un événement « modifiée »."""
        start = self.start.isoformat() if self.start else ""
        return "|".join([start, self.match, self.role, self.venue, self.address])

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["start"] = self.start.isoformat() if self.start else None
        data["url"] = self.url
        return data


@dataclass
class Dashboard:
    first_name: str = ""
    new_messages: int = 0


@dataclass
class Reports:
    pending: list[dict[str, str]] = field(default_factory=list)


@dataclass
class LoginForm:
    action: str
    fields: dict[str, str]
    email_field: str
    password_field: str


# --------------------------------------------------------------------- parseurs


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html or "", "html.parser")


def _text(node: Tag | None) -> str:
    if node is None:
        return ""
    return re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip()


def parse_datetime(text: str) -> datetime | None:
    """« 14/11/2026 - 15H00 » -> datetime naïf. Sans heure -> minuit."""
    m = _DATE_RE.search(text or "")
    if not m:
        return None
    day, month, year, hour, minute = m.groups()
    try:
        return datetime(int(year), int(month), int(day), int(hour or 0), int(minute or 0))
    except ValueError:
        return None


def parse_login_form(html: str) -> LoginForm | None:
    """Retourne le formulaire de connexion SSO s'il est présent dans la page."""
    soup = _soup(html)
    for form in soup.find_all("form"):
        password = form.find("input", attrs={"type": "password"})
        if password is None or not password.get("name"):
            continue
        email = form.find("input", attrs={"type": "email"}) or form.find(
            "input", attrs={"type": "text"}
        )
        if email is None or not email.get("name"):
            continue
        fields: dict[str, str] = {}
        for inp in form.find_all("input"):
            name = inp.get("name")
            if not name:
                continue
            if inp.get("type") in ("hidden", "submit"):
                fields[name] = inp.get("value", "")
        return LoginForm(
            action=form.get("action") or "",
            fields=fields,
            email_field=email["name"],
            password_field=password["name"],
        )
    return None


def is_logged_in(html: str) -> bool:
    return "/logout" in (html or "")


def _section_by_title(soup: BeautifulSoup, needle: str) -> Tag | None:
    needle = needle.lower()
    for title in soup.find_all(["h1", "h2"]):
        if needle in _text(title).lower():
            parent = title.find_parent(["section", "article"])
            if parent is not None:
                return parent
    return None


def parse_designations(html: str) -> list[Designation]:
    """Page /designations : tableaux « à venir » puis « historique »."""
    soup = _soup(html)
    result: list[Designation] = []
    seen: set[str] = set()
    for table in soup.find_all("table"):
        section = table.find_parent("section")
        title = _text(section.find(["h2", "h1"])) if section else ""
        upcoming = "venir" in title.lower()
        body = table.find("tbody") or table
        for row in body.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) < 2:
                continue
            link = row.find("a", href=_ID_RE)
            m = _ID_RE.search(link["href"]) if link else None
            if not m:
                continue
            did = m.group(1)
            if did in seen:
                continue
            seen.add(did)
            # La 1re cellule contient aussi la compétition (span mobile) : on l'ôte.
            date_cell = cells[0]
            for span in date_cell.find_all("span"):
                span.extract()
            result.append(
                Designation(
                    id=did,
                    start=parse_datetime(_text(date_cell)),
                    match=_text(cells[1]),
                    competition=_text(cells[2]) if len(cells) > 2 else "",
                    role=_text(cells[3]) if len(cells) > 3 else "",
                    upcoming=upcoming,
                )
            )
    return result


def parse_designation_detail(html: str, designation: Designation) -> Designation:
    """Complète une désignation avec sa fiche (/designation/<id>)."""
    soup = _soup(html)

    item = soup.find(class_="designation-item")
    if item is not None:
        inner = item.find(class_="designation-item__inner") or item
        first_p = inner.find("p")
        if first_p is not None and "designation-item__date" not in (first_p.get("class") or []):
            designation.organizer = _text(first_p)
        comp = _text(item.find(class_="designation-item__competition"))
        if comp:
            designation.competition = re.sub(r"\s*-\s*", " - ", comp)
        home = item.find(class_="designation-team--home")
        away = item.find(class_="designation-team--away")
        designation.home = _text(home.find(class_="designation-team__name")) if home else ""
        designation.away = _text(away.find(class_="designation-team__name")) if away else ""

    officials = _section_by_title(soup, "Officiels désignés")
    if officials is not None:
        designation.officials = [
            {
                "poste": _text(li.find(class_="list-designation--position")),
                "nom": _text(li.find(class_="list-designation--name")),
            }
            for li in officials.find_all("li")
            if li.find(class_="list-designation--name") is not None
        ]

    infos = _section_by_title(soup, "Informations")
    if infos is not None:
        for li in infos.find_all("li"):
            label = _text(li.find(class_="list-designation--position")).lower()
            value = _text(li.find(class_="list-designation--name"))
            if "distance" in label:
                m = _KM_RE.search(value)
                if m:
                    designation.distance_km = float(m.group(1).replace(",", "."))
            elif "installation" in label:
                designation.surface = value

    venue = soup.find(class_="map-title")
    if venue is not None:
        designation.venue = _text(venue)
        holder = venue.parent
        addr = holder.find("p") if holder is not None else None
        if addr is not None:
            lines = [s.strip() for s in addr.get_text("\n").split("\n")]
            designation.address = ", ".join(line for line in lines if line)
    return designation


def parse_dashboard(html: str) -> Dashboard:
    soup = _soup(html)
    dash = Dashboard()
    for title in soup.find_all(["h1", "h2"]):
        m = re.match(r"bonjour\s+(.+)", _text(title), re.IGNORECASE)
        if m:
            dash.first_name = m.group(1).strip().title()
            break
    section = _section_by_title(soup, "Nouveaux messages")
    if section is not None:
        body = section.find("tbody")
        if body is not None:
            dash.new_messages = len(body.find_all("tr"))
        else:
            dash.new_messages = len(section.find_all("li"))
    return dash


def parse_reports(html: str) -> Reports:
    """Page /rapports : rapports « à saisir ou en cours de saisie »."""
    soup = _soup(html)
    reports = Reports()
    for title in soup.find_all("h2"):
        if "saisir" not in _text(title).lower():
            continue
        table = title.find_next_sibling("table")
        if table is None:
            continue
        section = title.find_parent("section")
        kind = _text(section.find("h1")) if section else ""
        body = table.find("tbody") or table
        for row in body.find_all("tr"):
            cells = [_text(c) for c in row.find_all("td")]
            if len(cells) < 3:
                continue
            reports.pending.append(
                {"type": kind, "match": cells[0], "competition": cells[1], "date": cells[2]}
            )
    return reports


# ----------------------------------------------------------------------- client


class OfficielsClient:
    """Session authentifiée sur le Portail des Officiels.

    ``session`` doit avoir son propre pot de cookies (un par compte).
    """

    def __init__(self, session: aiohttp.ClientSession, email: str, password: str) -> None:
        self._session = session
        self._email = email
        self._password = password
        self._lock = asyncio.Lock()
        self.dashboard: Dashboard | None = None

    async def _request(
        self,
        method: str,
        url: str,
        data: dict[str, str] | None = None,
        referer: str | None = None,
    ) -> tuple[str, str]:
        """Retourne (url finale, html). Suit les redirections (SSO)."""
        headers = dict(HEADERS)
        if referer:
            parts = urlsplit(referer)
            headers["Referer"] = referer
            headers["Origin"] = f"{parts.scheme}://{parts.netloc}"
        try:
            async with self._session.request(
                method, url, data=data, headers=headers, timeout=TIMEOUT, allow_redirects=True
            ) as resp:
                if resp.status in (401, 403):
                    raise FFFConnectionError(f"Accès refusé par la FFF (HTTP {resp.status})")
                if resp.status >= 500:
                    raise FFFConnectionError(f"Portail en erreur (HTTP {resp.status})")
                html = await resp.text()
                return str(resp.url), html
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise FFFConnectionError(f"Portail injoignable : {err}") from err

    async def _login_with(self, page_url: str, form: LoginForm) -> str:
        payload = dict(form.fields)
        payload[form.email_field] = self._email
        payload[form.password_field] = self._password
        target = urljoin(page_url, form.action or page_url)
        _, html = await self._request("POST", target, payload, referer=page_url)
        if parse_login_form(html) is not None:
            raise FFFAuthError("Email ou mot de passe refusé par la FFF")
        return html

    async def _page(self, path: str) -> str:
        """Lit une page du portail, en se (re)connectant si nécessaire."""
        async with self._lock:
            url = BASE_URL + path
            final_url, html = await self._request("GET", url)
            form = parse_login_form(html)
            if form is not None:
                _LOGGER.debug("Session FFF absente ou expirée : connexion")
                html = await self._login_with(final_url, form)
                # Après le SSO on atterrit sur l'accueil : on redemande la page voulue.
                if path != PATH_HOME or not is_logged_in(html):
                    _, html = await self._request("GET", url)
                if parse_login_form(html) is not None:
                    raise FFFAuthError("Connexion FFF refusée")
            if not is_logged_in(html):
                raise FFFError(
                    "Page inattendue : ce compte FFF n'a peut-être pas accès au Portail des Officiels"
                )
            return html

    async def login(self) -> Dashboard:
        """Vérifie les identifiants et retourne le tableau de bord."""
        return await self.fetch_dashboard()

    async def fetch_dashboard(self) -> Dashboard:
        self.dashboard = parse_dashboard(await self._page(PATH_HOME))
        return self.dashboard

    async def fetch_designations(self) -> list[Designation]:
        return parse_designations(await self._page(PATH_DESIGNATIONS))

    async def fetch_designation_detail(self, designation: Designation) -> Designation:
        html = await self._page(PATH_DESIGNATION.format(id=designation.id))
        return parse_designation_detail(html, designation)

    async def fetch_reports(self) -> Reports:
        return parse_reports(await self._page(PATH_REPORTS))
