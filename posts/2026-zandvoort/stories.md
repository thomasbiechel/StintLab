# Story-Kandidaten · Dutch Grand Prix 2026 · Zandvoort

Leitfaden: eine Frage, die Fans sich stellen · Antwort nicht im TV sichtbar · jede Slide ein Schritt · letzte Slide = Antwort mit Grenzen

## 1. Wie ist ALO von P18 auf P9 gekommen?
*mover · Score 7.0*

- Start P18 → Ziel P9 (+9)
- davon durch Ausfälle vor ihm: 0 → auf der Strecke +9

```toml
[[slides]]
analysis = "positions"
drivers  = ["ALO"]
title    = "TITLE TODO"
subtitle = "SUBTITLE TODO"

```

## 2. PIA war im Schlussstint der 1.-schnellste – warum nur P6?
*pace · Score 6.0*

- Median Runden 72–72: +0.000 s auf den Schnellsten (PIA)
- Ziel P6

```toml
[[slides]]
analysis = "driver_pace"
laps     = [72, 72]
min_laps = 3
title    = "TITLE TODO"
subtitle = "SUBTITLE TODO"

```

## 3. Was ist STR in Runde 45 passiert? P17 → P19 in einer Runde
*incident · Score 5.1*

- Runde 45: +9.6 s gegenüber seinem Median, davon vor allem Sektor 3
- P17 → P19
- Hinweis: lap_times blendet Runden über 107 % aus – die Einbruchsrunde fehlt dort, deshalb nur der Positionsverlauf als Vorschlag

```toml
[[slides]]
analysis = "positions"
drivers  = ["STR"]
laps     = [40, 45]
title    = "TITLE TODO"
subtitle = "SUBTITLE TODO"

```

## 4. Wie hat LEC RUS nach 10 Runden Druck geknackt?
*battle · Score 5.1*

- Kampf um P4
- LEC 0.31–0.65 s hinter RUS, Runden 7–16 (10 Runden)
- danach überholt
- LEC minus RUS pro Runde: S1 +0.16 · S2 -0.08 · S3 -0.11 · Runde -0.02 s

```toml
[[slides]]
analysis = "gap_between"
drivers  = ["RUS", "LEC"]
laps     = [7, 16]
title    = "TITLE TODO"
subtitle = "SUBTITLE TODO"

[[slides]]
analysis = "gap_on_lap"
drivers  = ["RUS", "LEC"]
laps     = [7, 16]
title    = "TITLE TODO"
subtitle = "SUBTITLE TODO"

[[slides]]
analysis = "sector_delta"
drivers  = ["RUS", "LEC"]
laps     = [7, 16]
title    = "TITLE TODO"
subtitle = "SUBTITLE TODO"

[[slides]]
analysis = "tow_effect"
title    = "TITLE TODO"
subtitle = "SUBTITLE TODO"

```

## 5. P4 gegen P5: LEC 0.503 s hinter HAM – wie knapp war es?
*finish · Score 1.1*

- Offizieller Abstand 0.503 s

```toml
[[slides]]
analysis = "gap_between"
drivers  = ["HAM", "LEC"]
title    = "TITLE TODO"
subtitle = "SUBTITLE TODO"

```

## 6. Was hat die rote Flagge in Runde 2 verändert – den Abstand oder das Ergebnis?
*sc · Score 0.0*

- Vorsprung NOR vor ANT nach Runde 1: 0.7 s
- Im Ziel: NOR vor ANT um 11.536 s
- Top 6 vor der roten Flagge: NOR ANT RUS LEC PIA HAM · im Ziel: NOR ANT RUS HAM LEC PIA (Stopps beachten!)

```toml
[[slides]]
analysis = "gap_between"
drivers  = ["NOR", "ANT"]
title    = "TITLE TODO"
subtitle = "SUBTITLE TODO"

[[slides]]
analysis = "pit_cycle"
drivers  = ["NOR", "ANT"]
laps     = [1, 70]
title    = "TITLE TODO"
subtitle = "SUBTITLE TODO"

```

## 7. Wie ist HUL von P13 auf P8 gekommen?
*mover · Score 4.0*

- Start P13 → Ziel P8 (+5)
- davon durch Ausfälle vor ihm: 0 → auf der Strecke +5

```toml
[[slides]]
analysis = "positions"
drivers  = ["HUL"]
title    = "TITLE TODO"
subtitle = "SUBTITLE TODO"

```

## 8. Wie hat LEC PIA nach 6 Runden Druck geknackt?
*battle · Score 3.9*

- Kampf um P4
- LEC 0.23–0.77 s hinter PIA, Runden 28–33 (6 Runden)
- danach überholt
- LEC minus PIA pro Runde: S1 +0.14 · S2 -0.01 · S3 -0.28 · Runde -0.14 s
- Muster: in einem Sektor klar schneller, in anderen langsamer → hebt sich auf

```toml
[[slides]]
analysis = "gap_between"
drivers  = ["PIA", "LEC"]
laps     = [28, 33]
title    = "TITLE TODO"
subtitle = "SUBTITLE TODO"

[[slides]]
analysis = "gap_on_lap"
drivers  = ["PIA", "LEC"]
laps     = [28, 33]
title    = "TITLE TODO"
subtitle = "SUBTITLE TODO"

[[slides]]
analysis = "sector_delta"
drivers  = ["PIA", "LEC"]
laps     = [28, 33]
title    = "TITLE TODO"
subtitle = "SUBTITLE TODO"

[[slides]]
analysis = "tow_effect"
title    = "TITLE TODO"
subtitle = "SUBTITLE TODO"

```
