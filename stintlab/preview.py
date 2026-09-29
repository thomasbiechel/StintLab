"""Race Preview (Donnerstag-Post): Daten für die vier Preview-Slides.

Was hier zusammenkommt:
- Strecke: Layout mit Kurvennummern von MultiViewer (circuit_info_url aus
  OpenF1, gemerkt unter data/cache/circuits/). Ohne Netz/ohne Eintrag: die
  Siegerrunde der letzten Ausgabe aus den OpenF1-Positionsdaten, ohne Kurven.
  Das offizielle Streckenbild (circuit_image) wird bewusst NICHT benutzt –
  das ist eine Grafik von formula1.com.
- Letzte Ausgabe auf derselben Strecke (gleiche circuit_key, bis 2023 zurück):
  Sieger, schnellste Rennrunde, Pole, Rundenzahl, Teampace im Rennen.
- Wetter Fr–So: Vorhersage von Open-Meteo (kostenlos, ohne Schlüssel) für die
  Koordinaten der Strecke, dazu die Regenwahrscheinlichkeit zur Startzeit der
  wichtigsten Session des Tages. Ohne Netz: letzte gemerkte Vorhersage.
- Form: Teampace (Median der sauberen Rennrunden, Abstand zum schnellsten Team
  in %) der letzten drei Rennen, das neueste zählt am meisten (Gewichte 1-2-3).
- Chancen: 75 % Form + 25 % Pace der Teams bei der letzten Ausgabe hier.
  Die Strecke zählt wenig, weil sich 2026 das Reglement komplett geändert hat.
  Das ist eine EINSCHÄTZUNG aus Daten, keine Vorhersage – steht so auf der Slide.

Prozent statt Sekunden: nur so sind Rennen mit 1:13- und 1:45-Runden vergleichbar.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import median

from stintlab import openf1

FORM_RACES = 3
FORM_WEIGHTS = (1, 2, 3)          # älteste → neueste
TRACK_WEIGHT = 0.25
MIN_TEAM_LAPS = 10
FIRST_YEAR = 2023                 # ab hier hat OpenF1 Daten
# Abstand zum besten Chancen-Wert (in %), bis zu dem eine Stufe reicht
TIERS = ((0.5, "FAVOURITES"), (1.5, "IN THE MIX"), (float("inf"), "OUTSIDERS"))

# Alte Teamnamen → heutige (für die Vorjahres-Pace)
TEAM_ALIAS = {"Kick Sauber": "Audi", "Sauber": "Audi", "Alfa Romeo": "Audi", "RB": "Racing Bulls",
              "AlphaTauri": "Racing Bulls", "Haas": "Haas F1 Team"}

# Streckenkoordinaten (Start/Ziel ungefähr) nach circuit_key – für die Wettervorhersage
CIRCUIT_COORDS = {
    2: (52.0786, -1.0169),     # Silverstone
    4: (47.5789, 19.2486),     # Hungaroring
    6: (44.3439, 11.7167),     # Imola
    7: (50.4372, 5.9714),      # Spa
    9: (30.1328, -97.6411),    # Austin
    10: (-37.8497, 144.9680),  # Melbourne
    12: (2.7608, 101.7382),    # Sepang / Kuala Lumpur
    14: (-23.7036, -46.6997),  # Interlagos
    15: (41.5700, 2.2611),     # Barcelona
    19: (47.2197, 14.7647),    # Spielberg
    22: (43.7347, 7.4206),     # Monaco
    23: (45.5000, -73.5228),   # Montreal
    39: (45.6156, 9.2811),     # Monza
    46: (34.8431, 136.5407),   # Suzuka
    49: (31.3389, 121.2197),   # Shanghai
    55: (52.3888, 4.5409),     # Zandvoort
    61: (1.2914, 103.8640),    # Singapur
    63: (26.0325, 50.5106),    # Sakhir
    65: (19.4042, -99.0907),   # Mexiko-Stadt
    70: (24.4672, 54.6031),    # Yas Marina
    144: (40.3725, 49.8533),   # Baku
    149: (21.6319, 39.1044),   # Jeddah
    150: (25.4900, 51.4542),   # Lusail
    151: (25.9581, -80.2389),  # Miami
    152: (36.1147, -115.1728), # Las Vegas
    153: (40.4650, -3.6150),   # Madring
}

SESSION_SHORT = {"Practice 1": "FP1", "Practice 2": "FP2", "Practice 3": "FP3", "Qualifying": "QUALI",
                 "Sprint Qualifying": "SPRINT QUALI", "Sprint Shootout": "SPRINT QUALI",
                 "Sprint": "SPRINT", "Race": "RACE"}
KEY_SESSIONS = ("RACE", "QUALI", "SPRINT", "SPRINT QUALI", "FP3", "FP2", "FP1")


# ------------------------------------------------------------------ Helfer
def _year(m: dict) -> int:
    return int(m.get("year") or str(m.get("date_start", ""))[:4])


def _start(m: dict) -> datetime | None:
    try:
        return datetime.fromisoformat(str(m.get("date_start")).replace("Z", "+00:00"))
    except ValueError:
        return None


def _offset(m: dict) -> timedelta:
    """gmt_offset "08:00:00" / "-04:00:00" → timedelta."""
    raw = str(m.get("gmt_offset") or "00:00:00")
    sign = -1 if raw.startswith("-") else 1
    h, mi, *_ = (int(x) for x in raw.lstrip("+-").split(":"))
    return sign * timedelta(hours=h, minutes=mi)


def _is_race_weekend(m: dict) -> bool:
    return not m.get("is_cancelled") and "testing" not in str(m.get("meeting_name", "")).lower()


def team_name(team: str | None) -> str | None:
    return TEAM_ALIAS.get(team, team) if team else team


def team_pace_pct(data: dict, min_laps: int = MIN_TEAM_LAPS) -> dict[str, float]:
    """{Team: Abstand des Median der sauberen Rennrunden zum schnellsten Team, in %}."""
    from stintlab.analyses.race_pace import clean_laps
    clean, _ = clean_laps(data)
    by_team: dict[str, list[float]] = {}
    for drv, times in clean.items():
        by_team.setdefault(team_name(data.get("teams", {}).get(drv)) or drv, []).extend(times)
    med = {t: median(v) for t, v in by_team.items() if len(v) >= min_laps}
    if not med:
        return {}
    best = min(med.values())
    return {t: (m / best - 1) * 100 for t, m in med.items()}


# ------------------------------------------------------------------ Form + Chancen
def recent_races(meeting: dict, n: int = FORM_RACES, refresh: bool = False,
                 load=None) -> list[dict]:
    """Die letzten n gefahrenen Rennen VOR diesem Wochenende (gleiches Jahr),
    älteste zuerst: [{"meeting_key", "place", "pace": {Team: %}}]."""
    from stintlab.session import load_session
    load = load or load_session
    begin = _start(meeting)
    past = [m for m in openf1.meetings_of(_year(meeting), refresh)
            if _is_race_weekend(m) and _start(m) and begin and _start(m) < begin]
    out = []
    for m in sorted(past, key=_start, reverse=True):
        try:
            pace = team_pace_pct(load(m["meeting_key"], "R", refresh=refresh))
        except Exception as exc:                        # abgesagt, keine Daten, kein Netz
            print(f"  ℹ Rennen {m.get('location')} übersprungen: {exc}")
            continue
        if pace:
            out.append({"meeting_key": m["meeting_key"], "place": m.get("location") or m.get("circuit_short_name"),
                        "pace": pace})
        if len(out) == n:
            break
    return out[::-1]


def form_table(races: list[dict], weights=FORM_WEIGHTS) -> dict[str, float]:
    """Gewichteter Mittelwert der %-Abstände; neuestes Rennen = letztes Gewicht.
    Fehlt ein Team in einem Rennen, zählen nur seine übrigen Rennen."""
    w = list(weights)[-len(races):] if races else []
    acc: dict[str, list[float]] = {}
    for weight, race in zip(w, races):
        for team, pct in race["pace"].items():
            s = acc.setdefault(team, [0.0, 0.0])
            s[0] += weight * pct
            s[1] += weight
    return {t: s / ws for t, (s, ws) in acc.items() if ws}


def chances(form: dict[str, float], track: dict[str, float] | None,
            races: list[dict] | None = None, track_weight: float = TRACK_WEIGHT) -> list[dict]:
    """Rangliste: [{"team", "score", "form", "track", "tier", "trend"}], beste zuerst.
    trend: +1 besser geworden (neuestes Rennen deutlich besser als ältestes), -1 schlechter, 0 gleich."""
    rows = []
    for team, f in form.items():
        t = (track or {}).get(team)
        score = f if t is None else (1 - track_weight) * f + track_weight * t
        trend = 0
        seen = [r["pace"][team] for r in races or [] if team in r["pace"]]
        if len(seen) >= 2 and abs(seen[-1] - seen[0]) >= 0.3:
            trend = 1 if seen[-1] < seen[0] else -1
        rows.append({"team": team, "score": score, "form": f, "track": t, "trend": trend})
    rows.sort(key=lambda r: r["score"])
    if rows:
        best = rows[0]["score"]
        for r in rows:
            r["tier"] = next(name for limit, name in TIERS if r["score"] - best <= limit)
    return rows


# ------------------------------------------------------------------ Letzte Ausgabe
def last_edition(meeting: dict, refresh: bool = False) -> dict | None:
    """Das letzte Wochenende auf derselben Strecke (bis FIRST_YEAR zurück)."""
    for year in range(_year(meeting) - 1, FIRST_YEAR - 1, -1):
        try:
            ms = openf1.meetings_of(year, refresh)
        except Exception:
            continue
        hits = [m for m in ms if m.get("circuit_key") == meeting.get("circuit_key") and _is_race_weekend(m)]
        if hits:
            return max(hits, key=lambda m: _start(m) or datetime.min.replace(tzinfo=timezone.utc))
    return None


def _fmt_lap(sec: float) -> str:
    m, s = divmod(float(sec), 60)
    return f"{int(m)}:{s:06.3f}"


def history(prev: dict, refresh: bool = False, load=None) -> dict:
    """Sieger, schnellste Rennrunde, Pole und Teampace der Ausgabe `prev`."""
    from stintlab.session import load_session
    load = load or load_session
    out = {"year": _year(prev), "meeting_key": prev["meeting_key"], "place": prev.get("location")}
    race = load(prev["meeting_key"], "R", refresh=refresh)
    teams = race.get("teams", {})
    rows = sorted((r for r in race.get("results", []) if r.get("position")), key=lambda r: r["position"])
    if rows:
        out["winner"] = rows[0]["driver"]
        out["winner_team"] = teams.get(rows[0]["driver"])
    laps = [l for l in race.get("laps", []) if l.get("LapTime")]
    if laps:
        best = min(laps, key=lambda l: float(l["LapTime"]))
        out["fastest"] = {"driver": best["Driver"], "team": teams.get(best["Driver"]),
                          "time": float(best["LapTime"]), "text": _fmt_lap(best["LapTime"]),
                          "lap": best.get("LapNumber")}
        out["laps"] = max(int(l.get("LapNumber") or 0) for l in race.get("laps", []))
    out["track_pace"] = team_pace_pct(race)
    out["_race"] = race
    try:
        q = load(prev["meeting_key"], "Q", refresh=refresh)
        p1 = next((r for r in q.get("results", []) if r.get("position") == 1), None)
        if p1:
            out["pole"] = p1["driver"]
            out["pole_team"] = q.get("teams", {}).get(p1["driver"])
    except Exception:
        pass
    return out


# ------------------------------------------------------------------ Ältere Ausgaben (vor 2023): Jolpica-F1
# OpenF1 hat erst ab 2023 Daten. Für Strecken, die länger nicht im Kalender waren
# (Sepang zuletzt 2017), kommen Sieger, Pole und schnellste Runde aus Jolpica-F1,
# dem Nachfolger der Ergast-API (frei, ohne Schlüssel). Nur Ergebnisse – keine
# Teampace: ein Rennen von vor zwei Reglement-Generationen sagt nichts über 2026.
JOLPICA = "https://api.jolpi.ca/ergast/f1"
JOLPICA_DIR = openf1.CACHE_DIR / "jolpica"
ERGAST_CIRCUIT = {
    2: "silverstone", 4: "hungaroring", 6: "imola", 7: "spa", 9: "americas", 10: "albert_park", 12: "sepang",
    14: "interlagos", 15: "catalunya", 19: "red_bull_ring", 22: "monaco", 23: "villeneuve", 39: "monza",
    46: "suzuka", 49: "shanghai", 55: "zandvoort", 61: "marina_bay", 63: "bahrain", 65: "rodriguez",
    70: "yas_marina", 144: "baku", 149: "jeddah", 150: "losail", 151: "miami", 152: "vegas", 153: "madring",
}
# Alte Konstrukteursnamen → heutiges Team (nur für die Farbe der Kachel)
ERGAST_TEAM = {"Red Bull": "Red Bull Racing", "Toro Rosso": "Racing Bulls", "AlphaTauri": "Racing Bulls",
               "Force India": "Aston Martin", "Racing Point": "Aston Martin", "Renault": "Alpine",
               "Haas F1 Team": "Haas F1 Team", "Sauber": "Audi", "Alfa Romeo": "Audi"}


def _jolpica(path: str, refresh: bool = False, get=None) -> dict | None:
    """GET {JOLPICA}/{path} – gemerkt (alte Ergebnisse ändern sich nicht), ohne Netz aus dem Cache."""
    cache = JOLPICA_DIR / (path.replace("/", "_") + ".json")
    if cache.exists() and not refresh:
        return json.loads(cache.read_text(encoding="utf-8"))
    try:
        if get is None:
            import requests
            r = requests.get(f"{JOLPICA}/{path}.json", params={"limit": 100}, timeout=30)
            r.raise_for_status()
            raw = r.json()
        else:
            raw = get(path)
    except Exception as exc:
        print(f"  ℹ Jolpica-F1 nicht erreichbar ({type(exc).__name__})")
        return json.loads(cache.read_text(encoding="utf-8")) if cache.exists() else None
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(raw), encoding="utf-8")
    return raw


def _races(raw: dict | None) -> list[dict]:
    return ((raw or {}).get("MRData", {}).get("RaceTable", {}).get("Races")) or []


def jolpica_history(meeting: dict, refresh: bool = False, get=None) -> dict | None:
    """Letztes Rennen auf der Strecke vor diesem Jahr aus Jolpica-F1 – im selben Format wie history()."""
    cid = ERGAST_CIRCUIT.get(meeting.get("circuit_key"))
    if not cid:
        return None
    wins = [r for r in _races(_jolpica(f"circuits/{cid}/results/1", refresh, get))
            if int(r.get("season", 0)) < _year(meeting)]
    if not wins:
        return None
    last = max(wins, key=lambda r: (int(r["season"]), int(r["round"])))
    season, rnd = int(last["season"]), int(last["round"])
    out = {"year": season, "place": last.get("Circuit", {}).get("circuitName"), "source": "jolpica",
           "track_pace": {}}

    def who(res):
        drv = res.get("Driver", {})
        team = res.get("Constructor", {}).get("name")
        return drv.get("code") or drv.get("familyName", "?")[:3].upper(), ERGAST_TEAM.get(team, team)

    full = _races(_jolpica(f"{season}/{rnd}/results", refresh, get))
    results = full[0]["Results"] if full else last.get("Results", [])
    if results:
        out["winner"], out["winner_team"] = who(results[0])
        out["laps"] = int(results[0].get("laps") or 0) or None
    fl = [r for r in results if str(r.get("FastestLap", {}).get("rank")) == "1"]
    if fl:
        f = fl[0]["FastestLap"]
        d, t = who(fl[0])
        text = f.get("Time", {}).get("time")
        mm, ss = text.split(":") if text and ":" in text else ("0", text or "0")
        out["fastest"] = {"driver": d, "team": t, "text": text, "lap": int(f.get("lap") or 0) or None,
                          "time": int(mm) * 60 + float(ss)}
    q = _races(_jolpica(f"{season}/{rnd}/qualifying/1", refresh, get))
    if q and q[0].get("QualifyingResults"):
        out["pole"], out["pole_team"] = who(q[0]["QualifyingResults"][0])
    return out


# ------------------------------------------------------------------ Streckenlayout
CIRCUITS_DIR = openf1.CACHE_DIR / "circuits"


def _multiviewer(circuit_key: int, year: int, refresh: bool = False) -> dict | None:
    """Rohdaten von MultiViewer (x, y, corners, rotation) – gemerkt, ohne Netz aus dem Cache."""
    import requests
    path = CIRCUITS_DIR / f"{circuit_key}_{year}.json"
    if path.exists() and not refresh:
        return json.loads(path.read_text(encoding="utf-8"))
    try:
        r = requests.get(f"https://api.multiviewer.app/api/v1/circuits/{circuit_key}/{year}",
                         headers={"User-Agent": "StintLab"}, timeout=30)
        if r.status_code != 200:
            raise RuntimeError(r.status_code)
        raw = r.json()
    except Exception:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    if not raw.get("x"):
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(raw), encoding="utf-8")
    return raw


def layout_from_multiviewer(raw: dict) -> dict:
    """Um `rotation` gedreht wie die offizielle Streckenkarte."""
    import numpy as np
    ang = np.radians(float(raw.get("rotation") or 0))
    rot = np.array([[np.cos(ang), -np.sin(ang)], [np.sin(ang), np.cos(ang)]])
    xy = np.column_stack([raw["x"], raw["y"]]).astype(float) @ rot.T
    # Kurvennummer neben die Strecke: in Richtung `angle` versetzt (wie im FastF1-Beispiel)
    off = 0.045 * float(np.ptp(np.asarray(raw["x"], float)) or 1)
    corners = []
    for c in raw.get("corners", []):
        tp = c.get("trackPosition") or {}
        if "x" in tp and "y" in tp:
            p = np.array([tp["x"], tp["y"]], dtype=float)
            a = np.radians(float(c.get("angle") or 0))
            lp = p + off * np.array([np.cos(a), np.sin(a)])
            (cx, cy), (lx, ly) = p @ rot.T, lp @ rot.T
            corners.append({"number": f"{c.get('number')}{c.get('letter') or ''}", "x": float(cx), "y": float(cy),
                            "lx": float(lx), "ly": float(ly)})
    return {"x": xy[:, 0].tolist(), "y": xy[:, 1].tolist(), "corners": corners, "source": "multiviewer"}


def layout_from_race(race: dict, driver: str, refresh: bool = False) -> dict | None:
    """Schnellste Runde von `driver` aus den Positionsdaten (ohne Kurvennummern)."""
    num = race.get("numbers", {}).get(driver)
    laps = [l for l in race.get("laps", []) if l["Driver"] == driver and l.get("LapTime") and l.get("LapStart")]
    if not num or not laps:
        return None
    best = min(laps, key=lambda l: float(l["LapTime"]))
    start = best["LapStart"]
    end = start + timedelta(seconds=float(best["LapTime"]))
    loc = openf1.cached_fetch_driver("location", race["session_key"], int(num), refresh)
    pts = []
    for p in loc:
        try:
            t = datetime.fromisoformat(str(p["date"]).replace("Z", "+00:00"))
        except (KeyError, ValueError):
            continue
        if start <= t <= end and (p.get("x"), p.get("y")) != (0, 0):
            pts.append((p["x"], p["y"]))
    if len(pts) < 50:
        return None
    return {"x": [p[0] for p in pts], "y": [p[1] for p in pts], "corners": [], "source": "openf1"}


# Streckenverlauf als GeoJSON (github.com/bacinger/f1-circuits, MIT-Lizenz) – für Strecken,
# die MultiViewer (noch) nicht hat, z. B. Sepang vor dem ersten Rennen 2026. Ohne Kurvennummern
# und ohne Fahrtrichtung, dafür mit Streckenlänge.
GEO_URL = "https://raw.githubusercontent.com/bacinger/f1-circuits/master/circuits/{}.geojson"
GEO_ID = {
    2: "gb-1948", 4: "hu-1986", 6: "it-1953", 7: "be-1925", 9: "us-2012", 10: "au-1953", 12: "my-1999",
    14: "br-1940", 15: "es-1991", 19: "at-1969", 22: "mc-1929", 23: "ca-1978", 39: "it-1922", 46: "jp-1962",
    49: "cn-2004", 55: "nl-1948", 61: "sg-2008", 63: "bh-2002", 65: "mx-1962", 70: "ae-2009", 144: "az-2016",
    149: "sa-2021", 150: "qa-2004", 151: "us-2022", 152: "us-2023", 153: "es-2026",
}


def _geojson(circuit_key: int, refresh: bool = False, get=None) -> dict | None:
    gid = GEO_ID.get(circuit_key)
    if not gid:
        return None
    path = CIRCUITS_DIR / f"geo_{gid}.json"
    if path.exists() and not refresh:
        return json.loads(path.read_text(encoding="utf-8"))
    try:
        if get is None:
            import requests
            r = requests.get(GEO_URL.format(gid), timeout=30)
            r.raise_for_status()
            raw = r.json()
        else:
            raw = get(gid)
    except Exception:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(raw), encoding="utf-8")
    return raw


def layout_from_geojson(raw: dict) -> dict | None:
    """Längen-/Breitengrade → Meter (Norden oben), Länge aus den Eigenschaften."""
    import numpy as np
    feats = [f for f in raw.get("features", []) if f.get("geometry", {}).get("type") == "LineString"]
    if not feats:
        return None
    lon, lat = np.asarray(feats[0]["geometry"]["coordinates"], float).T[:2]
    x = (lon - lon.mean()) * 111_320 * np.cos(np.radians(lat.mean()))
    y = (lat - lat.mean()) * 110_540
    return {"x": x.tolist(), "y": y.tolist(), "corners": [], "source": "geojson",
            "length_m": feats[0].get("properties", {}).get("length")}


def track_layout(meeting: dict, hist: dict | None, refresh: bool = False) -> dict | None:
    year = _year(meeting)
    for y in (year, year - 1):
        raw = _multiviewer(meeting.get("circuit_key"), y, refresh)
        if raw:
            return layout_from_multiviewer(raw)
    geo = _geojson(meeting.get("circuit_key"), refresh)
    if geo:
        lay = layout_from_geojson(geo)
        if lay:
            return lay
    if hist and hist.get("_race") and hist.get("winner"):
        try:
            return layout_from_race(hist["_race"], hist["winner"], refresh)
        except Exception as exc:
            print(f"  ℹ Streckenlayout aus Positionsdaten nicht möglich: {exc}")
    return None


# ------------------------------------------------------------------ Wetter
WEATHER_DIR = openf1.CACHE_DIR / "weather"


def weekend_days(meeting: dict, sessions: list[dict]) -> list[dict]:
    """Ortstage des Wochenendes mit ihren Sessions: [{"date", "sessions": [(Kürzel, Ortszeit)]}]."""
    off = _offset(meeting)
    start = _start(meeting)
    try:
        end = datetime.fromisoformat(str(meeting.get("date_end")).replace("Z", "+00:00"))
    except ValueError:
        end = start + timedelta(days=2)
    d0, d1 = (start + off).date(), (end + off).date()
    days = [{"date": d0 + timedelta(days=i), "sessions": []} for i in range((d1 - d0).days + 1)]
    for s in sessions:
        try:
            t = datetime.fromisoformat(str(s.get("date_start")).replace("Z", "+00:00")) + off
        except ValueError:
            continue
        for day in days:
            if day["date"] == t.date():
                day["sessions"].append((SESSION_SHORT.get(s.get("session_name"), s.get("session_name")),
                                        t.replace(tzinfo=None)))
    return days


def _fetch_forecast(lat: float, lon: float, d0: date, d1: date) -> dict:
    import requests
    r = requests.get("https://api.open-meteo.com/v1/forecast", timeout=30, params={
        "latitude": lat, "longitude": lon, "timezone": "auto",
        "start_date": d0.isoformat(), "end_date": d1.isoformat(),
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,precipitation_sum,"
                 "wind_speed_10m_max",
        "hourly": "temperature_2m,precipitation_probability"})
    r.raise_for_status()
    return r.json()


def forecast(meeting: dict, days: list[dict], refresh: bool = True, fetch=_fetch_forecast) -> dict | None:
    """Vorhersage je Tag. Holt immer neu (Vorhersagen ändern sich); ohne Netz die gemerkte."""
    coords = CIRCUIT_COORDS.get(meeting.get("circuit_key"))
    if not coords or not days:
        return None
    path = WEATHER_DIR / f"{meeting['meeting_key']}.json"
    raw = None
    if refresh or not path.exists():
        try:
            raw = fetch(*coords, days[0]["date"], days[-1]["date"])
            raw["_fetched"] = datetime.now(timezone.utc).isoformat()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(raw), encoding="utf-8")
        except Exception as exc:
            print(f"  ℹ Wettervorhersage nicht erreichbar ({type(exc).__name__})" + (" – nutze gemerkte" if path.exists() else ""))
    if raw is None and path.exists():
        raw = json.loads(path.read_text(encoding="utf-8"))
    if not raw or "daily" not in raw:
        return None
    return parse_forecast(raw, days)


def parse_forecast(raw: dict, days: list[dict]) -> dict:
    daily, hourly = raw["daily"], raw.get("hourly", {})
    idx = {d: i for i, d in enumerate(daily.get("time", []))}
    hidx = {t: i for i, t in enumerate(hourly.get("time", []))}

    def pick(key, i):
        vals = daily.get(key) or []
        return vals[i] if i < len(vals) else None

    out = []
    for day in days:
        i = idx.get(day["date"].isoformat())
        if i is None:
            continue
        row = {"date": day["date"], "sessions": [s for s, _ in day["sessions"]],
               "tmax": pick("temperature_2m_max", i), "tmin": pick("temperature_2m_min", i),
               "rain_pct": pick("precipitation_probability_max", i), "rain_mm": pick("precipitation_sum", i),
               "wind": pick("wind_speed_10m_max", i), "code": pick("weather_code", i)}
        # Hauptsession des Tages (Rennen > Quali > …) und das Wetter zu ihrer Startzeit
        main = sorted(day["sessions"], key=lambda s: KEY_SESSIONS.index(s[0]) if s[0] in KEY_SESSIONS else 99)
        if main:
            name, t = main[0]
            h = hidx.get(t.replace(minute=0, second=0).strftime("%Y-%m-%dT%H:00"))
            row["key"] = {"session": name, "time": t.strftime("%H:%M"),
                          "rain_pct": hourly["precipitation_probability"][h] if h is not None else None,
                          "temp": hourly["temperature_2m"][h] if h is not None else None}
        out.append(row)
    return {"days": out, "fetched": raw.get("_fetched")}


# ------------------------------------------------------------------ Alles zusammen
def build_preview(meeting_key: int, refresh: bool = False) -> dict:
    """Alle Daten der Preview-Slides (wird einmal geladen, alle vier Slides nutzen es)."""
    meeting = openf1.meeting_by_key(meeting_key)
    if not meeting:
        raise ValueError(f"Wochenende {meeting_key} nicht in den gemerkten Jahreslisten – "
                         f"einmal python weekend.py/preview.py mit Netz aufrufen")
    out = {"session_type": "PREVIEW", "meeting": meeting, "meeting_key": meeting_key, "weights": FORM_WEIGHTS}

    prev = last_edition(meeting, refresh)
    hist = None
    if prev:
        try:
            hist = history(prev, refresh)
        except Exception as exc:
            print(f"  ⚠ Letzte Ausgabe ({prev.get('location')} {_year(prev)}) nicht ladbar: {exc}")
    if hist is None:                     # vor 2023 zuletzt hier (z. B. Sepang 2017)
        hist = jolpica_history(meeting, refresh)
    out["history"] = hist
    out["layout"] = track_layout(meeting, hist, refresh)

    try:
        sessions = openf1.sessions_of(meeting_key, refresh)
    except Exception:
        sessions = []
    out["weather"] = forecast(meeting, weekend_days(meeting, sessions))

    races = recent_races(meeting, refresh=refresh)
    out["races"] = races
    out["form"] = form_table(races)
    out["chances"] = chances(out["form"], (hist or {}).get("track_pace"), races)
    if hist:
        hist.pop("_race", None)
    return out
