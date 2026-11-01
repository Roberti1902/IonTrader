# NVDA: Phase-2-Report

Stand 2026-10-31 09:59. 1,377,100 Bars einzeln durchgerechnet. Gesamtlauf: 145 s auf 16 Threads, CPU-Auslastung 69%.

## 1. Die 20 Chartmuster: was wurde zuerst getroffen?

Entry, SL und TP wie im Bild. R = Gewinn in Einheiten des Risikos. Break-even = Trefferquote, ab der das Muster ohne Kosten nichts verliert. Kontrolle = 10,000 Läufe mit gleicher Richtung und gleichen SL/TP-Abständen in ATR, aber an zufällig verschobenen Zeitpunkten. Erst die Differenz zeigt, was das Muster über den Grundtrend der Aktie hinaus leistet.

| Muster | n | TP zuerst | SL zuerst | Zeitlimit | Break-even | Ø R | Ø R Kontrolle | Differenz |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| SKS | 7,414 | 39.0% | 57.7% | 3.3% | 42.4% | -0.044 | -0.015 | -0.030 |
| Doppeltop | 7,656 | 57.2% | 35.7% | 7.1% | 61.6% | -0.011 | -0.018 | +0.006 |
| Dreifachtop | 454 | 60.6% | 37.0% | 2.4% | 64.0% | -0.015 | -0.016 | +0.001 |
| Absteigendes Dreieck | 4,842 | 36.2% | 52.5% | 11.3% | 42.9% | -0.034 | -0.024 | -0.010 |
| Baerenflagge | 605 | 23.5% | 65.0% | 11.6% | 25.9% | +0.124 | -0.002 | +0.126 |
| Baerischer Wimpel | 2,396 | 37.0% | 61.7% | 1.3% | 37.9% | -0.004 | -0.011 | +0.007 |
| Baerischer Keil | 1,844 | 38.7% | 59.8% | 1.5% | 39.8% | +0.001 | -0.007 | +0.008 |
| Baerisches Rechteck | 527 | 60.3% | 35.5% | 4.2% | 63.0% | -0.006 | -0.014 | +0.008 |
| Inverse Tasse | 591 | 32.8% | 62.9% | 4.2% | 35.8% | -0.025 | -0.013 | -0.012 |
| Rounding Top | 2,198 | 46.8% | 36.4% | 16.8% | 56.0% | -0.018 | -0.040 | +0.022 |
| Inverse SKS | 7,485 | 42.5% | 53.7% | 3.8% | 42.4% | +0.063 | +0.037 | +0.025 |
| Doppelboden | 7,501 | 56.4% | 34.8% | 8.7% | 61.2% | -0.001 | +0.006 | -0.007 |
| Dreifachboden | 479 | 59.3% | 37.6% | 3.1% | 61.9% | -0.010 | +0.001 | -0.011 |
| Aufsteigendes Dreieck | 5,735 | 36.9% | 49.9% | 13.2% | 40.9% | +0.068 | +0.070 | -0.003 |
| Bullenflagge | 788 | 24.6% | 64.3% | 11.0% | 25.3% | +0.170 | +0.106 | +0.064 |
| Bullischer Wimpel | 2,913 | 38.9% | 59.5% | 1.7% | 38.9% | +0.049 | +0.053 | -0.004 |
| Bullischer Keil | 2,099 | 39.8% | 58.9% | 1.3% | 39.6% | +0.027 | +0.039 | -0.013 |
| Bullisches Rechteck | 647 | 62.4% | 33.5% | 4.0% | 63.1% | +0.025 | +0.001 | +0.024 |
| Tasse mit Henkel | 665 | 37.0% | 57.9% | 5.1% | 34.8% | +0.108 | +0.064 | +0.044 |
| Rounding Bottom | 1,984 | 50.5% | 30.9% | 18.5% | 55.9% | +0.075 | +0.032 | +0.043 |

### Differenz zur Kontrolle in R je Muster und Timeframe (mindestens 20 Fälle, * = signifikant nach FDR)

| Muster | 1m | 5m | 15m | 1h | 4h | 1D |
|---|---:|---:|---:|---:|---:|---:|
| SKS | -0.04 | -0.01 | +0.04 | -0.03 | +0.01 | +0.10 |
| Doppeltop | +0.00 | -0.00 | +0.07 | +0.04 | +0.19 | +0.03 |
| Dreifachtop | +0.00 | -0.03 | +0.07 |  |  |  |
| Absteigendes Dreieck | -0.01 | -0.01 | +0.08 | -0.11 |  | -0.15 |
| Baerenflagge | +0.12 | +0.05 | +0.58 |  |  |  |
| Baerischer Wimpel | +0.03 | -0.06 | -0.05 |  |  |  |
| Baerischer Keil | +0.00 | +0.02 | +0.09 | -0.10 |  |  |
| Baerisches Rechteck | +0.00 | +0.01 |  |  |  |  |
| Inverse Tasse | -0.01 | -0.09 | +0.24 |  |  |  |
| Rounding Top | +0.01 | +0.04 | +0.10 | +0.09 |  |  |
| Inverse SKS | +0.00 | +0.09 | +0.13 | +0.16 | +0.30 | +0.24 |
| Doppelboden | -0.00 | -0.03 | -0.02 | -0.09 | -0.14 | +0.04 |
| Dreifachboden | +0.00 | -0.20 |  |  |  |  |
| Aufsteigendes Dreieck | -0.02 | +0.05 | +0.16 | +0.14 | -0.17 | -0.13 |
| Bullenflagge | +0.04 | +0.18 | -0.49 |  |  |  |
| Bullischer Wimpel | -0.02 | +0.06 | -0.05 | +0.17 |  | -0.14 |
| Bullischer Keil | -0.03 | +0.04 | +0.08 | -0.05 |  |  |
| Bullisches Rechteck | +0.03 | +0.06 | -0.12 |  |  |  |
| Tasse mit Henkel | +0.03 | +0.11 | +0.13 |  |  |  |
| Rounding Bottom | +0.04 | +0.05 | -0.01 | +0.17 |  |  |

**Muster gegen Kontrolle:** 0 von 92 Kombinationen signifikant nach FDR; ohne Korrektur p<5 %: 5 (Zufall: rund 5).

**Selbstähnlichkeit über Timeframes** (mittlere Rangkorrelation, nahe +1 = dasselbe Verhalten, nahe 0 = keines): roh +0.72 aus 36 Paaren, nach Abzug der Kontrolle **+0.17** aus 36 Paaren.

## 2. Ereignisstudie: alle Muster und Indikatorsignale

1,059 Tests, je 100,000 zufällige Verschiebungen. Nach Korrektur für viele Tests (FDR 5%) bleiben **1** übrig, davon **0** in der erwarteten Richtung.

Ohne Korrektur p<5 %: 36 Tests (bei reinem Zufall rund 53). Median aller p-Werte: 0.53 (bei reinem Zufall 0,50).

n unabh. = Ereignisse, die mindestens einen Horizont auseinanderliegen.

| Signal | TF | Horizont | n | n unabh. | Ø Rendite | Normal | P(steigt) | Normal | q | Erwartung |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| Inverse Tasse | 1m | 6M | 453 | 20 | +30.62 % | +26.74 % | 86.1% | 82.7% | 0.0212 | Gegenteil |

| Familie | Tests | Signifikant |
|---|---:|---:|
| FIB | 140 | 0 |
| MOM | 220 | 0 |
| MR | 240 | 0 |
| Muster | 459 | 1 |

## 3. Fraktale Markthypothese

H = DFA-Hurst der Renditen (0,5 = kein Gedächtnis). H |Rendite| = Gedächtnis der Schwankung. Lo = Test gegen Scheineffekte; außerhalb von 0,809 bis 1,862 ist Langzeit-Gedächtnis bei 95 % signifikant.

| TF | Bars | H | Lo | Gedächtnis? | H abs. | Lo abs. | Gedächtnis? | Zeit H>0,55 | Zeit H<0,45 |
|---|---:|---:|---:|---|---:|---:|---|---:|---:|
| 1m | 1,060,089 | 0.503 | 1.21 | nein | 0.855 | 16.76 | ja | 5% | 10% |
| 5m | 212,224 | 0.513 | 1.21 | nein | 0.831 | 11.50 | ja | 2% | 2% |
| 15m | 70,781 | 0.520 | 1.21 | nein | 0.806 | 8.30 | ja | 1% | 2% |
| 1h | 19,061 | 0.519 | 1.20 | nein | 0.783 | 6.43 | ja | 0% | 3% |
| 4h | 5,446 | 0.499 | 1.17 | nein | 0.747 | 5.20 | ja | 1% | 12% |
| 1D | 6,987 | 0.526 | 1.41 | nein | 0.856 | 4.84 | ja | 10% | 8% |
| 1W | 1,450 | 0.550 | 1.40 | nein | 0.776 | 3.20 | ja | 37% | 16% |
| 12D | 582 | 0.569 | 1.42 | nein | 0.732 | 2.06 | ja | 83% | 0% |
| 1M | 333 | 0.570 | 1.35 | nein | 0.691 | 2.25 | ja | – | – |

## 4. Ist Hurst der Schalter zwischen Mean Reversion und Momentum?

Rendite in Signalrichtung über dem Normalwert, getrennt nach H zum Signalzeitpunkt. Die These stimmt, wenn MR bei H<0,5 und Momentum bei H>0,5 besser abschneidet; |t| ab rund 2 ist unterscheidbar.

| TF | Familie | Horizont | n H<0,5 | Ø H<0,5 | n H>0,5 | Ø H>0,5 | t Differenz | These |
|---|---|---|---:|---:|---:|---:|---:|---|
| 1m | MR | 1T | 88,237 | +0.02 % | 69,010 | -0.01 % | -2.1 | - |
| 1m | MR | 7T | 88,011 | -0.05 % | 68,994 | +0.01 % | -1.8 | - |
| 1m | MOM | 1T | 69,312 | +0.00 % | 52,234 | +0.00 % | +0.2 | - |
| 1m | MOM | 7T | 69,127 | +0.00 % | 52,226 | -0.00 % | +0.9 | - |
| 5m | MR | 1T | 14,428 | -0.02 % | 15,978 | -0.00 % | -0.5 | - |
| 5m | MR | 7T | 14,397 | +0.06 % | 15,960 | +0.03 % | +0.2 | - |
| 5m | MOM | 1T | 10,226 | +0.01 % | 11,224 | -0.01 % | +0.5 | - |
| 5m | MOM | 7T | 10,208 | +0.00 % | 11,205 | +0.02 % | +0.7 | - |
| 15m | MR | 1T | 4,926 | -0.06 % | 5,307 | -0.02 % | -0.6 | - |
| 15m | MR | 7T | 4,924 | +0.21 % | 5,290 | +0.10 % | -0.2 | - |
| 15m | MOM | 1T | 3,364 | +0.06 % | 3,415 | +0.03 % | +0.4 | - |
| 15m | MOM | 7T | 3,363 | +0.07 % | 3,408 | -0.03 % | +1.5 | - |
| 1h | MR | 1T | 1,221 | +0.03 % | 1,086 | +0.20 % | -1.7 | - |
| 1h | MR | 7T | 1,219 | +0.15 % | 1,086 | +0.41 % | -0.8 | - |
| 1h | MOM | 1T | 851 | +0.10 % | 681 | +0.06 % | -0.2 | - |
| 1h | MOM | 7T | 849 | +0.09 % | 681 | +0.16 % | +0.8 | - |
| 4h | MR | 1T | 518 | +0.06 % | 220 | +0.52 % | -1.2 | - |
| 4h | MR | 7T | 518 | +0.31 % | 220 | -0.14 % | +0.4 | - |
| 4h | MOM | 1T | 295 | -0.05 % | 165 | +0.12 % | -0.8 | - |
| 4h | MOM | 7T | 294 | -0.40 % | 165 | +0.18 % | -1.0 | - |
| 1D | MR | 1T | 456 | +0.04 % | 493 | +0.14 % | -0.1 | - |
| 1D | MR | 7T | 456 | -0.09 % | 493 | +0.44 % | -0.5 | - |
| 1D | MOM | 1T | 257 | +0.27 % | 336 | -0.00 % | +1.2 | - |
| 1D | MOM | 7T | 257 | +0.17 % | 336 | -0.00 % | +0.4 | - |
| 1W | MR | 1T | 76 | -1.06 % | 136 | -0.02 % | -1.0 | - |
| 1W | MR | 7T | 76 | -2.11 % | 136 | +0.02 % | -1.4 | - |
| 1W | MOM | 1T | 37 | -0.36 % | 89 | +0.21 % | -0.7 | - |
| 1W | MOM | 7T | 37 | -0.69 % | 89 | +0.14 % | -0.6 | - |

**Gestützt in 0 von 28 Vergleichen.**

## 5. Mean Reversion und Momentum

Rollend über 256 Bars. Stationär = ADF unter -2,86: In diesem Fenster kehrt der Kurs messbar zum Mittelwert zurück (bei reinem Zufall rund 5 % der Fenster). Variance Ratio unter 1 = Umkehr, über 1 = Trend.

| TF | Zeit stationär | Halbwertszeit (Bars) | VR 2 | VR 4 | VR 8 |
|---|---:|---:|---:|---:|---:|
| 1m | 10.7% | 32 | 0.971 | 0.934 | 0.887 |
| 5m | 6.3% | 41 | 0.981 | 0.951 | 0.921 |
| 15m | 4.8% | 42 | 0.989 | 0.972 | 0.942 |
| 1h | 3.9% | 42 | 0.986 | 0.972 | 0.972 |
| 4h | 7.3% | 49 | 0.991 | 0.950 | 0.938 |
| 1D | 3.2% | 54 | 0.981 | 0.944 | 0.943 |
| 1W | 3.9% | 52 | 1.035 | 1.035 | 1.095 |
| 12D | 4.3% | 25 | 1.021 | 1.141 | 1.209 |
