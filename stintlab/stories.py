"""Story-Finder: Kandidaten für die tiefe Analyse nach dem Rennen.

Leitfaden (Baku 2026): Ein guter Post beantwortet EINE Frage, die sich Fans
nach dem Rennen stellen, und deren Antwort man im TV nicht sieht. Dieses Modul
sucht in den Daten nach Mustern, aus denen solche Fragen werden – jeweils mit
Kennzahlen und einem passenden Slide-Vorschlag. Ob die Frage wirklich trägt
(„interessiert das jemanden?“, „sieht man das im TV?“), entscheidet ein Mensch.

Detektoren (alle nur grüne Runden – kein SC/VSC/rote Flagge, keine Boxenrunden):
- battle:   zwei Autos direkt hintereinander, lange innerhalb 1 s, kein Überholen
            (+ Sektor-Muster: wo holt der Hintere auf, wo verliert er?)
- incident: eine Runde viel langsamer als sonst, dabei Plätze verloren
            (+ in welchem Sektor, + Meldungen der Rennleitung dazu)
- mover:    viele Plätze gewonnen/verloren gegenüber dem Start
- sc:       Vorsprung vor dem ersten Safety Car vs. im Ziel
- pace:     Pace im letzten Stint passt nicht zum Ergebnis
- finish:   knapper Zieleinlauf zwischen zwei Plätzen
"""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import median

from stintlab.analyses.positions import compute_positions
from stintlab.analyses.sector_delta import compute_sector_delta
from stintlab.race_control import restricted_laps

BATTLE_GAP_S = 1.0
BATTLE_MIN_LAPS = 5
INCIDENT_LOSS_S = 5.0
MOVER_MIN_PLACES = 5
FINISH_GAP_S = 1.0


@dataclass
class Story:
    kind: str
    score: float
    question: str
    facts: list[str]
    slides: list[dict] = field(default_factory=list)


def _green_laps(data: dict) -> set[int]:
    restricted = restricted_laps(data.get("race_control", []))
    laps = {l["LapNumber"] for l in data.get("laps", []) if l.get("LapNumber")}
    # auch die Runde nach einer Neutralisation weglassen (Restart)
    return {n for n in laps if n > 1 and n not in restricted and n - 1 not in restricted}


def _pit_laps(data: dict) -> set[tuple[str, int]]:
    out = set()
    for p in data.get("pit_stops", []):
        out |= {(p["driver"], p["lap"]), (p["driver"], (p["lap"] or 0) + 1)}
    return out


def _order(lap_ends: dict, n: int) -> list[str]:
    return [d for _, d in sorted((e[n], d) for d, e in lap_ends.items() if n in e)]


def _front_weight(position: int | None) -> float:
    """Geschichten weiter vorne interessieren mehr: P1 = 1, P4 ≈ 0,5, P10 ≈ 0,25."""
    return 1.0 / (1.0 + (max(position or 20, 1) - 1) / 3.0)


def find_battles(data: dict, max_gap: float = BATTLE_GAP_S, min_laps: int = BATTLE_MIN_LAPS) -> list[Story]:
    ends, green, pits = data.get("lap_ends", {}), _green_laps(data), _pit_laps(data)
    # Positionen mit offizieller Zielrunde – die Zeitstempel der letzten Runde sind
    # ungenau (Baku 2026: VER lag dort „vor“ RUS, offiziell 0,196 s dahinter)
    positions = compute_positions(ends, results=data.get("results"))
    runs: dict[tuple[str, str], list[list[tuple[int, float]]]] = {}
    for n in sorted(green):
        order = _order(ends, n)
        for ahead, behind in zip(order, order[1:]):
            if (ahead, n) in pits or (behind, n) in pits:
                continue
            gap = (ends[behind][n] - ends[ahead][n]).total_seconds()
            if gap > max_gap:
                continue
            seq = runs.setdefault((ahead, behind), [])
            if seq and seq[-1][-1][0] == n - 1:
                seq[-1].append((n, gap))
            else:
                seq.append([(n, gap)])
    stories = []
    for (a, b), seqs in runs.items():
        for seq in seqs:
            if len(seq) < min_laps:
                continue
            first, last = seq[0][0], seq[-1][0]
            gaps = [g for _, g in seq]
            # hat B danach überholt? (Positionen in der Runde nach dem Duell)
            pa, pb = positions.get(a, {}).get(last + 1), positions.get(b, {}).get(last + 1)
            passed = bool(pa and pb and pb < pa)
            facts = [f"{b} {min(gaps):.2f}–{max(gaps):.2f} s hinter {a}, Runden {first}–{last} ({len(seq)} Runden)",
                     "danach überholt" if passed else "kein Überholmanöver"]
            deltas = compute_sector_delta(data, a, b, (first, last))
            med = {k: median(v.values()) for k, v in deltas.items() if v}
            if len(med) == 4:
                parts = [f"S{i} {med[f'Sector{i}']:+.2f}" for i in (1, 2, 3)]
                facts.append(f"{b} minus {a} pro Runde: " + " · ".join(parts) + f" · Runde {med['LapTime']:+.2f} s")
                trade = any(med[f"Sector{i}"] < -0.15 for i in (1, 2, 3)) and any(med[f"Sector{i}"] > 0.1 for i in (1, 2, 3))
                if trade:
                    facts.append("Muster: in einem Sektor klar schneller, in anderen langsamer → hebt sich auf")
            ahead_pos = positions.get(a, {}).get(last)
            if ahead_pos:
                facts.insert(0, f"Kampf um P{ahead_pos}")
            score = len(seq) / max(median(gaps), 0.2) * (0.5 if passed else 1.0) * _front_weight(ahead_pos)
            question = (f"{b} war {len(seq)} Runden in {a}s Windschatten – warum hat er nicht überholt?" if not passed
                        else f"Wie hat {b} {a} nach {len(seq)} Runden Druck geknackt?")
            slides = [{"analysis": "gap_between", "drivers": [a, b], "laps": [first, last]},
                      {"analysis": "gap_on_lap", "drivers": [a, b], "laps": [first, last]},
                      {"analysis": "sector_delta", "drivers": [a, b], "laps": [first, last]},
                      {"analysis": "tow_effect"}]
            stories.append(Story("battle", score, question, facts, slides))
    return stories


def find_incidents(data: dict, loss_s: float = INCIDENT_LOSS_S) -> list[Story]:
    green, pits = _green_laps(data), _pit_laps(data)
    positions = compute_positions(data.get("lap_ends", {}))
    by_driver: dict[str, dict[int, dict]] = {}
    for l in data.get("laps", []):
        by_driver.setdefault(l["Driver"], {})[l["LapNumber"]] = l
    stories = []
    for drv, laps in by_driver.items():
        clean = [float(l["LapTime"]) for n, l in laps.items() if n in green and l.get("LapTime")
                 and (drv, n) not in pits]
        if len(clean) < 5:
            continue
        base = median(clean)
        for n, l in laps.items():
            t = l.get("LapTime")
            if n not in green or (drv, n) in pits or not t or float(t) - base < loss_s:
                continue
            pos = positions.get(drv, {})
            before, after = pos.get(n - 1), pos.get(n)
            lost = (after - before) if before and after else 0
            if lost < 2:
                continue
            sec_base = {k: median(float(x[k]) for x in laps.values() if x.get(k) and x["LapNumber"] in green)
                        for k in ("Sector1", "Sector2", "Sector3")}
            worst = max(sec_base, key=lambda k: float(l.get(k) or 0) - sec_base[k])
            loss = float(t) - base
            msgs = [m["message"] for m in data.get("race_control", [])
                    if f"({drv})" in (m.get("message") or "") and f"LAP {n}" in (m.get("message") or "")]
            later = [p for k, p in pos.items() if k > n]
            facts = [f"Runde {n}: {loss:+.1f} s gegenüber seinem Median, davon vor allem {worst.replace('Sector', 'Sektor ')}",
                     f"P{before} → P{after}" + (f", im Ziel P{later[-1]}" if later else "")]
            facts += [f"Rennleitung: {m}" for m in msgs]
            stories.append(Story("incident", (lost * 1.5 + loss / 2) * (0.5 + _front_weight(before)),
                                 f"Was ist {drv} in Runde {n} passiert? P{before} → P{after} in einer Runde",
                                 facts + ["Hinweis: lap_times blendet Runden über 107 % aus – die Einbruchsrunde "
                                          "fehlt dort, deshalb nur der Positionsverlauf als Vorschlag"],
                                 [{"analysis": "positions", "drivers": [drv], "laps": [max(n - 5, 0), max(pos) if pos else n]}]))
    return stories


def find_movers(data: dict, min_places: int = MOVER_MIN_PLACES) -> list[Story]:
    grid = data.get("grid", {})
    stories = []
    ends = data.get("lap_ends", {})
    retired = [r["driver"] for r in data.get("results", []) if r.get("dnf")]
    for r in data.get("results", []):
        d, pos, start = r["driver"], r.get("position"), grid.get(r["driver"])
        if not pos or not start or abs(start - pos) < min_places:
            continue
        up = start > pos
        # Wie viele Plätze kamen durch Ausfälle von Autos, die vor ihm lagen?
        gifted = []
        for x in retired:
            last = max(ends.get(x, {}) or [0])
            if last and last in ends.get(d, {}) and ends[x][last] < ends[d][last]:
                gifted.append(x)
        facts = [f"Start P{start} → Ziel P{pos} ({start - pos:+d})"]
        if up:
            facts.append(f"davon durch Ausfälle vor ihm: {len(gifted)}" + (f" ({', '.join(gifted)})" if gifted else "")
                         + f" → auf der Strecke {start - pos - len(gifted):+d}")
        q = (f"Wie ist {d} von P{start} auf P{pos} gekommen?" if up else f"Wie ist {d} von P{start} auf P{pos} gefallen?")
        net = abs(start - pos) - (len(gifted) if up else 0)
        stories.append(Story("mover", net * (0.5 + _front_weight(pos)), q, facts,
                             [{"analysis": "positions", "drivers": [d]}]))
    return stories


def find_safety_car(data: dict) -> list[Story]:
    restricted = sorted(restricted_laps(data.get("race_control", [])))
    ends = data.get("lap_ends", {})
    rows = sorted((r for r in data.get("results", []) if r.get("position")), key=lambda r: r["position"])
    if not restricted or len(rows) < 2:
        return []
    before = restricted[0] - 1
    p1, p2 = rows[0]["driver"], rows[1]["driver"]
    if before not in ends.get(p1, {}) or before not in ends.get(p2, {}):
        return []
    order_before = _order(ends, before)
    lead = (ends[order_before[1]][before] - ends[order_before[0]][before]).total_seconds()
    final_gap = rows[1].get("gap")
    final_gap = final_gap if isinstance(final_gap, (int, float)) else None
    top = [r["driver"] for r in rows[:6]]
    facts = [f"Vorsprung {order_before[0]} vor {order_before[1]} nach Runde {before}: {lead:.1f} s",
             f"Im Ziel: {p1} vor {p2}" + (f" um {final_gap:.3f} s" if final_gap is not None else ""),
             f"Top 6 vor dem SC: {' '.join(order_before[:6])} · im Ziel: {' '.join(top)} (Stopps beachten!)"]
    return [Story("sc", lead / max(final_gap or 1.0, 0.1) / 10,
                  f"Was hat das Safety Car in Runde {restricted[0]} verändert – den Abstand oder das Ergebnis?",
                  facts, [{"analysis": "gap_between", "drivers": [order_before[0], order_before[1]]},
                          {"analysis": "pit_cycle", "drivers": [order_before[0], order_before[1]],
                           "laps": [before, restricted[-1]]}])]


def find_pace_vs_result(data: dict, window: int = 10) -> list[Story]:
    green = _green_laps(data)
    last = max(green) if green else 0
    restricted = restricted_laps(data.get("race_control", []))
    start = max([n + 2 for n in restricted if n < last] + [last - window])
    laps = (max(start, last - window + 1), last)
    times: dict[str, list[float]] = {}
    for l in data.get("laps", []):
        if l.get("LapTime") and laps[0] <= l["LapNumber"] <= laps[1] and l["LapNumber"] in green:
            times.setdefault(l["Driver"], []).append(float(l["LapTime"]))
    pace = sorted((median(v), d) for d, v in times.items() if len(v) >= 0.7 * (laps[1] - laps[0] + 1))
    result = {r["driver"]: r["position"] for r in data.get("results", []) if r.get("position")}
    stories = []
    for rank, (m, d) in enumerate(pace, 1):
        pos = result.get(d)
        # nur schnelle Fahrer: „7.-schnellster, aber P13“ ist meist Verkehr, keine Geschichte
        if rank > 5 or not pos or pos - rank < 2:
            continue
        stories.append(Story("pace", (pos - rank) * 1.2,
                             f"{d} war im Schlussstint der {rank}.-schnellste – warum nur P{pos}?",
                             [f"Median Runden {laps[0]}–{laps[1]}: {m - pace[0][0]:+.3f} s auf den Schnellsten ({pace[0][1]})",
                              f"Ziel P{pos}"],
                             [{"analysis": "driver_pace", "laps": list(laps), "min_laps": max(3, int(0.7 * (laps[1] - laps[0] + 1)))}]))
    return stories


def find_close_finishes(data: dict, max_gap: float = FINISH_GAP_S) -> list[Story]:
    rows = sorted((r for r in data.get("results", []) if r.get("position")), key=lambda r: r["position"])
    stories = []
    for a, b in zip(rows, rows[1:]):
        ga, gb = a.get("gap"), b.get("gap")
        if not isinstance(gb, (int, float)) or not isinstance(ga, (int, float)):
            continue
        diff = gb - ga
        if diff < max_gap:
            stories.append(Story("finish", (max_gap - diff) * 5 / b["position"] ** 0.5,
                                 f"P{a['position']} gegen P{b['position']}: {b['driver']} {diff:.3f} s hinter {a['driver']} – wie knapp war es?",
                                 [f"Offizieller Abstand {diff:.3f} s"],
                                 [{"analysis": "gap_between", "drivers": [a["driver"], b["driver"]]}]))
    return stories


DETECTORS = (find_battles, find_incidents, find_movers, find_safety_car, find_pace_vs_result, find_close_finishes)


def _subject(s: Story) -> str | None:
    """Hauptfahrer einer Geschichte (für das Zusammenlegen von Dopplungen)."""
    for sl in s.slides:
        if len(sl.get("drivers", [])) == 1:
            return sl["drivers"][0]
    return None


def find_stories(data: dict) -> list[Story]:
    """Alle Kandidaten, gemischt sortiert: zuerst die beste Geschichte jeder Art
    (sonst füllen z. B. Mittelfeld-Duelle die ganze Liste), dann der Rest."""
    stories = []
    for det in DETECTORS:
        try:
            stories += det(data)
        except Exception as exc:          # ein kaputter Detektor soll die anderen nicht stoppen
            print(f"⚠ {det.__name__}: {exc}")
    # Absteiger, der schon als Zwischenfall erklärt ist → in den Zwischenfall übernehmen
    incidents = {_subject(s): s for s in stories if s.kind == "incident"}
    kept = []
    for s in stories:
        if s.kind == "mover" and _subject(s) in incidents:
            incidents[_subject(s)].facts.append(s.facts[0])
            continue
        kept.append(s)
    kept.sort(key=lambda s: -s.score)
    best, rest, seen = [], [], set()
    for s in kept:
        (rest if s.kind in seen else best).append(s)
        seen.add(s.kind)
    return best + rest
