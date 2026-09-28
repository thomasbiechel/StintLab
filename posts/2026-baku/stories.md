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
