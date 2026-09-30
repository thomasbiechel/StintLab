"""Tests für die Reihenfolge nach der ersten Kurve (echte Startwertung)."""

import numpy as np
import pytest

from stintlab.analyses.first_corner import AFTER_EXIT, first_corner_exit, order_after_turn1, resample
from stintlab.analyses.starts import race_starts

# Abgerundetes Rechteck: 1800 geradeaus Richtung Osten, Kurve (Radius 100) nach rechts, …
R, A, B = 100.0, 1800.0, 800.0
PER = 2 * (A + B) + 2 * np.pi * R


def xy(s):
    s = np.mod(s, PER)
    segs = [("line", (0, 0), (1, 0), A), ("arc", (A, -R), 90, R), ("line", (A + R, -R), (0, -1), B),
            ("arc", (A, -R - B), 0, R), ("line", (A, -2 * R - B), (-1, 0), A), ("arc", (0, -R - B), -90, R),
            ("line", (-R, -R - B), (0, 1), B), ("arc", (0, -R), 180, R)]
    out = []
    for v in np.atleast_1d(s):
        for kind, p, d, L in segs:
            length = L if kind == "line" else np.pi / 2 * R
            if v <= length:
                if kind == "line":
                    out.append((p[0] + d[0] * v, p[1] + d[1] * v))
                else:                           # rechtsherum: Winkel nimmt ab
                    ang = np.radians(d) - v / R
                    out.append((p[0] + R * np.cos(ang), p[1] + R * np.sin(ang)))
                break
            v -= length
    return np.array(out)


def car(offset, speed):
    """Einführungsrunde (langsam, bis −60 s), Stand bis 0, dann Rennen ab offset; Zeitpunkte ~3,7/s."""
    t = np.arange(-160.0, 260.0, 0.27)
    s = np.where(t < -60, offset - PER + 25 * (t + 60), offset)
    s = np.where(t >= 0, offset + speed * t, s)
    p = xy(s)
    return np.column_stack([t, p[:, 0], p[:, 1]])


def test_first_corner_exit_is_after_the_first_arc():
    ref = resample(xy(np.linspace(0, PER, 4000)))
    f = first_corner_exit(ref)
    arc_end = (A + np.pi / 2 * R) / PER
    assert arc_end - 0.005 < f < arc_end + 0.03


def test_order_after_turn1_follows_who_gets_there_first_and_skips_the_formation_lap():
    # POL auf der Pole; B startet 16 dahinter, ist aber schneller → vor POL am Messpunkt;
    # C startet 32 dahinter und bleibt dahinter. Die Einführungsrunde passiert den Messpunkt
    # auch – in anderer Reihenfolge – und darf nicht zählen.
    off, v = {"POL": 0.0, "B": -16.0, "C": -32.0}, {"POL": 55.0, "B": 60.0, "C": 54.0}
    tracks = {d: car(off[d], v[d]) for d in off}
    line1 = {d: (PER - off[d]) / v[d] for d in off}
    # C fehlt in den Rundendaten (wie RUS in Melbourne) – die Zieldurchfahrt kommt aus den Positionen
    known = {k: t for k, t in line1.items() if k != "C"}
    order, at, lines = order_after_turn1(tracks, "POL", known, (line1["POL"], line1["POL"] + PER / 55.0), PER / 55.0)
    assert lines["C"] == pytest.approx(line1["C"], abs=0.3)
    d = at * PER
    expect = sorted(off, key=lambda k: (d - off[k]) / v[k])
    assert [k for k, _ in sorted(order.items(), key=lambda kv: kv[1])] == expect
    assert at > (A + np.pi / 2 * R) / PER + AFTER_EXIT - 0.01


def test_race_starts_uses_the_given_order():
    from datetime import datetime, timedelta
    t0 = datetime(2026, 1, 1)
    names = ["A", "B", "C", "D", "E", "F"]
    race = {"lap_ends": {d: {1: t0 + timedelta(seconds=i)} for i, d in enumerate(names)},
            "grid": {d: i for i, d in enumerate(names, start=1)}, "teams": {}, "race_control": [], "pit_stops": []}
    # an der Linie A-B-C-… (kein Gewinn), nach Kurve 1 aber C vorne
    starts = {s["driver"]: s["gain"] for s in race_starts(race, {"A": 2, "B": 3, "C": 1, "D": 4, "E": 5, "F": 6})}
    assert starts == {"A": -1, "B": -1, "C": 2, "D": 0, "E": 0, "F": 0}
    # Fahrer ohne Messwert fallen heraus, Startplätze werden unter den übrigen neu gezählt
    starts = {s["driver"]: s["gain"] for s in race_starts(race, {"B": 2, "C": 1, "D": 3, "E": 4, "F": 5})}
    assert starts == {"B": -1, "C": 1, "D": 0, "E": 0, "F": 0}
