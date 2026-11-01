# NVDA: Phase-3-Report

Stand 2026-10-31 10:47. 1,256,833 Trainingspunkte, NVDA plus 30 weitere Ticker. Walk-Forward über 5 Testjahre von 2019-11-01 bis 2024-10-30; die Zeit danach bleibt für Phase 5 unangetastet.

Für jedes Testjahr: Training nur mit dem, was vorher bekannt war; Auswahl des besten Stands auf einem eigenen Zeitfenster davor; gemessen nur im Testjahr selbst. Ein Netz wird je Ziel nur übernommen, wenn es die Basis im Auswahlfenster belegbar schlägt (t ≥ 2 auf unabhängigen Blöcken). Sonst bleibt das Ziel auf der Basis und zeigt hier 0 %.

In Klammern das 95 %-Intervall; fett, wenn es ganz über null liegt.

## Spanne: Was die Schwankungs-Formel allein leistet

HAR = Schwankung aus letztem Tag, letzter Woche und letztem Monat, gegenüber festen Quantilen.

| 1T | 7T | 1M | 6M | 1J |
|---:|---:|---:|---:|---:|
| **+2.68 %** (+2.0 bis +3.4) | **+1.36 %** (+0.3 bis +2.5) | -0.23 % (-1.4 bis +1.0) | -3.57 % (-19.1 bis +6.5) | -3.91 % (-5.6 bis -1.6) |

## Richtung: Brier Skill gegen die Basisrate

| Modell | Modus | 1T | 7T | 1M | 6M | 1J |
|---|---|---:|---:|---:|---:|---:|
| lstm | nur Ticker | +0.00 % (+0.0 bis +0.0) | +0.00 % (+0.0 bis +0.0) | -0.00 % (-0.0 bis +0.0) | +0.00 % (+0.0 bis +0.0) | -0.00 % (-0.0 bis -0.0) |
| lstm | Universum + Feinschliff | +0.00 % (+0.0 bis +0.0) | +0.00 % (+0.0 bis +0.0) | -0.00 % (-0.0 bis +0.0) | +0.00 % (+0.0 bis +0.0) | -0.00 % (-0.0 bis -0.0) |
| gru | nur Ticker | +0.00 % (+0.0 bis +0.0) | +0.00 % (+0.0 bis +0.0) | -0.00 % (-0.0 bis +0.0) | +0.00 % (+0.0 bis +0.0) | -0.00 % (-0.0 bis -0.0) |
| gru | Universum + Feinschliff | +0.00 % (+0.0 bis +0.0) | +0.00 % (+0.0 bis +0.0) | -0.00 % (-0.0 bis +0.0) | +0.00 % (+0.0 bis +0.0) | -0.00 % (-0.0 bis -0.0) |
| transformer | nur Ticker | +0.00 % (+0.0 bis +0.0) | +0.00 % (+0.0 bis +0.0) | -0.00 % (-0.0 bis +0.0) | +0.00 % (+0.0 bis +0.0) | -0.00 % (-0.0 bis -0.0) |
| transformer | Universum + Feinschliff | +0.00 % (+0.0 bis +0.0) | +0.00 % (+0.0 bis +0.0) | -3.31 % (-11.5 bis +3.7) | +0.00 % (+0.0 bis +0.0) | -0.00 % (-0.0 bis -0.0) |
| tft | nur Ticker | +0.00 % (+0.0 bis +0.0) | +0.00 % (+0.0 bis +0.0) | -0.00 % (-0.0 bis +0.0) | +0.00 % (+0.0 bis +0.0) | -0.00 % (-0.0 bis -0.0) |
| tft | Universum + Feinschliff | +0.00 % (+0.0 bis +0.0) | +0.00 % (+0.0 bis +0.0) | -0.00 % (-0.0 bis +0.0) | +0.00 % (+0.0 bis +0.0) | -0.00 % (-0.0 bis -0.0) |

## Spanne: Pinball Skill der Netze gegen HAR

| Modell | Modus | 1T | 7T | 1M | 6M | 1J |
|---|---|---:|---:|---:|---:|---:|
| lstm | nur Ticker | +0.00 % (-0.0 bis +0.0) | -0.00 % (-0.0 bis +0.0) | -0.00 % (-0.0 bis +0.0) | +0.00 % (-0.0 bis +0.0) | +0.00 % (-0.0 bis +0.0) |
| lstm | Universum + Feinschliff | +0.00 % (-0.0 bis +0.0) | -0.00 % (-0.0 bis +0.0) | -0.00 % (-0.0 bis +0.0) | +0.00 % (-0.0 bis +0.0) | +0.00 % (-0.0 bis +0.0) |
| gru | nur Ticker | +0.00 % (-0.0 bis +0.0) | -0.00 % (-0.0 bis +0.0) | -0.00 % (-0.0 bis +0.0) | +0.00 % (-0.0 bis +0.0) | +0.00 % (-0.0 bis +0.0) |
| gru | Universum + Feinschliff | +0.00 % (-0.0 bis +0.0) | -0.12 % (-0.3 bis +0.0) | -0.00 % (-0.0 bis +0.0) | +0.00 % (-0.0 bis +0.0) | +0.00 % (-0.0 bis +0.0) |
| transformer | nur Ticker | +0.00 % (-0.0 bis +0.0) | -0.00 % (-0.0 bis +0.0) | -0.00 % (-0.0 bis +0.0) | +0.00 % (-0.0 bis +0.0) | +0.00 % (-0.0 bis +0.0) |
| transformer | Universum + Feinschliff | +0.00 % (-0.0 bis +0.0) | -0.00 % (-0.0 bis +0.0) | -5.41 % (-14.2 bis +1.0) | +0.00 % (-0.0 bis +0.0) | +0.00 % (-0.0 bis +0.0) |
| tft | nur Ticker | +0.00 % (-0.0 bis +0.0) | -0.00 % (-0.0 bis +0.0) | -0.00 % (-0.0 bis +0.0) | +0.00 % (-0.0 bis +0.0) | +0.00 % (-0.0 bis +0.0) |
| tft | Universum + Feinschliff | +0.00 % (-0.0 bis +0.0) | -0.00 % (-0.0 bis +0.0) | -0.00 % (-0.0 bis +0.0) | +0.00 % (-0.0 bis +0.0) | +0.00 % (-0.0 bis +0.0) |

## Trefferquote: Modell / Basisrate

| Modell | Modus | 1T | 7T | 1M | 6M | 1J |
|---|---|---:|---:|---:|---:|---:|
| lstm | nur Ticker | 53.7% / 53.7% | 59.0% / 59.0% | 67.5% / 67.5% | 83.2% / 83.2% | 81.2% / 81.2% |
| lstm | Universum + Feinschliff | 53.7% / 53.7% | 59.0% / 59.0% | 67.5% / 67.5% | 83.2% / 83.2% | 81.2% / 81.2% |
| gru | nur Ticker | 53.7% / 53.7% | 59.0% / 59.0% | 67.5% / 67.5% | 83.2% / 83.2% | 81.2% / 81.2% |
| gru | Universum + Feinschliff | 53.7% / 53.7% | 59.0% / 59.0% | 67.5% / 67.5% | 83.2% / 83.2% | 81.2% / 81.2% |
| transformer | nur Ticker | 53.7% / 53.7% | 59.0% / 59.0% | 67.5% / 67.5% | 83.2% / 83.2% | 81.2% / 81.2% |
| transformer | Universum + Feinschliff | 53.7% / 53.7% | 59.0% / 59.0% | 64.1% / 67.5% | 83.2% / 83.2% | 81.2% / 81.2% |
| tft | nur Ticker | 53.7% / 53.7% | 59.0% / 59.0% | 67.5% / 67.5% | 83.2% / 83.2% | 81.2% / 81.2% |
| tft | Universum + Feinschliff | 53.7% / 53.7% | 59.0% / 59.0% | 67.5% / 67.5% | 83.2% / 83.2% | 81.2% / 81.2% |

## Unabhängige Fälle in den Testjahren

| 1T | 7T | 1M | 6M | 1J |
|---:|---:|---:|---:|---:|
| 1255 | 260 | 61 | 10 | 5 |

## Welcher Timeframe zählt für welchen Horizont? (lstm, nur Ticker, letztes Testjahr)

Mittlere Attention je Horizont. Rund 14 % überall heißt: keine erkennbare Bevorzugung eines Timeframes.

| Horizont | 5m | 15m | 1h | 4h | 1D | 1W | 1M |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1T | 14% | 14% | 14% | 14% | 14% | 14% | 14% |
| 7T | 14% | 14% | 14% | 14% | 14% | 14% | 14% |
| 1M | 14% | 14% | 14% | 14% | 14% | 14% | 14% |
| 6M | 14% | 14% | 14% | 14% | 14% | 14% | 14% |
| 1J | 14% | 14% | 14% | 14% | 14% | 14% | 14% |

## Pattern-Matching

4,122,438 historische Sequenzen über 6 Timeframes und 3 Fensterlängen. 3,000 Abfragen, jede kennt nur die Vergangenheit bis zu ihrem Zeitpunkt. Dauer je Abfrage: Median 11 ms, 99 % unter 14 ms.

| Horizont | Abfragen | unabhängig | Brier Skill | 95 %-Intervall | Ø P(steigt) Matching | Ø Basisrate |
|---|---:|---:|---:|---:|---:|---:|
| 1T | 2,997 | 1141 | -0.82 % | -1.4 bis -0.2 | 54.7% | 54.9% |
| 7T | 2,984 | 260 | -0.53 % | -1.1 bis +0.1 | 59.3% | 59.7% |
| 1M | 2,949 | 61 | -0.91 % | -2.0 bis -0.1 | 68.8% | 69.5% |
| 6M | 2,712 | 10 | +0.01 % | -7.7 bis +1.9 | 81.2% | 82.0% |
| 1J | 2,404 | 5 | -1.14 % | -8.0 bis +0.8 | 74.3% | 75.1% |
