"""Positionsdaten (/location) für flüssige Animationen aufbereiten.

PROBLEM 1 – ZITTERNDE ZEITSTEMPEL: Die Punkte liegen räumlich richtig, aber
ihre Zeitstempel schwanken um ~±0,1 s. Monza 2026 Q3, Gasly auf der Geraden
(konstant ~305 km/h): von Punkt zu Punkt gerechnet 127 … 468 km/h. Eine weiche
Interpolation macht daraus ein Auto, das ständig bremst und beschleunigt
(„Jojo“).

PROBLEM 2 – EINGEFRORENE POSITION: Gasly bleibt 1,1 s fast auf der Stelle
(29,6–30,7 s der Runde), vorher und nachher ~110 km/h – dieselbe Datenlücke wie
beim eingefrorenen Tempo (siehe telemetry.frozen_runs). So fährt kein Auto.

LÖSUNG (retime): Die Punkte behalten ihre Lage, nur die ZEIT wird geglättet.
1. Hängende Punkte entfernen: Tempo unter 25 % des Tempos der Umgebung (±2 s).
   Echte langsame Stellen (Haarnadel, Boxenstopp) haben eine langsame Umgebung
   und bleiben erhalten.
2. Zeit als Funktion der gefahrenen Strecke glätten: für jeden Punkt eine
   Gerade t(s) durch die Nachbarn im Fenster (~1,2 s), dann streng steigend.
"""

from __future__ import annotations

import numpy as np

WINDOW_S = 1.2   # getestet: Fehler im Tempo −80 %, Bremszonen bleiben erhalten
STALL_RATIO = 0.25
STALL_CONTEXT_S = 2.0


def _arc(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    return np.concatenate([[0.0], np.cumsum(np.hypot(np.diff(x), np.diff(y)))])


def drop_stalls(t, x, y, ratio: float = STALL_RATIO, context_s: float = STALL_CONTEXT_S):
    """Punkte entfernen, an denen das Auto viel langsamer „steht“ als ringsum."""
    if len(t) < 5:
        return t, x, y
    s = _arc(x, y)
    v = np.gradient(s, t)                       # Tempo je Punkt (Einheiten/s)
    keep = np.ones(len(t), dtype=bool)
    lo = np.searchsorted(t, t - context_s)      # Fenster per Index: ganzes Rennen ~37 000 Punkte
    hi = np.searchsorted(t, t + context_s, side="right")
    for i in range(len(t)):
        idx = np.arange(lo[i], hi[i])
        idx = idx[np.abs(t[idx] - t[i]) > 0.3]
        if len(idx) >= 4 and v[i] < ratio * np.median(v[idx]):
            keep[i] = False
    keep[0] = keep[-1] = True
    return t[keep], x[keep], y[keep]


def retime(t, x, y, window_s: float = WINDOW_S):
    """(t, x, y) mit geglätteter Zeit – siehe Moduldoku.

    Der Fehler steckt in der ZEIT, nicht im Ort. Deshalb wird die Zeit als
    Funktion der Strecke geglättet (t über s, lokale Gerade), nicht umgekehrt:
    Regression rechnet den Fehler in der abhängigen Größe heraus."""
    t, x, y = (np.asarray(a, dtype=float) for a in (t, x, y))
    t, x, y = drop_stalls(t, x, y)
    if len(t) < 5:
        return t, x, y
    s = _arc(x, y)
    half = window_s / 2
    t_hat = t.copy()
    lo = np.searchsorted(t, t - half)
    hi = np.searchsorted(t, t + half, side="right")
    for i in range(len(t)):
        ss, tt = s[lo[i]:hi[i]] - s[i], t[lo[i]:hi[i]]
        if len(tt) >= 3 and np.ptp(ss) > 0:
            # Gerade t = a·s + b, ausgewertet bei s = 0 (schneller als polyfit)
            sm, tm = ss.mean(), tt.mean()
            a = np.sum((ss - sm) * (tt - tm)) / np.sum((ss - sm) ** 2)
            t_hat[i] = tm - a * sm
    # streng steigend (Interpolation braucht das); Stillstand bleibt über gleiche Orte erhalten
    for i in range(1, len(t_hat)):
        if t_hat[i] <= t_hat[i - 1]:
            t_hat[i] = t_hat[i - 1] + 1e-3
    return t_hat, x, y
