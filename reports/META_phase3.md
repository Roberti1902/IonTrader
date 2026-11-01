# META: Phase-3-Report

Stand 2026-10-31 00:13. 1,256,789 Trainingspunkte, META plus 30 weitere Ticker. Walk-Forward über 5 Testjahre von 2019-11-01 bis 2024-10-30; die Zeit danach bleibt für Phase 5 unangetastet.

Für jedes Testjahr: Training nur mit dem, was vorher bekannt war; Auswahl des besten Stands auf einem eigenen Zeitfenster davor; gemessen nur im Testjahr selbst. Ein Netz wird je Ziel nur übernommen, wenn es die Basis im Auswahlfenster belegbar schlägt (t ≥ 2 auf unabhängigen Blöcken). Sonst bleibt das Ziel auf der Basis und zeigt hier 0 %.

In Klammern das 95 %-Intervall; fett, wenn es ganz über null liegt.

## Spanne: Was die Schwankungs-Formel allein leistet

HAR = Schwankung aus letztem Tag, letzter Woche und letztem Monat, gegenüber festen Quantilen.

| 1T | 7T | 1M | 6M | 1J |
|---:|---:|---:|---:|---:|
| **+3.54 %** (+2.6 bis +4.5) | **+2.67 %** (+1.3 bis +3.9) | **+3.82 %** (+1.0 bis +6.6) | +3.68 % (-0.9 bis +8.4) | -1.81 % (-15.2 bis +2.9) |

## Richtung: Brier Skill gegen die Basisrate

| Modell | Modus | 1T | 7T | 1M | 6M | 1J |
|---|---|---:|---:|---:|---:|---:|
| lstm | nur Ticker | +0.00 % (-0.0 bis +0.0) | -1.89 % (-4.2 bis +0.5) | -0.00 % (-0.0 bis +0.0) | +0.00 % (+0.0 bis +0.0) | -0.00 % (-0.0 bis +0.0) |
| lstm | Universum + Feinschliff | +0.00 % (-0.0 bis +0.0) | -0.97 % (-2.4 bis +0.6) | -1.43 % (-5.3 bis +2.3) | +0.00 % (+0.0 bis +0.0) | -0.00 % (-0.0 bis +0.0) |
| gru | nur Ticker | -0.23 % (-0.4 bis -0.1) | -1.18 % (-1.8 bis -0.6) | -0.00 % (-0.0 bis +0.0) | +0.00 % (+0.0 bis +0.0) | -0.00 % (-0.0 bis +0.0) |
| gru | Universum + Feinschliff | -0.22 % (-0.8 bis +0.3) | +0.00 % (+0.0 bis +0.0) | -5.21 % (-12.8 bis +2.2) | +0.00 % (+0.0 bis +0.0) | -0.00 % (-0.0 bis +0.0) |
| transformer | nur Ticker | -0.23 % (-0.4 bis -0.1) | +0.00 % (+0.0 bis +0.0) | -0.00 % (-0.0 bis +0.0) | +0.00 % (+0.0 bis +0.0) | -0.00 % (-0.0 bis +0.0) |
| transformer | Universum + Feinschliff | +0.19 % (-0.2 bis +0.5) | +0.43 % (-1.4 bis +2.2) | -3.45 % (-12.0 bis +4.5) | +0.00 % (+0.0 bis +0.0) | -0.00 % (-0.0 bis +0.0) |
| tft | nur Ticker | +0.11 % (-0.1 bis +0.3) | -2.14 % (-4.0 bis -0.2) | +1.13 % (-2.2 bis +5.3) | +0.00 % (+0.0 bis +0.0) | -0.00 % (-0.0 bis +0.0) |
| tft | Universum + Feinschliff | +0.00 % (-0.0 bis +0.0) | -2.90 % (-4.8 bis -1.1) | +1.17 % (-3.8 bis +5.6) | +0.00 % (+0.0 bis +0.0) | -0.00 % (-0.0 bis +0.0) |

## Spanne: Pinball Skill der Netze gegen HAR

| Modell | Modus | 1T | 7T | 1M | 6M | 1J |
|---|---|---:|---:|---:|---:|---:|
| lstm | nur Ticker | -0.00 % (-0.0 bis +0.0) | +0.00 % (+0.0 bis +0.0) | +0.00 % (-0.0 bis +0.0) | -0.00 % (-0.0 bis +0.0) | -0.00 % (-0.0 bis +0.0) |
| lstm | Universum + Feinschliff | -0.00 % (-0.0 bis +0.0) | +0.00 % (+0.0 bis +0.0) | -1.78 % (-4.8 bis +0.9) | -0.00 % (-0.0 bis +0.0) | -0.00 % (-0.0 bis +0.0) |
| gru | nur Ticker | -0.35 % (-0.6 bis -0.1) | -2.01 % (-3.1 bis -0.9) | +0.00 % (-0.0 bis +0.0) | -0.00 % (-0.0 bis +0.0) | -0.00 % (-0.0 bis +0.0) |
| gru | Universum + Feinschliff | -0.00 % (-0.0 bis +0.0) | +0.00 % (+0.0 bis +0.0) | -3.93 % (-9.0 bis +0.1) | -0.00 % (-0.0 bis +0.0) | -0.00 % (-0.0 bis +0.0) |
| transformer | nur Ticker | -0.00 % (-0.0 bis +0.0) | +0.00 % (+0.0 bis +0.0) | +0.00 % (-0.0 bis +0.0) | -0.00 % (-0.0 bis +0.0) | -0.00 % (-0.0 bis +0.0) |
| transformer | Universum + Feinschliff | -0.00 % (-0.0 bis +0.0) | +0.00 % (+0.0 bis +0.0) | -2.51 % (-9.8 bis +3.7) | -0.00 % (-0.0 bis +0.0) | -0.00 % (-0.0 bis +0.0) |
| tft | nur Ticker | -0.00 % (-0.3 bis +0.3) | -5.39 % (-8.5 bis -2.4) | +0.96 % (-0.9 bis +3.5) | -0.00 % (-0.0 bis +0.0) | -0.00 % (-0.0 bis +0.0) |
| tft | Universum + Feinschliff | -0.00 % (-0.0 bis +0.0) | +0.07 % (-0.1 bis +0.3) | +0.00 % (-0.0 bis +0.0) | -0.00 % (-0.0 bis +0.0) | -0.00 % (-0.0 bis +0.0) |

## Trefferquote: Modell / Basisrate

| Modell | Modus | 1T | 7T | 1M | 6M | 1J |
|---|---|---:|---:|---:|---:|---:|
| lstm | nur Ticker | 52.8% / 52.8% | 56.3% / 55.8% | 63.9% / 63.9% | 72.0% / 72.0% | 70.5% / 70.5% |
| lstm | Universum + Feinschliff | 52.8% / 52.8% | 56.3% / 55.8% | 62.5% / 63.9% | 72.0% / 72.0% | 70.5% / 70.5% |
| gru | nur Ticker | 52.8% / 52.8% | 55.8% / 55.8% | 63.9% / 63.9% | 72.0% / 72.0% | 70.5% / 70.5% |
| gru | Universum + Feinschliff | 53.5% / 52.8% | 55.8% / 55.8% | 55.8% / 63.9% | 72.0% / 72.0% | 70.5% / 70.5% |
| transformer | nur Ticker | 52.8% / 52.8% | 55.8% / 55.8% | 63.9% / 63.9% | 72.0% / 72.0% | 70.5% / 70.5% |
| transformer | Universum + Feinschliff | 53.0% / 52.8% | 56.5% / 55.8% | 58.0% / 63.9% | 72.0% / 72.0% | 70.5% / 70.5% |
| tft | nur Ticker | 52.4% / 52.8% | 55.7% / 55.8% | 63.2% / 63.9% | 72.0% / 72.0% | 70.5% / 70.5% |
| tft | Universum + Feinschliff | 52.8% / 52.8% | 56.6% / 55.8% | 62.6% / 63.9% | 72.0% / 72.0% | 70.5% / 70.5% |

## Unabhängige Fälle in den Testjahren

| 1T | 7T | 1M | 6M | 1J |
|---:|---:|---:|---:|---:|
| 1255 | 260 | 61 | 10 | 5 |

## Welcher Timeframe zählt für welchen Horizont? (tft, Universum + Feinschliff, letztes Testjahr)

Mittlere Attention je Horizont. Rund 14 % überall heißt: keine erkennbare Bevorzugung eines Timeframes.

| Horizont | 5m | 15m | 1h | 4h | 1D | 1W | 1M |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1T | 14% | 14% | 14% | 15% | 14% | 15% | 14% |
| 7T | 14% | 14% | 14% | 15% | 14% | 15% | 14% |
| 1M | 14% | 14% | 14% | 15% | 14% | 15% | 14% |
| 6M | 14% | 14% | 14% | 15% | 14% | 15% | 14% |
| 1J | 14% | 14% | 14% | 15% | 14% | 15% | 13% |

## Pattern-Matching

4,109,904 historische Sequenzen über 6 Timeframes und 3 Fensterlängen. 3,000 Abfragen, jede kennt nur die Vergangenheit bis zu ihrem Zeitpunkt. Dauer je Abfrage: Median 10 ms, 99 % unter 13 ms.

| Horizont | Abfragen | unabhängig | Brier Skill | 95 %-Intervall | Ø P(steigt) Matching | Ø Basisrate |
|---|---:|---:|---:|---:|---:|---:|
| 1T | 2,998 | 1138 | -0.49 % | -1.1 bis +0.2 | 53.0% | 53.2% |
| 7T | 2,993 | 260 | -0.48 % | -1.0 bis +0.1 | 57.1% | 57.0% |
| 1M | 2,949 | 61 | -0.92 % | -1.4 bis -0.4 | 64.0% | 63.9% |
| 6M | 2,714 | 10 | -0.23 % | -1.1 bis +0.1 | 75.5% | 75.5% |
| 1J | 2,406 | 5 | -0.34 % | -0.4 bis +0.3 | 76.3% | 76.1% |
