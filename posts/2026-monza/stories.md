# Story-Kandidaten · Italian Grand Prix 2026 · Monza

Leitfaden: eine Frage, die Fans sich stellen · Antwort nicht im TV sichtbar · jede Slide ein Schritt · letzte Slide = Antwort mit Grenzen

## 1. Wie ist ANT von P19 auf P1 gekommen?
*mover · Score 25.5*

- Start P19 → Ziel P1 (+18)
- davon durch Ausfälle vor ihm: 1 (LEC) → auf der Strecke +17

```toml
[[slides]]
analysis = "positions"
drivers  = ["ANT"]
title    = "TITLE TODO"
subtitle = "SUBTITLE TODO"

```

## 2. ANT war 5 Runden in RUSs Windschatten – warum hat er nicht überholt?
*battle · Score 8.6*

- Kampf um P1
- ANT 0.36–0.71 s hinter RUS, Runden 23–27 (5 Runden)
- kein Überholmanöver
- ANT minus RUS pro Runde: S1 -0.20 · S2 +0.26 · S3 -0.03 · Runde +0.03 s
- Muster: in einem Sektor klar schneller, in anderen langsamer → hebt sich auf

```toml
[[slides]]
analysis = "gap_between"
drivers  = ["RUS", "ANT"]
laps     = [23, 27]
title    = "TITLE TODO"
subtitle = "SUBTITLE TODO"

[[slides]]
analysis = "gap_on_lap"
drivers  = ["RUS", "ANT"]
laps     = [23, 27]
title    = "TITLE TODO"
subtitle = "SUBTITLE TODO"

[[slides]]
analysis = "sector_delta"
drivers  = ["RUS", "ANT"]
laps     = [23, 27]
title    = "TITLE TODO"
subtitle = "SUBTITLE TODO"

[[slides]]
analysis = "tow_effect"
title    = "TITLE TODO"
subtitle = "SUBTITLE TODO"

```

## 3. Was ist ALO in Runde 23 passiert? P17 → P20 in einer Runde
*incident · Score 5.1*

- Runde 23: +6.4 s gegenüber seinem Median, davon vor allem Sektor 3
- P17 → P20
- Hinweis: lap_times blendet Runden über 107 % aus – die Einbruchsrunde fehlt dort, deshalb nur der Positionsverlauf als Vorschlag

```toml
[[slides]]
analysis = "positions"
drivers  = ["ALO"]
laps     = [18, 23]
title    = "TITLE TODO"
subtitle = "SUBTITLE TODO"

```

## 4. GAS war im Schlussstint der 5.-schnellste – warum nur P7?
*pace · Score 2.4*

- Median Runden 44–53: +1.263 s auf den Schnellsten (ANT)
- Ziel P7

```toml
[[slides]]
analysis = "driver_pace"
laps     = [44, 53]
min_laps = 7
title    = "TITLE TODO"
subtitle = "SUBTITLE TODO"

```

## 5. P4 gegen P5: PIA 0.197 s hinter NOR – wie knapp war es?
*finish · Score 1.8*

- Offizieller Abstand 0.197 s

```toml
[[slides]]
analysis = "gap_between"
drivers  = ["NOR", "PIA"]
title    = "TITLE TODO"
subtitle = "SUBTITLE TODO"

```

## 6. Was hat die rote Flagge in Runde 3 verändert – den Abstand oder das Ergebnis?
*sc · Score 0.0*

- Vorsprung RUS vor GAS nach Runde 2: 0.8 s
- Im Ziel: ANT vor RUS um 3.857 s
- Top 6 vor der roten Flagge: RUS GAS VER PIA COL NOR · im Ziel: ANT RUS VER NOR PIA HAM (Stopps beachten!)

```toml
[[slides]]
analysis = "gap_between"
drivers  = ["RUS", "GAS"]
title    = "TITLE TODO"
subtitle = "SUBTITLE TODO"

[[slides]]
analysis = "pit_cycle"
drivers  = ["RUS", "GAS"]
laps     = [2, 29]
title    = "TITLE TODO"
subtitle = "SUBTITLE TODO"

```

## 7. Wie ist GAS von P1 auf P7 gefallen?
*mover · Score 5.0*

- Start P1 → Ziel P7 (-6)

```toml
[[slides]]
analysis = "positions"
drivers  = ["GAS"]
title    = "TITLE TODO"
subtitle = "SUBTITLE TODO"

```

## 8. Wie hat NOR GAS nach 11 Runden Druck geknackt?
*battle · Score 5.0*

- Kampf um P6
- NOR 0.23–0.72 s hinter GAS, Runden 10–20 (11 Runden)
- danach überholt
- NOR minus GAS pro Runde: S1 -0.06 · S2 -0.00 · S3 -0.02 · Runde -0.04 s

```toml
[[slides]]
analysis = "gap_between"
drivers  = ["GAS", "NOR"]
laps     = [10, 20]
title    = "TITLE TODO"
subtitle = "SUBTITLE TODO"

[[slides]]
analysis = "gap_on_lap"
drivers  = ["GAS", "NOR"]
laps     = [10, 20]
title    = "TITLE TODO"
subtitle = "SUBTITLE TODO"

[[slides]]
analysis = "sector_delta"
drivers  = ["GAS", "NOR"]
laps     = [10, 20]
title    = "TITLE TODO"
subtitle = "SUBTITLE TODO"

[[slides]]
analysis = "tow_effect"
title    = "TITLE TODO"
subtitle = "SUBTITLE TODO"

```
