# Story-Kandidaten · Singapore Grand Prix 2026 · Marina Bay

Leitfaden: eine Frage, die Fans sich stellen · Antwort nicht im TV sichtbar · jede Slide ein Schritt · letzte Slide = Antwort mit Grenzen

## 1. Wie ist HAD von P22 auf P10 gekommen?
*mover · Score 8.2*

- Start P22 → Ziel P10 (+12)
- davon durch Ausfälle vor ihm: 1 (COL) → auf der Strecke +11

```toml
[[slides]]
analysis = "positions"
drivers  = ["HAD"]
title    = "TITLE TODO"
subtitle = "SUBTITLE TODO"

```

## 2. HAD war im Schlussstint der 5.-schnellste – warum nur P10?
*pace · Score 6.0*

- Median Runden 53–62: +0.506 s auf den Schnellsten (ANT)
- Ziel P10

```toml
[[slides]]
analysis = "driver_pace"
laps     = [53, 62]
min_laps = 7
title    = "TITLE TODO"
subtitle = "SUBTITLE TODO"

```

## 3. NOR war 7 Runden in ANTs Windschatten – warum hat er nicht überholt?
*battle · Score 5.9*

- Kampf um P3
- NOR 0.33–1.03 s hinter ANT, Runden 13–19 (7 Runden)
- kein Überholmanöver
- NOR minus ANT pro Runde: S1 +0.05 · S2 +0.12 · S3 -0.10 · Runde -0.11 s

```toml
[[slides]]
analysis = "gap_between"
drivers  = ["ANT", "NOR"]
laps     = [13, 19]
title    = "TITLE TODO"
subtitle = "SUBTITLE TODO"

[[slides]]
analysis = "gap_on_lap"
drivers  = ["ANT", "NOR"]
laps     = [13, 19]
title    = "TITLE TODO"
subtitle = "SUBTITLE TODO"

[[slides]]
analysis = "sector_delta"
drivers  = ["ANT", "NOR"]
laps     = [13, 19]
title    = "TITLE TODO"
subtitle = "SUBTITLE TODO"

[[slides]]
analysis = "tow_effect"
title    = "TITLE TODO"
subtitle = "SUBTITLE TODO"

```

## 4. Was hat das VSC in Runde 8 verändert – den Abstand oder das Ergebnis?
*sc · Score 0.0*

- Vorsprung VER vor LEC nach Runde 7: 0.9 s
- Im Ziel: VER vor LEC um 7.335 s
- Top 6 vor dem VSC: VER LEC HAM ANT NOR PIA · im Ziel: VER LEC ANT NOR PIA HAM (Stopps beachten!)

```toml
[[slides]]
analysis = "gap_between"
drivers  = ["VER", "LEC"]
title    = "TITLE TODO"
subtitle = "SUBTITLE TODO"

[[slides]]
analysis = "pit_cycle"
drivers  = ["VER", "LEC"]
laps     = [7, 40]
title    = "TITLE TODO"
subtitle = "SUBTITLE TODO"

```

## 5. Wie ist RUS von P19 auf P9 gekommen?
*mover · Score 7.7*

- Start P19 → Ziel P9 (+10)
- davon durch Ausfälle vor ihm: 0 → auf der Strecke +10

```toml
[[slides]]
analysis = "positions"
drivers  = ["RUS"]
title    = "TITLE TODO"
subtitle = "SUBTITLE TODO"

```

## 6. Wie ist LIN von P9 auf P15 gefallen?
*mover · Score 4.1*

- Start P9 → Ziel P15 (-6)

```toml
[[slides]]
analysis = "positions"
drivers  = ["LIN"]
title    = "TITLE TODO"
subtitle = "SUBTITLE TODO"

```

## 7. NOR war 6 Runden in ANTs Windschatten – warum hat er nicht überholt?
*battle · Score 3.6*

- Kampf um P4
- NOR 0.50–0.88 s hinter ANT, Runden 2–7 (6 Runden)
- kein Überholmanöver
- NOR minus ANT pro Runde: S1 +0.13 · S2 -0.13 · S3 +0.03 · Runde +0.02 s

```toml
[[slides]]
analysis = "gap_between"
drivers  = ["ANT", "NOR"]
laps     = [2, 7]
title    = "TITLE TODO"
subtitle = "SUBTITLE TODO"

[[slides]]
analysis = "gap_on_lap"
drivers  = ["ANT", "NOR"]
laps     = [2, 7]
title    = "TITLE TODO"
subtitle = "SUBTITLE TODO"

[[slides]]
analysis = "sector_delta"
drivers  = ["ANT", "NOR"]
laps     = [2, 7]
title    = "TITLE TODO"
subtitle = "SUBTITLE TODO"

[[slides]]
analysis = "tow_effect"
title    = "TITLE TODO"
subtitle = "SUBTITLE TODO"

```

## 8. PIA war im Schlussstint der 2.-schnellste – warum nur P5?
*pace · Score 3.6*

- Median Runden 53–62: +0.214 s auf den Schnellsten (ANT)
- Ziel P5

```toml
[[slides]]
analysis = "driver_pace"
laps     = [53, 62]
min_laps = 7
title    = "TITLE TODO"
subtitle = "SUBTITLE TODO"

```
