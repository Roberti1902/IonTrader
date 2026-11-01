# META: Phase-2-Report

Stand 2026-10-30 23:57. 1,371,715 Bars einzeln durchgerechnet. Gesamtlauf: 129 s auf 16 Threads, CPU-Auslastung 79%.

## 1. Die 20 Chartmuster: was wurde zuerst getroffen?

Entry, SL und TP wie im Bild. R = Gewinn in Einheiten des Risikos. Break-even = Trefferquote, ab der das Muster ohne Kosten nichts verliert. Kontrolle = 10,000 Läufe mit gleicher Richtung und gleichen SL/TP-Abständen in ATR, aber an zufällig verschobenen Zeitpunkten. Erst die Differenz zeigt, was das Muster über den Grundtrend der Aktie hinaus leistet.

| Muster | n | TP zuerst | SL zuerst | Zeitlimit | Break-even | Ø R | Ø R Kontrolle | Differenz |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| SKS | 7,935 | 41.7% | 55.3% | 3.0% | 42.5% | +0.023 | +0.002 | +0.021 |
| Doppeltop | 8,944 | 56.2% | 35.7% | 8.2% | 59.8% | +0.007 | -0.007 | +0.013 |
| Dreifachtop | 510 | 58.6% | 38.6% | 2.7% | 59.6% | +0.002 | -0.003 | +0.004 |
| Absteigendes Dreieck | 5,307 | 34.6% | 54.1% | 11.2% | 41.4% | -0.034 | -0.004 | -0.029 |
| Baerenflagge | 618 | 19.3% | 70.2% | 10.5% | 24.9% | -0.036 | +0.012 | -0.048 |
| Baerischer Wimpel | 2,808 | 38.8% | 59.8% | 1.4% | 39.4% | +0.009 | +0.003 | +0.006 |
| Baerischer Keil | 1,622 | 37.6% | 60.9% | 1.5% | 39.3% | -0.009 | +0.004 | -0.013 |
| Baerisches Rechteck | 568 | 56.7% | 40.1% | 3.2% | 60.3% | -0.043 | -0.004 | -0.038 |
| Inverse Tasse | 624 | 32.1% | 63.5% | 4.5% | 34.2% | +0.027 | +0.004 | +0.022 |
| Rounding Top | 2,377 | 44.7% | 37.1% | 18.2% | 55.2% | -0.029 | -0.020 | -0.009 |
| Inverse SKS | 8,046 | 41.8% | 54.6% | 3.6% | 42.5% | +0.038 | +0.015 | +0.023 |
| Doppelboden | 8,735 | 55.0% | 36.3% | 8.7% | 59.6% | -0.002 | -0.003 | +0.001 |
| Dreifachboden | 468 | 59.8% | 36.8% | 3.4% | 58.3% | +0.043 | -0.006 | +0.049 |
| Aufsteigendes Dreieck | 5,878 | 35.4% | 51.5% | 13.1% | 40.1% | +0.055 | +0.035 | +0.021 |
| Bullenflagge | 790 | 24.3% | 63.3% | 12.4% | 25.8% | +0.165 | +0.070 | +0.095 |
| Bullischer Wimpel | 3,139 | 37.9% | 60.7% | 1.3% | 39.0% | -0.012 | +0.021 | -0.033 |
| Bullischer Keil | 1,774 | 39.1% | 58.8% | 2.1% | 39.5% | +0.046 | +0.013 | +0.034 |
| Bullisches Rechteck | 683 | 56.1% | 39.2% | 4.7% | 59.4% | -0.034 | -0.006 | -0.027 |
| Tasse mit Henkel | 630 | 33.2% | 59.8% | 7.0% | 33.5% | +0.091 | +0.029 | +0.063 |
| Rounding Bottom | 2,232 | 46.1% | 32.7% | 21.2% | 54.9% | +0.041 | +0.013 | +0.027 |

### Differenz zur Kontrolle in R je Muster und Timeframe (mindestens 20 Fälle, * = signifikant nach FDR)

| Muster | 1m | 5m | 15m | 1h | 4h | 1D |
|---|---:|---:|---:|---:|---:|---:|
| SKS | +0.01 | +0.06 | +0.08 | +0.19 |  |  |
| Doppeltop | +0.01 | +0.04 | +0.02 | +0.12 | -0.02 | +0.11 |
| Dreifachtop | +0.00 | +0.03 |  |  |  |  |
| Absteigendes Dreieck | -0.03 | -0.05 | -0.07 | +0.01 |  |  |
| Baerenflagge | +0.01 | -0.30 | -0.31 |  |  |  |
| Baerischer Wimpel | +0.03 | -0.09 | -0.07 | -0.14 |  |  |
| Baerischer Keil | +0.03 | -0.13 | -0.28 | -0.41 |  |  |
| Baerisches Rechteck | -0.03 | -0.04 | -0.13 |  |  |  |
| Inverse Tasse | +0.01 | +0.05 |  |  |  |  |
| Rounding Top | -0.01 | -0.03 | -0.08 | +0.01 |  |  |
| Inverse SKS | +0.00 | +0.11 | +0.10 | +0.15 | +0.11 |  |
| Doppelboden | -0.01 | -0.00 | +0.06 | +0.23 | +0.07 | -0.08 |
| Dreifachboden | +0.02 | +0.16 |  |  |  |  |
| Aufsteigendes Dreieck | +0.01 | +0.02 | +0.15 | +0.20 | +0.22 | -0.19 |
| Bullenflagge | +0.02 | +0.26 | +0.67 |  |  |  |
| Bullischer Wimpel | -0.03 | -0.02 | -0.11 | +0.12 |  |  |
| Bullischer Keil | +0.03 | -0.07 | +0.31 | +0.47 |  |  |
| Bullisches Rechteck | -0.01 | -0.08 |  |  |  |  |
| Tasse mit Henkel | +0.05 | +0.21 | -0.15 |  |  |  |
| Rounding Bottom | +0.02 | +0.03 | +0.18 | -0.07 |  |  |

**Muster gegen Kontrolle:** 0 von 88 Kombinationen signifikant nach FDR; ohne Korrektur p<5 %: 4 (Zufall: rund 4).

**Selbstähnlichkeit über Timeframes** (mittlere Rangkorrelation, nahe +1 = dasselbe Verhalten, nahe 0 = keines): roh +0.43 aus 36 Paaren, nach Abzug der Kontrolle **+0.25** aus 36 Paaren.

## 2. Ereignisstudie: alle Muster und Indikatorsignale

988 Tests, je 100,000 zufällige Verschiebungen. Nach Korrektur für viele Tests (FDR 5%) bleiben **0** übrig, davon **0** in der erwarteten Richtung.

Ohne Korrektur p<5 %: 39 Tests (bei reinem Zufall rund 49). Median aller p-Werte: 0.51 (bei reinem Zufall 0,50).

n unabh. = Ereignisse, die mindestens einen Horizont auseinanderliegen.


| Familie | Tests | Signifikant |
|---|---:|---:|
| FIB | 125 | 0 |
| MOM | 190 | 0 |
| MR | 235 | 0 |
| Muster | 438 | 0 |

## 3. Fraktale Markthypothese

H = DFA-Hurst der Renditen (0,5 = kein Gedächtnis). H |Rendite| = Gedächtnis der Schwankung. Lo = Test gegen Scheineffekte; außerhalb von 0,809 bis 1,862 ist Langzeit-Gedächtnis bei 95 % signifikant.

| TF | Bars | H | Lo | Gedächtnis? | H abs. | Lo abs. | Gedächtnis? | Zeit H>0,55 | Zeit H<0,45 |
|---|---:|---:|---:|---|---:|---:|---|---:|---:|
| 1m | 1,059,314 | 0.506 | 1.37 | nein | 0.835 | 18.50 | ja | 6% | 10% |
| 5m | 212,180 | 0.517 | 1.38 | nein | 0.816 | 11.90 | ja | 4% | 8% |
| 15m | 70,779 | 0.523 | 1.39 | nein | 0.785 | 9.17 | ja | 1% | 7% |
| 1h | 19,058 | 0.518 | 1.38 | nein | 0.763 | 6.43 | ja | 0% | 7% |
| 4h | 5,445 | 0.493 | 1.36 | nein | 0.725 | 5.33 | ja | 1% | 28% |
| 1D | 3,634 | 0.517 | 1.15 | nein | 0.752 | 4.23 | ja | 1% | 31% |
| 1W | 754 | 0.572 | 1.16 | nein | 0.759 | 2.98 | ja | 30% | 20% |
| 12D | 302 | 0.491 | 1.13 | nein | 0.710 | 2.30 | ja | – | – |
| 1M | 173 | 0.599 | 1.21 | nein | 0.723 | 2.05 | ja | – | – |

## 4. Ist Hurst der Schalter zwischen Mean Reversion und Momentum?

Rendite in Signalrichtung über dem Normalwert, getrennt nach H zum Signalzeitpunkt. Die These stimmt, wenn MR bei H<0,5 und Momentum bei H>0,5 besser abschneidet; |t| ab rund 2 ist unterscheidbar.

| TF | Familie | Horizont | n H<0,5 | Ø H<0,5 | n H>0,5 | Ø H>0,5 | t Differenz | These |
|---|---|---|---:|---:|---:|---:|---:|---|
| 1m | MR | 1T | 84,088 | +0.01 % | 70,076 | +0.00 % | -1.1 | - |
| 1m | MR | 7T | 84,082 | +0.07 % | 69,847 | -0.00 % | +0.6 | - |
| 1m | MOM | 1T | 67,527 | -0.00 % | 54,637 | +0.00 % | -0.6 | - |
| 1m | MOM | 7T | 67,524 | -0.01 % | 54,473 | +0.00 % | -0.6 | - |
| 5m | MR | 1T | 15,696 | +0.02 % | 14,759 | +0.04 % | -0.6 | - |
| 5m | MR | 7T | 15,644 | +0.08 % | 14,753 | +0.02 % | -0.7 | - |
| 5m | MOM | 1T | 11,525 | -0.01 % | 10,342 | +0.02 % | -2.6 | gestützt |
| 5m | MOM | 7T | 11,505 | -0.05 % | 10,339 | +0.04 % | -1.5 | - |
| 15m | MR | 1T | 6,677 | +0.01 % | 3,619 | +0.03 % | -0.6 | - |
| 15m | MR | 7T | 6,677 | +0.03 % | 3,598 | +0.22 % | -1.0 | - |
| 15m | MOM | 1T | 4,501 | +0.01 % | 2,241 | +0.04 % | -0.2 | - |
| 15m | MOM | 7T | 4,501 | +0.03 % | 2,234 | -0.00 % | +0.2 | - |
| 1h | MR | 1T | 1,794 | -0.01 % | 516 | +0.23 % | -0.1 | - |
| 1h | MR | 7T | 1,794 | +0.25 % | 513 | -0.03 % | +0.2 | - |
| 1h | MOM | 1T | 1,140 | +0.05 % | 353 | -0.15 % | +1.8 | - |
| 1h | MOM | 7T | 1,140 | -0.11 % | 352 | -0.08 % | -0.1 | - |
| 4h | MR | 1T | 605 | -0.14 % | 95 | +0.55 % | -2.6 | - |
| 4h | MR | 7T | 605 | -0.04 % | 95 | +1.34 % | -2.5 | - |
| 4h | MOM | 1T | 343 | +0.16 % | 109 | -0.20 % | +1.7 | - |
| 4h | MOM | 7T | 343 | +0.26 % | 109 | -0.21 % | +0.9 | - |
| 1D | MR | 1T | 326 | +0.36 % | 115 | -0.07 % | +0.9 | - |
| 1D | MR | 7T | 326 | +0.56 % | 115 | +0.06 % | +0.7 | - |
| 1D | MOM | 1T | 205 | +0.09 % | 64 | -0.29 % | +1.2 | - |
| 1D | MOM | 7T | 204 | +0.20 % | 64 | +0.49 % | -0.5 | - |
| 1W | MR | 1T | 34 | -0.65 % | 48 | -0.29 % | -0.2 | - |
| 1W | MR | 7T | 34 | -0.13 % | 48 | +0.70 % | -0.1 | - |
| 1W | MOM | 1T | 18 | -0.28 % | 32 | -0.65 % | +0.5 | - |
| 1W | MOM | 7T | 18 | +0.01 % | 32 | -0.57 % | +0.3 | - |

**Gestützt in 1 von 28 Vergleichen.**

## 5. Mean Reversion und Momentum

Rollend über 256 Bars. Stationär = ADF unter -2,86: In diesem Fenster kehrt der Kurs messbar zum Mittelwert zurück (bei reinem Zufall rund 5 % der Fenster). Variance Ratio unter 1 = Umkehr, über 1 = Trend.

| TF | Zeit stationär | Halbwertszeit (Bars) | VR 2 | VR 4 | VR 8 |
|---|---:|---:|---:|---:|---:|
| 1m | 10.3% | 32 | 0.976 | 0.943 | 0.892 |
| 5m | 6.5% | 39 | 0.981 | 0.952 | 0.918 |
| 15m | 4.8% | 40 | 0.984 | 0.968 | 0.939 |
| 1h | 4.8% | 39 | 0.993 | 0.980 | 0.963 |
| 4h | 4.7% | 41 | 0.985 | 0.953 | 0.905 |
| 1D | 2.5% | 42 | 0.966 | 0.933 | 0.826 |
| 1W | 1.8% | 73 | 0.933 | 0.950 | 1.025 |
