"""Hatte ein Fahrer auf seinen schnellen Runden Windschatten? (stintlab/traffic.py)

Aufruf:
    python tow_check.py 1308 Q ANT                    # alle schnellen Runden im Qualifying
    python tow_check.py 1308 Q ANT --part Q3          # nur Q3
    python tow_check.py 1308 Q ANT --zone 4.2-5.0     # zusätzlich: Abschnitt vor der Speed Trap
    python tow_check.py 1308 FP3 NOR --window 600

Schnelle Runde = gültige Zeit, keine Out-Lap, höchstens 3 % über der Bestzeit des
Fahrers (im gewählten Abschnitt). Beim ersten Mal lädt das Skript die Positions-
daten aller Fahrer der Session (Netz nötig, danach Cache).
"""

from __future__ import annotations

import argparse

from stintlab import openf1
from stintlab.quali import lap_parts
from stintlab.session import load_session
from stintlab.traffic import TOW_S, WINDOW_M, cars_ahead, closest, samples
from stintlab.reels.ghost_lap import lap_positions

FAST_PCT = 1.03


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("meeting_key", type=int)
    ap.add_argument("session", help="FP1, FP2, FP3, SQ, S, Q oder R")
    ap.add_argument("driver", help="Kürzel, z. B. ANT")
    ap.add_argument("--part", help="nur ein Qualifying-Abschnitt: Q1, Q2 oder Q3")
    ap.add_argument("--zone", help="Streckenabschnitt in km, z. B. 4.2-5.0")
    ap.add_argument("--window", type=float, default=WINDOW_M, help=f"Meter vor ihm (Standard {WINDOW_M:.0f})")
    args = ap.parse_args()

    d = load_session(args.meeting_key, args.session)
    drv = args.driver.upper()
    if drv not in d["numbers"]:
        raise SystemExit(f"{drv} fuhr nicht in dieser Session ({', '.join(sorted(d['numbers']))})")
    parts = lap_parts(d) if args.session in ("Q", "SQ") else {}
    laps = [l for l in d["laps"] if l["Driver"] == drv and l.get("LapTime") and not l.get("IsPitOutLap")
            and (not args.part or parts.get((drv, l["LapNumber"])) == args.part)]
    if not laps:
        raise SystemExit("Keine gewerteten Runden gefunden")
    best = min(float(l["LapTime"]) for l in laps)
    fast = [l for l in laps if float(l["LapTime"]) <= best * FAST_PCT]
    zone = tuple(float(x) for x in args.zone.split("-")) if args.zone else None

    key = d["session_key"]
    loc = lambda who: d.get("location", {}).get(who) or openf1.cached_fetch_driver("location", key, d["numbers"][who])
    print(f"Lade Positionsdaten von {len(d['numbers'])} Fahrern …")
    others = {o: samples(loc(o)) for o in d["numbers"] if o != drv}
    own = loc(drv)

    for lap in fast:
        t, x, y = lap_positions(own, lap)
        lt = float(lap["LapTime"])
        inside = (t >= 0) & (t <= lt)
        ev = cars_ahead(lap["LapStart"].timestamp(), lt, (t[inside], x[inside], y[inside]), others,
                        window_m=args.window)
        part = parts.get((drv, lap["LapNumber"]))
        head = f"\n{part + ' · ' if part else ''}Runde {lap['LapNumber']}  {lt:.3f}  Speed Trap {lap.get('SpeedST')} km/h"
        print(head)
        near = closest(ev)
        if not near:
            print(f"   frei – kein Auto innerhalb {args.window:.0f} m vor ihm, die ganze Runde")
        for who, e in list(near.items())[:4]:
            flag = "  ← Windschatten möglich" if e["gap_s"] < TOW_S else ""
            print(f"   {who}: {e['gap_s']:.2f} s / {e['gap_m']:.0f} m vor ihm bei km {e['km']:.2f}{flag}")
        if zone:
            z = closest(ev, zone)
            txt = "frei" if not z else ", ".join(f"{w} {e['gap_s']:.2f} s" for w, e in list(z.items())[:3])
            print(f"   km {zone[0]}–{zone[1]}: {txt}")


if __name__ == "__main__":
    main()
