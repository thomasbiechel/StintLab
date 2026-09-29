"""Teamkollegen-Duell im Qualifying über die ganze Saison.

FRAGE: Wer schlägt seinen Teamkollegen – wie oft und um wie viel?

METHODE, pro Qualifying und Team:
- Wer ist vorne? = besserer Platz im offiziellen Quali-Ergebnis (vor
  Startplatzstrafen – es geht um die Runde, nicht um die Startaufstellung).
- Wie viel? = Zeitabstand im LETZTEN Abschnitt, in dem BEIDE eine Zeit gesetzt
  haben (Q3, sonst Q2, sonst Q1), in Prozent der schnelleren Zeit. Prozent statt
  Sekunden, weil Monza (~80 s) und Singapur (~90 s) sonst nicht vergleichbar sind.
- Pro Paarung: Siege und MEDIAN des Abstands (ein verpatztes Qualifying soll den
  Wert nicht dominieren).
- Hat einer keine Zeit (nicht gefahren, disqualifiziert), zählt das Qualifying
  nicht für die Paarung.
- Fahrerwechsel in der Saison: jede Paarung wird für sich gewertet.

GRENZE: Der Abstand im letzten gemeinsamen Abschnitt ist nicht immer eine faire
Runde (Verkehr, gelbe Flagge, Regen im Abschnitt). Der Median dämpft das, hebt es
aber nicht auf.
"""

from __future__ import annotations

from statistics import median

from stintlab.preview import team_name
from stintlab.style import COLORS, style_axes, team_color

MIN_DUELS = 3          # weniger gemeinsame Qualifyings → Paarung nicht gezeigt


def _times(r: dict) -> list:
    d = r.get("duration")
    return d if isinstance(d, list) else [d]


def duel(ra: dict, rb: dict) -> tuple[str, float] | None:
    """Ein Qualifying: (Kürzel des Vorderen, Abstand in % zum Hinteren) oder None."""
    ta, tb = _times(ra), _times(rb)
    common = [i for i in range(min(len(ta), len(tb)))
              if isinstance(ta[i], (int, float)) and isinstance(tb[i], (int, float))]
    if not common or ra.get("dsq") or rb.get("dsq"):
        return None
    i = common[-1]
    pa, pb = ra.get("position"), rb.get("position")
    if isinstance(pa, int) and isinstance(pb, int):
        ahead_a = pa < pb
    else:
        ahead_a = ta[i] <= tb[i]
    fast, slow = (ta[i], tb[i]) if ahead_a else (tb[i], ta[i])
    return (ra["driver"] if ahead_a else rb["driver"]), (slow / fast - 1) * 100


def duel_rows(sessions: list[dict], min_duels: int = MIN_DUELS) -> list[dict]:
    """[{team, a, b, wins_a, wins_b, n, median_pct, places}] – a = der mit mehr Siegen.
    median_pct > 0: a im Median so viel % schneller (im letzten gemeinsamen Abschnitt)."""
    pairs: dict[tuple, dict] = {}
    for s in sessions:
        by_team: dict[str, list[dict]] = {}
        for r in s.get("results", []):
            t = team_name(s.get("teams", {}).get(r["driver"]))
            if t:
                by_team.setdefault(t, []).append(r)
        for t, rs in by_team.items():
            if len(rs) != 2:
                continue
            ra, rb = sorted(rs, key=lambda r: r["driver"])
            res = duel(ra, rb)
            if res is None:
                continue
            key = (t, ra["driver"], rb["driver"])
            p = pairs.setdefault(key, {"wins": {ra["driver"]: 0, rb["driver"]: 0}, "gaps": [], "places": []})
            winner, pct = res
            p["wins"][winner] += 1
            p["gaps"].append(pct if winner == ra["driver"] else -pct)      # > 0: ra vorne
            p["places"].append(s.get("place"))
    rows = []
    for (t, x, y), p in pairs.items():
        n = len(p["gaps"])
        if n < min_duels:
            continue
        med = median(p["gaps"])
        a, b = (x, y) if (p["wins"][x], med) >= (p["wins"][y], -med) else (y, x)
        rows.append({"team": t, "a": a, "b": b, "wins_a": p["wins"][a], "wins_b": p["wins"][b], "n": n,
                     "median_pct": med if a == x else -med, "places": p["places"]})
    return sorted(rows, key=lambda r: (-(r["wins_a"] - r["wins_b"]) / r["n"], -r["median_pct"]))


def render_teammate_duel(ax, sessions: list[dict]) -> list[dict]:
    rows = duel_rows(sessions)
    if not rows:
        raise ValueError("Keine Teamkollegen-Paarung mit genug gemeinsamen Qualifyings")
    style_axes(ax, grid_axis="x")
    n = len(rows)
    lim = max(max(abs(r["median_pct"]) for r in rows) * 1.35, 0.3)
    for i, r in enumerate(rows):
        y = n - 1 - i
        col = team_color(r["team"])
        w = r["median_pct"]
        ax.barh(y, w, color=col, height=0.55, alpha=0.9, zorder=3)
        ax.text(-lim * 0.98, y + 0.02, r["a"], ha="left", va="center", fontsize=11, fontweight="bold", color=col)
        ax.text(-lim * 0.98 + lim * 0.3, y, f"{r['wins_a']}–{r['wins_b']}", ha="left", va="center",
                fontsize=12, fontweight="bold", color=COLORS["text"])
        ax.text(-lim * 0.98 + lim * 0.62, y, r["b"], ha="left", va="center", fontsize=11, color=COLORS["muted"],
                fontweight="bold")
        ax.text(max(w, 0) + lim * 0.03, y, f"{w:+.2f} %", ha="left", va="center", fontsize=9,
                color=COLORS["text"], fontweight="bold")
    ax.axvline(0, color=COLORS["muted"], linewidth=0.8)
    ax.set_xlim(-lim, lim * 1.2)
    ax.set_xticks([t for t in ax.get_xticks() if 0 <= t <= lim * 1.2])     # links stehen die Namen
    ax.set_ylim(-0.7, n - 0.3)
    ax.set_yticks([])
    ax.set_xlabel("Median gap to teammate in the last shared session (% of lap time)")
    total = len({s.get("meeting_key") for s in sessions})
    ax.text(0.99, 0.01, f"{total} qualifyings · head-to-head = better quali position · "
            f"pairs with < {MIN_DUELS} shared sessions left out", transform=ax.transAxes,
            ha="right", va="bottom", fontsize=7.5, color=COLORS["muted"])
    return rows
