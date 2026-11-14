"""Constantes de l'intégration MyFFF (Portail des Officiels)."""

from __future__ import annotations

DOMAIN = "myfff"
MANUFACTURER = "Fédération Française de Football"

CONF_SCAN_INTERVAL = "scan_interval"
CONF_MATCH_DURATION = "match_duration"

# Le portail n'a pas d'API : on lit des pages web. On reste discret.
DEFAULT_SCAN_INTERVAL_H = 6
MIN_SCAN_INTERVAL_H = 1
MAX_SCAN_INTERVAL_H = 24

DEFAULT_MATCH_DURATION_MIN = 105
MIN_MATCH_DURATION_MIN = 30
MAX_MATCH_DURATION_MIN = 180

# Nombre de fiches détaillées (stade, adresse…) lues pour l'historique.
HISTORY_DETAILS = 5

EVENT_NEW_DESIGNATION = "myfff_nouvelle_designation"
EVENT_DESIGNATION_CHANGED = "myfff_designation_modifiee"
EVENT_DESIGNATION_REMOVED = "myfff_designation_retiree"

STORAGE_VERSION = 1
