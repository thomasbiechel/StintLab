"""Testet die Instagram-Hülle mit erfundenen Rundenzeiten – kein Backend nötig.

Ausführen im Repo-Ordner:  python demo_slide.py
"""

import numpy as np

from stintlab.style import COLORS, new_slide, save_slide

rng = np.random.default_rng(42)
laps = np.arange(1, 26)

# Zwei erfundene Stints: Basiszeit + Reifenabbau pro Runde + Rauschen
driver_a = 92.0 + 0.045 * laps + rng.normal(0, 0.12, laps.size)
driver_b = 92.2 + 0.020 * laps + rng.normal(0, 0.12, laps.size)

fig, ax = new_slide(
    title="Who managed their tyres better in the final stint?",
    subtitle="Demo with synthetic data · lap times in seconds",
)

ax.plot(laps, driver_a, "o-", ms=3.5, lw=1.4, color=COLORS["muted"], label="Driver A")
ax.plot(laps, driver_b, "o-", ms=3.5, lw=1.4, color=COLORS["accent"], label="Driver B")
ax.set_xlabel("Lap in stint")
ax.set_ylabel("Lap time (s)")
ax.legend(loc="upper left")

out = save_slide(fig, "output/demo_slide.png")
print(f"Gespeichert: {out}")