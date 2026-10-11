"""Verkehr auf einer Runde: welche Autos fuhren wie dicht VOR einem Fahrer?

FRAGE (Kuala Lumpur 2026 Q): Hatte Antonelli Windschatten, als er nur 305 km/h
an der Speed Trap fuhr? TV: er war in Q2/Q3 allein – die Daten sollen das zeigen.

METHODE, für jede Runde des Fahrers alle STEP_S Sekunden:
1. Bahn der Runde aus seinen eigenen Positionen (x/y, ~4 Hz) mit Streckenmeter.
2. Jedes andere Auto zur selben Uhrzeit auf diese Bahn projizieren
   (nächster Bahnpunkt) → Meter vor ihm auf der Strecke.
3. Zeitabstand = Meter / sein Tempo an der Stelle.

RAUS (sonst Scheintreffer):
- Boxengasse: Autos unter MIN_SPEED_KMH. Kuala Lumpur: die Box liegt direkt
  neben der Start-Ziel-Geraden; stehende Autos lagen „2 m vor ihm“, mehrere
  gleichzeitig. Ein Auto auf der Strecke ist auf einer schnellen Runde nie so
  langsam; wer langsam vor ihm herfährt (Abkühlrunde), wird damit auch
  ausgefiltert – für Windschatten zählt so ein Auto ohnehin nicht.
- Langsamere Autos (unter SAME_PACE × sein Tempo): wer gerade überholt wird
  (Abkühlrunde, Aufwärmrunde), liegt kurz „1 m vor ihm“, gibt aber keinen
  Windschatten. Kuala Lumpur Q1: ANT an BOT, BOR, ALB vorbei.
- Weiter als MAX_OFF_M neben der Bahn (Notausgang, Datenfehler).
- Lücken in den Positionsdaten des anderen Autos > MAX_HOLE_S.

WINDSCHATTEN: spürbar etwa unter 1 s Abstand (TOW_S), stark unter ~0,5 s.
"""

from __future__ import annotations

import numpy as np

from stintlab.session import _parse

STEP_S = 0.25
WINDOW_M = 400.0
MIN_SPEED_KMH = 80.0
MAX_OFF_M = 25.0
MAX_HOLE_S = 1.0
TOW_S = 1.0
SAME_PACE = 0.9       # Auto davor muss mind. 90 % seines Tempos fahren
UNITS_PER_M = 10.0    # OpenF1 x/y ≈ Dezimeter (Kuala Lumpur gemessen: 9,87) – nur für Meterangaben
                      # und Filter; der Zeitabstand ist davon unabhängig (Meter / eigenes Tempo)


def samples(location: list[dict]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """/location → (Unix-Zeit, x, y), sortiert, ohne doppelte Zeitstempel."""
    pts = sorted((_parse(p["date"]).timestamp(), float(p["x"]), float(p["y"])) for p in location
                 if p.get("date") and p.get("x") is not None and p.get("y") is not None)
    if not pts:
        return np.array([]), np.array([]), np.array([])
    a = np.array(pts)
    keep = np.concatenate([[True], np.diff(a[:, 0]) > 0])
    a = a[keep]
    return a[:, 0], a[:, 1], a[:, 2]


def cars_ahead(t0: float, lap_time: float, path: tuple[np.ndarray, np.ndarray, np.ndarray],
               others: dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]], length_m: float | None = None,
               window_m: float = WINDOW_M, step_s: float = STEP_S) -> list[dict]:
    """Alle Momente, in denen ein anderes Auto bis window_m vor dem Fahrer war.

    t0: Unix-Zeit des Rundenbeginns; path: (Zeit ab t0, x, y) des Fahrers in der Runde;
    others: {Fahrer: (Unix-Zeit, x, y)}; length_m: Rundenlänge in Metern (Maßstab),
    ohne Angabe UNITS_PER_M – braucht dann keine Telemetrie (car_data).
    Ergebnis: [{"driver", "t", "km", "gap_m", "gap_s"}], t = Sekunde der Runde.
    """
    pt, px, py = path
    s = np.concatenate([[0.0], np.cumsum(np.hypot(np.diff(px), np.diff(py)))])
    per_m = s[-1] / length_m if length_m else UNITS_PER_M
    tt = np.arange(0.0, lap_time, step_s)
    sa = np.interp(tt, pt, s)
    va = np.gradient(sa, tt) / per_m                                   # m/s
    events = []
    for drv, (ot, ox, oy) in others.items():
        if len(ot) < 2:
            continue
        ta = t0 + tt
        ok = (ta > ot[0]) & (ta < ot[-1])
        if not ok.any():
            continue
        idx = np.clip(np.searchsorted(ot, ta), 1, len(ot) - 1)
        hole = (ot[idx] - ot[idx - 1]) > MAX_HOLE_S
        qx, qy = np.interp(ta, ot, ox), np.interp(ta, ot, oy)
        # Tempo des anderen Autos über ±0,5 s
        ax_, ay_ = np.interp(ta - 0.5, ot, ox), np.interp(ta - 0.5, ot, oy)
        bx_, by_ = np.interp(ta + 0.5, ot, ox), np.interp(ta + 0.5, ot, oy)
        v_other = np.hypot(bx_ - ax_, by_ - ay_) / per_m * 3.6        # km/h
        fast = (v_other >= MIN_SPEED_KMH) & (v_other >= SAME_PACE * va * 3.6)
        for k in np.where(ok & ~hole & fast)[0]:
            d = np.hypot(px - qx[k], py - qy[k])
            j = int(np.argmin(d))
            if d[j] / per_m > MAX_OFF_M:
                continue
            ahead = (s[j] - sa[k]) / per_m
            if 0.0 < ahead <= window_m:
                events.append({"driver": drv, "t": float(tt[k]), "km": float(sa[k] / per_m / 1000),
                               "gap_m": float(ahead), "gap_s": float(ahead / max(va[k], 1.0))})
    return sorted(events, key=lambda e: e["t"])


def closest(events: list[dict], zone_km: tuple[float, float] | None = None) -> dict[str, dict]:
    """Pro Fahrer der kleinste Zeitabstand, optional nur im Abschnitt zone_km."""
    out: dict[str, dict] = {}
    for e in events:
        if zone_km and not zone_km[0] <= e["km"] <= zone_km[1]:
            continue
        if e["driver"] not in out or e["gap_s"] < out[e["driver"]]["gap_s"]:
            out[e["driver"]] = e
    return dict(sorted(out.items(), key=lambda kv: kv[1]["gap_s"]))
