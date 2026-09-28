"""Zugriff auf die OpenF1-API: Anmeldung, Abruf und lokaler Cache.

Zugangsdaten kommen aus der Datei .env im Projektordner:
    OPENF1_USERNAME=...
    OPENF1_PASSWORD=...

Jede Antwort wird unter data/cache/<session_key>/<endpoint>.json gespeichert.
Beim nächsten Aufruf wird nur noch die lokale Datei gelesen – eine beendete
Session ändert sich nicht mehr. Mit refresh=True wird neu geladen.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

BASE_URL = "https://api.openf1.org/v1"
TOKEN_URL = "https://api.openf1.org/token"
REPO = Path(__file__).resolve().parent.parent
CACHE_DIR = REPO / "data" / "cache"

SESSION_NAMES = {
    "FP1": "Practice 1", "FP2": "Practice 2", "FP3": "Practice 3",
    "Q": "Qualifying", "SQ": "Sprint Qualifying", "S": "Sprint", "R": "Race",
}

_token: str | None = None
_token_expires_at = 0.0


def _get_token() -> str:
    """Holt einen Zugangstoken und verwendet ihn wieder, bis er fast abläuft."""
    global _token, _token_expires_at
    if _token and time.time() < _token_expires_at:
        return _token

    load_dotenv(REPO / ".env")
    username = os.getenv("OPENF1_USERNAME")
    password = os.getenv("OPENF1_PASSWORD")
    if not username or not password:
        raise RuntimeError("OPENF1_USERNAME / OPENF1_PASSWORD fehlen in der .env")

    r = requests.post(TOKEN_URL, data={"username": username, "password": password}, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"OpenF1-Anmeldung fehlgeschlagen ({r.status_code}): {r.text[:200]}")
    payload = r.json()
    _token = payload["access_token"]
    # 60 s Sicherheitsabstand, damit der Token nicht mitten in einer Anfrage abläuft
    _token_expires_at = time.time() + float(payload.get("expires_in", 3600)) - 60
    return _token


def fetch(endpoint: str, params: dict) -> list[dict]:
    """Eine Anfrage an OpenF1, mit Wiederholung bei Rate-Limit (429)."""
    for attempt in range(5):
        r = requests.get(
            f"{BASE_URL}/{endpoint}",
            params=params,
            headers={"Authorization": f"Bearer {_get_token()}"},
            timeout=120,
        )
        if r.status_code == 429:
            time.sleep(2 * (attempt + 1))
            continue
        if r.status_code == 404:
            return []
        r.raise_for_status()
        return r.json()
    raise RuntimeError(f"OpenF1 Rate-Limit bei {endpoint} – später erneut versuchen")


def cached_fetch(endpoint: str, session_key: int, refresh: bool = False) -> list[dict]:
    """Wie fetch(), aber mit lokaler Kopie unter data/cache/<session_key>/."""
    path = CACHE_DIR / str(session_key) / f"{endpoint}.json"
    if path.exists() and not refresh:
        return json.loads(path.read_text(encoding="utf-8"))
    data = fetch(endpoint, {"session_key": session_key})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return data


def _cached_list(path: Path, endpoint: str, params: dict, refresh: bool) -> list[dict]:
    """Liste von OpenF1 holen und lokal merken. Ohne Netz: die gemerkte Liste."""
    if path.exists() and not refresh:
        return json.loads(path.read_text(encoding="utf-8"))
    try:
        data = fetch(endpoint, params)
    except (requests.RequestException, RuntimeError):
        if path.exists():
            print(f"ℹ OpenF1 nicht erreichbar – nutze gemerkte Liste {path.name}")
            return json.loads(path.read_text(encoding="utf-8"))
        raise
    if data:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")
    return data


def sessions_of(meeting_key: int, refresh: bool = False) -> list[dict]:
    """Alle Sessions eines Wochenendes (gemerkt unter data/cache/meetings/)."""
    return _cached_list(CACHE_DIR / "meetings" / f"{meeting_key}_sessions.json",
                        "sessions", {"meeting_key": meeting_key}, refresh)


def find_session_key(meeting_key: int, session_type: str, refresh: bool = False) -> int:
    """meeting_key (ganzes Wochenende) + Session-Typ → session_key (eine Session)."""
    name = SESSION_NAMES.get(session_type)
    if not name:
        raise ValueError(f"Unbekannter Session-Typ '{session_type}'. Erlaubt: {', '.join(SESSION_NAMES)}")
    sessions = sessions_of(meeting_key, refresh)
    match = next((s for s in sessions if s.get("session_name") == name), None)
    if not match and not refresh:
        # Liste wurde gemerkt, bevor es die Session gab (z. B. am Freitag) → neu laden
        sessions = sessions_of(meeting_key, refresh=True)
        match = next((s for s in sessions if s.get("session_name") == name), None)
    if not match:
        available = [s.get("session_name") for s in sessions]
        raise ValueError(f"'{name}' gibt es bei Meeting {meeting_key} nicht. Verfügbar: {available}")
    return match["session_key"]


# Felder, in denen nach dem Suchbegriff gesucht wird. Ort und Strecke sind nötig:
# 2026 heißt das Rennen in Sepang (Malaysia) offiziell „Bahrain Grand Prix“.
MEETING_FIELDS = ("meeting_name", "meeting_official_name", "location", "country_name", "circuit_short_name")


def match_meetings(meetings: list[dict], query: str, now=None) -> list[dict]:
    """Passende Wochenenden, das zeitlich nächstliegende zuerst.

    query: Teil von Name, Ort, Land oder Strecke (ohne Groß-/Kleinschreibung),
           eine meeting_key als Zahl oder "latest" (das letzte begonnene).
    """
    from datetime import datetime, timezone
    now = now or datetime.now(timezone.utc)

    def start(m):
        try:
            return datetime.fromisoformat(str(m.get("date_start")).replace("Z", "+00:00"))
        except ValueError:
            return None
    q = str(query).strip().lower()
    if q.isdigit():
        return [m for m in meetings if str(m.get("meeting_key")) == q]
    if q == "latest":
        begun = [m for m in meetings if start(m) and start(m) <= now]
        return sorted(begun, key=start, reverse=True)[:1]
    hits = [m for m in meetings if any(q in str(m.get(f) or "").lower() for f in MEETING_FIELDS)]
    return sorted(hits, key=lambda m: abs((start(m) - now).total_seconds()) if start(m) else float("inf"))


def find_meeting(query: str, year: int, refresh: bool = False) -> dict:
    """Ein Wochenende per Suchbegriff (siehe match_meetings)."""
    path = CACHE_DIR / "meetings" / f"{year}.json"
    meetings = _cached_list(path, "meetings", {"year": year}, refresh)
    hits = match_meetings(meetings, query)
    if (not hits or str(query).lower() == "latest") and not refresh:
        try:   # gemerkte Liste evtl. veraltet (neues Wochenende) → einmal neu laden
            meetings = _cached_list(path, "meetings", {"year": year}, True)
            hits = match_meetings(meetings, query)
        except (requests.RequestException, RuntimeError):
            pass
    if not hits:
        names = sorted({m.get("location") or m.get("meeting_name") for m in meetings})
        raise ValueError(f"Kein Wochenende {year} passt zu '{query}'. Bekannt: {', '.join(map(str, names))}")
    return hits[0]


def cached_fetch_driver(endpoint: str, session_key: int, driver_number: int,
                        refresh: bool = False) -> list[dict]:
    """Wie cached_fetch(), aber nur für einen Fahrer – für große Endpunkte wie
    car_data (Telemetrie), die für alle Fahrer zusammen zu groß wären.
    Cache: data/cache/<session_key>/<endpoint>_<Startnummer>.json
    """
    path = CACHE_DIR / str(session_key) / f"{endpoint}_{driver_number}.json"
    if path.exists() and not refresh:
        return json.loads(path.read_text(encoding="utf-8"))
    data = fetch(endpoint, {"session_key": session_key, "driver_number": driver_number})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return data
