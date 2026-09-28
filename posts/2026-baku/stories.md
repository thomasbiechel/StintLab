# Story-Kandidaten · Azerbaijan Grand Prix 2026 · Baku

Leitfaden: eine Frage, die Fans sich stellen · Antwort nicht im TV sichtbar · jede Slide ein Schritt · letzte Slide = Antwort mit Grenzen

## 1. Was ist PIA in Runde 40 passiert? P3 → P15 in einer Runde
*incident · Score 25.7*

- Runde 40: +10.8 s gegenüber seinem Median, davon vor allem Sektor 1
- P3 → P15, im Ziel P14
- Rennleitung: CAR 81 (PIA) TIME 1:58.595 DELETED - TRACK LIMITS AT TURN 1 LAP 40 16:20:55
- Hinweis: lap_times blendet Runden über 107 % aus – die Einbruchsrunde fehlt dort, deshalb nur der Positionsverlauf als Vorschlag
- Start P3 → Ziel P14 (-11)

```toml
[[slides]]
analysis = "positions"
drivers  = ["PIA"]
laps     = [35, 51]
title    = "TITLE TODO"
subtitle = "SUBTITLE TODO"

```

## 2. VER war 11 Runden in RUSs Windschatten – warum hat er nicht überholt?
*battle · Score 17.8*

- Kampf um P1
- VER 0.50–0.91 s hinter RUS, Runden 40–50 (11 Runden)
- kein Überholmanöver
- VER minus RUS pro Runde: S1 +0.18 · S2 +0.26 · S3 -0.45 · Runde +0.01 s
- Muster: in einem Sektor klar schneller, in anderen langsamer → hebt sich auf

```toml
[[slides]]
analysis = "gap_between"
drivers  = ["RUS", "VER"]
laps     = [40, 50]
title    = "TITLE TODO"
subtitle = "SUBTITLE TODO"

[[slides]]
analysis = "gap_on_lap"
drivers  = ["RUS", "VER"]
laps     = [40, 50]
title    = "TITLE TODO"
subtitle = "SUBTITLE TODO"

[[slides]]
analysis = "sector_delta"
drivers  = ["RUS", "VER"]
laps     = [40, 50]
title    = "TITLE TODO"
subtitle = "SUBTITLE TODO"

[[slides]]
analysis = "tow_effect"
title    = "TITLE TODO"
subtitle = "SUBTITLE TODO"

```

## 3. Wie ist ANT von P16 auf P5 gekommen?
*mover · Score 9.3*

- Start P16 → Ziel P5 (+11)
- davon durch Ausfälle vor ihm: 1 (GAS) → auf der Strecke +10

```toml
[[slides]]
analysis = "positions"
drivers  = ["ANT"]
title    = "TITLE TODO"
subtitle = "SUBTITLE TODO"

```

## 4. Was hat das Safety Car in Runde 31 verändert – den Abstand oder das Ergebnis?
*sc · Score 5.8*

- Vorsprung RUS vor PIA nach Runde 30: 11.4 s
- Im Ziel: RUS vor VER um 0.196 s
- Top 6 vor dem SC: RUS PIA VER HAD LEC HAM · im Ziel: RUS VER HAD LEC ANT HAM (Stopps beachten!)

```toml
[[slides]]
analysis = "gap_between"
drivers  = ["RUS", "PIA"]
title    = "TITLE TODO"
subtitle = "SUBTITLE TODO"

[[slides]]
analysis = "pit_cycle"
drivers  = ["RUS", "PIA"]
laps     = [30, 38]
title    = "TITLE TODO"
subtitle = "SUBTITLE TODO"

```

## 5. P1 gegen P2: VER 0.196 s hinter RUS – wie knapp war es?
*finish · Score 2.8*

- Offizieller Abstand 0.196 s

```toml
[[slides]]
analysis = "gap_between"
drivers  = ["RUS", "VER"]
title    = "TITLE TODO"
subtitle = "SUBTITLE TODO"

```

## 6. ANT war im Schlussstint der 3.-schnellste – warum nur P5?
*pace · Score 2.4*

- Median Runden 42–51: +0.650 s auf den Schnellsten (RUS)
- Ziel P5

```toml
[[slides]]
analysis = "driver_pace"
laps     = [42, 51]
min_laps = 7
title    = "TITLE TODO"
subtitle = "SUBTITLE TODO"

```

## 7. VER war 13 Runden in PIAs Windschatten – warum hat er nicht überholt?
*battle · Score 15.0*

- Kampf um P2
- VER 0.35–0.94 s hinter PIA, Runden 7–19 (13 Runden)
- kein Überholmanöver
- VER minus PIA pro Runde: S1 +0.20 · S2 +0.41 · S3 -0.61 · Runde -0.01 s
- Muster: in einem Sektor klar schneller, in anderen langsamer → hebt sich auf

```toml
[[slides]]
analysis = "gap_between"
drivers  = ["PIA", "VER"]
laps     = [7, 19]
title    = "TITLE TODO"
subtitle = "SUBTITLE TODO"

[[slides]]
analysis = "gap_on_lap"
drivers  = ["PIA", "VER"]
laps     = [7, 19]
title    = "TITLE TODO"
subtitle = "SUBTITLE TODO"

[[slides]]
analysis = "sector_delta"
drivers  = ["PIA", "VER"]
laps     = [7, 19]
title    = "TITLE TODO"
subtitle = "SUBTITLE TODO"

[[slides]]
analysis = "tow_effect"
title    = "TITLE TODO"
subtitle = "SUBTITLE TODO"

```

## 8. HAD war 13 Runden in VERs Windschatten – warum hat er nicht überholt?
*battle · Score 11.9*

- Kampf um P3
- HAD 0.15–1.03 s hinter VER, Runden 18–30 (13 Runden)
- kein Überholmanöver
- HAD minus VER pro Runde: S1 +0.04 · S2 +0.20 · S3 -0.23 · Runde +0.06 s
- Muster: in einem Sektor klar schneller, in anderen langsamer → hebt sich auf

```toml
[[slides]]
analysis = "gap_between"
drivers  = ["VER", "HAD"]
laps     = [18, 30]
title    = "TITLE TODO"
subtitle = "SUBTITLE TODO"

[[slides]]
analysis = "gap_on_lap"
drivers  = ["VER", "HAD"]
laps     = [18, 30]
title    = "TITLE TODO"
subtitle = "SUBTITLE TODO"

[[slides]]
analysis = "sector_delta"
drivers  = ["VER", "HAD"]
laps     = [18, 30]
title    = "TITLE TODO"
subtitle = "SUBTITLE TODO"

[[slides]]
analysis = "tow_effect"
title    = "TITLE TODO"
subtitle = "SUBTITLE TODO"

```
