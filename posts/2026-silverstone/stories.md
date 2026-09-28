# Story-Kandidaten · British Grand Prix 2026 · Silverstone

Leitfaden: eine Frage, die Fans sich stellen · Antwort nicht im TV sichtbar · jede Slide ein Schritt · letzte Slide = Antwort mit Grenzen

## 1. VER war im Schlussstint der 1.-schnellste – warum nur P20?
*pace · Score 22.8*

- Median Runden 41–47: +0.000 s auf den Schnellsten (VER)
- Ziel P20

```toml
[[slides]]
analysis = "driver_pace"
laps     = [41, 47]
min_laps = 4
title    = "TITLE TODO"
subtitle = "SUBTITLE TODO"

```

## 2. Wie ist ANT von P1 auf P15 gefallen?
*mover · Score 9.5*

- Start P1 → Ziel P15 (-14)

```toml
[[slides]]
analysis = "positions"
drivers  = ["ANT"]
title    = "TITLE TODO"
subtitle = "SUBTITLE TODO"

```

## 3. Was ist HUL in Runde 2 passiert? P15 → P19 in einer Runde
*incident · Score 7.0*

- Runde 2: +8.6 s gegenüber seinem Median, davon vor allem Sektor 2
- P15 → P19, im Ziel P15
- Hinweis: lap_times blendet Runden über 107 % aus – die Einbruchsrunde fehlt dort, deshalb nur der Positionsverlauf als Vorschlag

```toml
[[slides]]
analysis = "positions"
drivers  = ["HUL"]
laps     = [0, 36]
title    = "TITLE TODO"
subtitle = "SUBTITLE TODO"

```

## 4. HAM war 6 Runden in RUSs Windschatten – warum hat er nicht überholt?
*battle · Score 4.0*

- Kampf um P4
- HAM 0.27–0.91 s hinter RUS, Runden 25–30 (6 Runden)
- kein Überholmanöver
- HAM minus RUS pro Runde: S1 -0.22 · S2 +0.06 · S3 +0.01 · Runde -0.16 s

```toml
[[slides]]
analysis = "gap_between"
drivers  = ["RUS", "HAM"]
laps     = [25, 30]
title    = "TITLE TODO"
subtitle = "SUBTITLE TODO"

[[slides]]
analysis = "gap_on_lap"
drivers  = ["RUS", "HAM"]
laps     = [25, 30]
title    = "TITLE TODO"
subtitle = "SUBTITLE TODO"

[[slides]]
analysis = "sector_delta"
drivers  = ["RUS", "HAM"]
laps     = [25, 30]
title    = "TITLE TODO"
subtitle = "SUBTITLE TODO"

[[slides]]
analysis = "tow_effect"
title    = "TITLE TODO"
subtitle = "SUBTITLE TODO"

```

## 5. P1 gegen P2: RUS 0.427 s hinter LEC – wie knapp war es?
*finish · Score 2.0*

- Offizieller Abstand 0.427 s

```toml
[[slides]]
analysis = "gap_between"
drivers  = ["LEC", "RUS"]
title    = "TITLE TODO"
subtitle = "SUBTITLE TODO"

```

## 6. Was hat das VSC in Runde 22 verändert – den Abstand oder das Ergebnis?
*sc · Score 0.8*

- Vorsprung LEC vor ANT nach Runde 21: 3.5 s
- Im Ziel: LEC vor RUS um 0.427 s
- Top 6 vor dem VSC: LEC ANT HAM RUS NOR VER · im Ziel: LEC RUS HAM NOR HAD LAW (Stopps beachten!)

```toml
[[slides]]
analysis = "gap_between"
drivers  = ["LEC", "ANT"]
title    = "TITLE TODO"
subtitle = "SUBTITLE TODO"

[[slides]]
analysis = "pit_cycle"
drivers  = ["LEC", "ANT"]
laps     = [21, 52]
title    = "TITLE TODO"
subtitle = "SUBTITLE TODO"

```

## 7. Wie ist VER von P7 auf P20 gefallen?
*mover · Score 8.3*

- Start P7 → Ziel P20 (-13)

```toml
[[slides]]
analysis = "positions"
drivers  = ["VER"]
title    = "TITLE TODO"
subtitle = "SUBTITLE TODO"

```

## 8. Wie ist COL von P19 auf P9 gekommen?
*mover · Score 7.0*

- Start P19 → Ziel P9 (+10)
- davon durch Ausfälle vor ihm: 1 (VER) → auf der Strecke +9

```toml
[[slides]]
analysis = "positions"
drivers  = ["COL"]
title    = "TITLE TODO"
subtitle = "SUBTITLE TODO"

```
