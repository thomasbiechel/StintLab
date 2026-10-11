# Story-Kandidaten · Bahrain Grand Prix 2026 · Kuala Lumpur

Leitfaden: eine Frage, die Fans sich stellen · Antwort nicht im TV sichtbar · jede Slide ein Schritt · letzte Slide = Antwort mit Grenzen

## 1. Wie ist RUS von P7 auf P20 gefallen?
*mover · Score 8.3*

- Start P7 → Ziel P20 (-13)

```toml
[[slides]]
analysis = "positions"
drivers  = ["RUS"]
title    = "TITLE TODO"
subtitle = "SUBTITLE TODO"

```

## 2. Was ist ALB in Runde 14 passiert? P13 → P15 in einer Runde
*incident · Score 4.0*

- Runde 14: +5.4 s gegenüber seinem Median, davon vor allem Sektor 1
- P13 → P15, im Ziel P19
- Hinweis: lap_times blendet Runden über 107 % aus – die Einbruchsrunde fehlt dort, deshalb nur der Positionsverlauf als Vorschlag

```toml
[[slides]]
analysis = "positions"
drivers  = ["ALB"]
laps     = [9, 41]
title    = "TITLE TODO"
subtitle = "SUBTITLE TODO"

```

## 3. Wie hat PIA LIN nach 7 Runden Druck geknackt?
*battle · Score 1.9*

- Kampf um P8
- PIA 0.32–0.91 s hinter LIN, Runden 16–22 (7 Runden)
- danach überholt
- PIA minus LIN pro Runde: S1 -0.01 · S2 +0.03 · S3 -0.17 · Runde -0.16 s

```toml
[[slides]]
analysis = "gap_between"
drivers  = ["LIN", "PIA"]
laps     = [16, 22]
title    = "TITLE TODO"
subtitle = "SUBTITLE TODO"

[[slides]]
analysis = "gap_on_lap"
drivers  = ["LIN", "PIA"]
laps     = [16, 22]
title    = "TITLE TODO"
subtitle = "SUBTITLE TODO"

[[slides]]
analysis = "sector_delta"
drivers  = ["LIN", "PIA"]
laps     = [16, 22]
title    = "TITLE TODO"
subtitle = "SUBTITLE TODO"

[[slides]]
analysis = "tow_effect"
title    = "TITLE TODO"
subtitle = "SUBTITLE TODO"

```

## 4. P14 gegen P15: OCO 0.227 s hinter BEA – wie knapp war es?
*finish · Score 1.0*

- Offizieller Abstand 0.227 s

```toml
[[slides]]
analysis = "gap_between"
drivers  = ["BEA", "OCO"]
title    = "TITLE TODO"
subtitle = "SUBTITLE TODO"

```

## 5. Was hat das Safety Car in Runde 2 verändert – den Abstand oder das Ergebnis?
*sc · Score 0.2*

- Vorsprung VER vor HAM nach Runde 1: 5.0 s
- Im Ziel: VER vor ANT um 2.307 s
- Top 6 vor dem SC: VER HAM ANT LEC NOR PIA · im Ziel: VER ANT HAM LEC HAD PIA (Stopps beachten!)

```toml
[[slides]]
analysis = "gap_between"
drivers  = ["VER", "HAM"]
title    = "TITLE TODO"
subtitle = "SUBTITLE TODO"

[[slides]]
analysis = "pit_cycle"
drivers  = ["VER", "HAM"]
laps     = [1, 51]
title    = "TITLE TODO"
subtitle = "SUBTITLE TODO"

```

## 6. Wie ist LIN von P22 auf P10 gekommen?
*mover · Score 8.2*

- Start P22 → Ziel P10 (+12)
- davon durch Ausfälle vor ihm: 1 (RUS) → auf der Strecke +11

```toml
[[slides]]
analysis = "positions"
drivers  = ["LIN"]
title    = "TITLE TODO"
subtitle = "SUBTITLE TODO"

```

## 7. Wie ist BOR von P10 auf P18 gefallen?
*mover · Score 5.2*

- Start P10 → Ziel P18 (-8)

```toml
[[slides]]
analysis = "positions"
drivers  = ["BOR"]
title    = "TITLE TODO"
subtitle = "SUBTITLE TODO"

```

## 8. Wie ist COL von P21 auf P13 gekommen?
*mover · Score 4.9*

- Start P21 → Ziel P13 (+8)
- davon durch Ausfälle vor ihm: 1 (RUS) → auf der Strecke +7

```toml
[[slides]]
analysis = "positions"
drivers  = ["COL"]
title    = "TITLE TODO"
subtitle = "SUBTITLE TODO"

```
