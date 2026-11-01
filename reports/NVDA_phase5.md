# NVDA: Phase-5-Report

Stand 2026-10-31 14:48. Statistische Auswertung der Kursgeschichte, keine Anlageberatung.

## 1. Die Matrix heute

Stand: Handelsschluss 2026-10-30.

| Horizont | Bullish | Bearish | Basisrate | Richtung belegt? | Median | Spanne 80 % | VaR 95 | VaR 99 | Risiko geprüft? |
|---|---:|---:|---:|---|---:|---:|---:|---:|---|
| 1T | 52.8% | 47.2% | 54.1% | nein | +0.2 % | -3.0 bis +3.2 % | 3.9 % | 6.0 % | nein |
| 7T | 58.6% | 41.4% | 58.9% | nein | +0.7 % | -6.5 bis +7.5 % | 8.4 % | 13.5 % | ja |
| 1M | 66.0% | 34.0% | 66.9% | nein | +3.8 % | -15.3 bis +23.6 % | 20.7 % | 33.6 % | ja |
| 6M | 82.3% | 17.7% | 82.5% | nein | +16.6 % | -41.4 bis +85.0 % | 37.2 % | 62.1 % | nein |
| 1J | 82.0% | 18.0% | 82.0% | nein | +33.5 % | -94.2 bis +196.8 % | 47.5 % | 75.9 % | nein |

Richtung belegt heißt: Der Stack schlägt die Basisrate in Walk-Forward und Abschlussprüfung mit einem Intervall ganz über null. Diese Regel wurde nach dem ersten Blick auf die Abschlussprüfung verschärft: Vorher genügte die Abschlussprüfung allein. Risiko geprüft heißt: FHS besteht den VaR-95-Backtest auf diesem Horizont.

## 2. Abschlussprüfung auf den unangetasteten 2 Jahren

Zeitraum ab 2024-10-30. Die Modelleinstellungen wurden am 2026-10-31 vor dieser Prüfung eingefroren und danach nicht verändert. Brier Skill gegen die Basisrate, in Klammern das 95 %-Intervall; fett, wenn es ganz über null liegt.

| Quelle | 1T | 7T | 1M | 6M | 1J |
|---|---:|---:|---:|---:|---:|
| Stack | +0.21 % (-0.1 bis +0.6) | +0.02 % (-0.1 bis +0.2) | +0.67 % (-0.5 bis +1.5) | -0.46 % (-1.5 bis -0.2) | -0.14 % (zu wenig Fälle) |
| Monte Carlo allein | +0.26 % (-0.5 bis +1.0) | -0.10 % (-3.0 bis +2.6) | +4.10 % (-5.9 bis +11.5) | -37.77 % (-97.9 bis -22.2) | -64.14 % (zu wenig Fälle) |

| Stack im Detail | 1T | 7T | 1M | 6M | 1J |
|---|---:|---:|---:|---:|---:|
| Unabhängige Fälle | 501 | 105 | 24 | 4 | 2 |
| Ø angezeigte Bullish-Quote | 54.3 % | 59.4 % | 67.0 % | 81.6 % | 77.4 % |
| Tatsächlich gestiegen | 52.3 % | 56.1 % | 57.8 % | 88.3 % | 99.6 % |
| Zufallsstreuung bei dieser Fallzahl | ±4.5 Pkt. | ±9.7 Pkt. | ±20.2 Pkt. | ±32.1 Pkt. | ±14.1 Pkt. |
| Anzeige innerhalb der Streuung? | ja | ja | ja | ja | **nein** |
| Treffer Stack | 52.3 % | 56.1 % | 57.8 % | 88.3 % | 99.6 % |
| Treffer Basisrate | 52.3 % | 56.1 % | 57.8 % | 88.3 % | 99.6 % |

### Beide Prüfzeiträume zusammen

Walk-Forward und Abschlussprüfung als durchgehender Test. Das ist die aussagekräftigste Zahl dieses Reports.

| Quelle | 1T | 7T | 1M | 6M | 1J |
|---|---:|---:|---:|---:|---:|
| Stack | +0.04 % (-0.1 bis +0.2) | -0.13 % (-0.3 bis +0.0) | -0.18 % (-0.9 bis +0.4) | -0.57 % (-2.2 bis -0.1) | -0.04 % (-0.3 bis +0.0) |
| Monte Carlo allein | +0.16 % (-0.4 bis +0.7) | +0.10 % (-1.9 bis +2.0) | +3.37 % (-4.7 bis +9.4) | -9.41 % (-104.7 bis +22.0) | -10.89 % (-68.5 bis +3.0) |

| Stack im Detail | 1T | 7T | 1M | 6M | 1J |
|---|---:|---:|---:|---:|---:|
| Unabhängige Fälle | 1504 | 313 | 73 | 12 | 6 |
| Ø angezeigte Bullish-Quote | 54.6 % | 59.6 % | 68.3 % | 81.8 % | 76.4 % |
| Tatsächlich gestiegen | 53.4 % | 57.3 % | 61.9 % | 81.9 % | 80.9 % |
| Zufallsstreuung bei dieser Fallzahl | ±2.6 Pkt. | ±5.6 Pkt. | ±11.4 Pkt. | ±22.2 Pkt. | ±32.1 Pkt. |
| Anzeige innerhalb der Streuung? | ja | ja | ja | ja | ja |
| Treffer Stack | 53.4 % | 57.3 % | 61.9 % | 81.9 % | 80.9 % |
| Treffer Basisrate | 53.4 % | 57.3 % | 61.9 % | 81.9 % | 80.9 % |

### Stimmt, was angezeigt wird?

Nur Abschlussprüfung. Bei wenigen unabhängigen Fällen ist die tatsächliche Quote stark zufallsabhängig.

**1T**

| Bereich | Fälle | Unabhängig | Angezeigt | Tatsächlich |
|---|---:|---:|---:|---:|
| 50–55 % | 390 | 390 | 53.9% | 51.5% |
| 55–60 % | 111 | 111 | 55.6% | 55.0% |

**7T**

| Bereich | Fälle | Unabhängig | Angezeigt | Tatsächlich |
|---|---:|---:|---:|---:|
| 55–60 % | 497 | 105 | 59.4% | 56.1% |

**1M**

| Bereich | Fälle | Unabhängig | Angezeigt | Tatsächlich |
|---|---:|---:|---:|---:|
| 65–70 % | 481 | 24 | 67.0% | 57.8% |

**6M**

| Bereich | Fälle | Unabhängig | Angezeigt | Tatsächlich |
|---|---:|---:|---:|---:|
| 80–100 % | 376 | 4 | 81.6% | 88.3% |

**1J**

| Bereich | Fälle | Unabhängig | Angezeigt | Tatsächlich |
|---|---:|---:|---:|---:|
| 75–80 % | 250 | 2 | 77.4% | 99.6% |

### Spanne gegen HAR und feste Werte in der Abschlussprüfung

Pinball Skill. MC ist FHS; in Klammern das 95 %-Intervall, fett, wenn es ganz über null liegt.

| Horizont | Fälle | Unabhängig | MC gegen fest | HAR gegen fest | MC gegen HAR |
|---|---:|---:|---:|---:|---:|
| 1T | 501 | 501 | +0.78 % (-1.6 bis +3.0) | +1.70 % | -0.94 % (-3.0 bis +1.2) |
| 7T | 497 | 105 | +0.95 % (-1.8 bis +3.5) | +2.24 % | -1.32 % (-3.9 bis +1.2) |
| 1M | 481 | 24 | +5.14 % (-0.2 bis +10.4) | +1.04 % | +4.15 % (-1.7 bis +9.7) |
| 6M | 376 | 4 | **+25.88 %** (+5.5 bis +40.7) | -8.80 % | **+31.88 %** (+10.0 bis +44.7) |
| 1J | 250 | 2 | +40.70 % (zu wenig Fälle) | -0.14 % | +40.79 % (zu wenig Fälle) |

### Spanne und Risiko in der Abschlussprüfung

| Horizont | Fälle | Unabhängig | 80 %-Spanne roh | mit Conformal | Breite roh | Breite Conformal |
|---|---:|---:|---:|---:|---:|---:|
| 1T | 501 | 501 | 80.8% | 83.2% | 6.6 % | 7.2 % |
| 7T | 497 | 99 | 82.3% | 86.3% | 15.9 % | 17.1 % |
| 1M | 481 | 22 | 94.8% | 97.1% | 34.9 % | 38.3 % |
| 6M | 376 | 2 | 100.0% | 100.0% | 105.1 % | 147.4 % |
| 1J | 250 | 0 | 100.0% | 100.0% | 188.1 % | 350.4 % |

| Verfahren | Horizont | Kennzahl | Fälle | Erwartet | Treffer | Quote | p Kupiec | p Christoffersen | Ergebnis |
|---|---|---|---:|---:|---:|---:|---:|---:|---|
| FHS | 1T | VaR 95 | 501 | 25.1 | 29.0 | 5.8% | 0.429 | 0.139 | bestanden |
| FHS | 1T | VaR 99 | 501 | 5.0 | 3.0 | 0.6% | 0.329 | 0.610 | bestanden |
| FHS | 7T | VaR 95 | 100 | 5.0 | 4.0 | 4.0% | 0.635 | 0.755 | bestanden |
| FHS | 7T | VaR 99 | 100 | 1.0 | 1.0 | 1.0% | 1.000 | 0.990 | zu wenig Fälle |
| FHS | 1M | VaR 95 | 23 | 1.2 | 0.0 | 0.0% | 0.125 | 0.307 | zu wenig Fälle |
| FHS | 1M | VaR 99 | 23 | 0.2 | 0.0 | 0.0% | 0.497 | 0.794 | zu wenig Fälle |
| FHS | 6M | VaR 95 | 3 | 0.2 | 0.0 | 0.0% | 0.579 | 0.857 | zu wenig Fälle |
| FHS | 6M | VaR 99 | 3 | 0.0 | 0.0 | 0.0% | 0.806 | 0.970 | zu wenig Fälle |
| FHS | 1J | VaR 95 | 1 | 0.1 | 0.0 | 0.0% | 0.749 | 0.950 | zu wenig Fälle |
| FHS | 1J | VaR 99 | 1 | 0.0 | 0.0 | 0.0% | 0.887 | 0.990 | zu wenig Fälle |

## 3. Walk-Forward

Testjahre 2020-10-31 bis 2024-10-30. Das erste Jahr ab 2019-11-01 dient nur zum Lernen der Gewichte. Für jedes Testjahr gilt: Gewichte nur aus Tagen, deren Ergebnis vorher feststand. Brier Skill gegen die Basisrate, in Klammern das 95 %-Intervall; fett, wenn es ganz über null liegt.

| Quelle | 1T | 7T | 1M | 6M | 1J |
|---|---:|---:|---:|---:|---:|
| Stack | -0.04 % (-0.2 bis +0.1) | -0.21 % (-0.4 bis -0.0) | -0.63 % (-1.5 bis +0.2) | -0.60 % (-3.8 bis -0.1) | -0.03 % (-0.3 bis +0.0) |
| Monte Carlo allein | +0.11 % (-0.7 bis +0.8) | +0.20 % (-2.4 bis +2.5) | +2.99 % (-8.0 bis +11.3) | -2.15 % (-166.1 bis +27.5) | -5.92 % (-67.7 bis +6.6) |
| Stack + Isotonic | -7.62 % (-12.3 bis -3.3) | -24.43 % (-41.8 bis -8.4) | -87.88 % (-173.7 bis -27.3) | -50.94 % (-188.3 bis -36.0) | -27.89 % (-149.9 bis +0.1) |

| Stack im Detail | 1T | 7T | 1M | 6M | 1J |
|---|---:|---:|---:|---:|---:|
| Unabhängige Fälle | 1003 | 208 | 49 | 8 | 4 |
| Ø angezeigte Bullish-Quote | 54.7 % | 59.7 % | 68.9 % | 81.9 % | 76.0 % |
| Tatsächlich gestiegen | 53.9 % | 57.9 % | 63.9 % | 79.2 % | 74.7 % |
| Zufallsstreuung bei dieser Fallzahl | ±3.1 Pkt. | ±6.8 Pkt. | ±13.7 Pkt. | ±28.7 Pkt. | ±43.5 Pkt. |
| Anzeige innerhalb der Streuung? | ja | ja | ja | ja | ja |
| Treffer Stack | 53.9 % | 57.9 % | 63.9 % | 79.2 % | 74.7 % |
| Treffer Basisrate | 53.9 % | 57.9 % | 63.9 % | 79.2 % | 74.7 % |

Isotonic und Conformal werden nur genutzt, wo sie im Walk-Forward besser waren. Isotonic: bei keinem Horizont. Conformal: 1T, 7T, 1M, 6M, 1J.

### Gewichte im Stack

Abweichung von der Basisrate je Quelle. Strafe L2 = 10, vorab festgelegt. 0 heißt: Diese Quelle hat beim Lernen nichts beigetragen.

| Horizont | lstm solo | lstm universe | gru solo | gru universe | transformer solo | transformer universe | tft solo | tft universe | monte carlo | matching | muster |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1T | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.17 | 0.29 | 0.00 |
| 7T | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.08 | 0.04 | 0.00 |
| 1M | 0.00 | 0.00 | 0.00 | 0.02 | 0.00 | 0.03 | 0.00 | 0.00 | 0.16 | 0.04 | 0.00 |
| 6M | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.01 | 0.00 | 0.00 |
| 1J | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |

### 80 %-Spanne im Walk-Forward

| Horizont | Fälle | Unabhängig | Roh | Mit Conformal | Breite roh | Breite Conformal |
|---|---:|---:|---:|---:|---:|---:|
| 1T | 1,255 | 1255 | 73.9% | 75.7% | 7.2 % | 7.4 % |
| 7T | 1,251 | 250 | 76.4% | 77.8% | 16.9 % | 17.7 % |
| 1M | 1,235 | 58 | 74.9% | 77.9% | 36.6 % | 39.0 % |
| 6M | 1,130 | 8 | 59.5% | 77.2% | 105.1 % | 147.5 % |
| 1J | 1,004 | 3 | 50.4% | 77.7% | 178.9 % | 357.4 % |

## 4. Deine Thesen für NVDA

| These | Messung | Urteil |
|---|---|---|
| 20 Chartmuster sagen die Richtung voraus | 0 von 92 Kombinationen schlagen zufällige Einstiege | nicht gestützt |
| Fibonacci-Niveaus wirken | 0 von 140 Tests in erwarteter Richtung nach FDR; ohne Korrektur p<5 %: 2 (Zufall: rund 7) | nicht gestützt |
| Mean-Reversion-Signale wirken | 0 von 240 Tests in erwarteter Richtung nach FDR; ohne Korrektur p<5 %: 4 (Zufall: rund 12) | nicht gestützt |
| Momentum-Signale wirken | 0 von 220 Tests in erwarteter Richtung nach FDR; ohne Korrektur p<5 %: 8 (Zufall: rund 11) | nicht gestützt |
| Märkte haben Gedächtnis: Richtung | H 0.50 bis 0.57; Lo-Test auf 0 von 9 Timeframes signifikant | nicht gestützt |
| Märkte haben Gedächtnis: Schwankung | H 0.69 bis 0.86; Lo-Test auf 9 von 9 Timeframes signifikant | gestützt |
| Hurst schaltet zwischen Mean Reversion und Momentum | 0 von 28 Vergleichen stützen das | nicht gestützt |
| Mean Reversion ist häufig | Kurs in 3 bis 11 % der Fenster stationär (Zufall: rund 5 %) | nicht gestützt |
| LSTM, GRU, Transformer und TFT sagen die Richtung voraus | 0 von 40 Modell-Horizont-Kombinationen liegen mit dem Intervall über der Basisrate | nicht gestützt |
| Monte Carlo erfasst das Risiko | FHS besteht 2 von 4 testbaren VaR-Backtests | teilweise |

## Setup: Welche Indikatoren helfen bei diesem Ticker?

5,930 Tests: jeder Indikator gegen die spätere Rendite (Richtung) und ihren Betrag (Schwankung), je Timeframe und Horizont, mit je 5,000 Verschiebungen. IC ist die Rangkorrelation, q die Fehlerquote nach Korrektur für viele Tests.

### Richtung: 0 von 1,786 Tests signifikant bei 1 Tag, 7 Tagen und 1 Monat

Bei 6 Monaten und 1 Jahr zusätzlich 1 von 1,179; das stützt sich aber nur auf wenige unabhängige Zeiträume und zählt hier nicht.

Kein Indikator übersteht die Korrektur.

### Schwankung: 242 von 1,786 Tests signifikant bei 1 Tag, 7 Tagen und 1 Monat

Bei 6 Monaten und 1 Jahr zusätzlich 4 von 1,179; das stützt sich aber nur auf wenige unabhängige Zeiträume und zählt hier nicht.

| Indikator | Timeframe | Horizont | IC | q |
|---|---|---|---:|---:|
| fib_dir_k3 | 12D | 1T | +0.290 | 0.0097 |
| fib_382_k2 | 12D | 1T | -0.285 | 0.0097 |
| atr_pct | 15m | 1T | +0.272 | 0.0352 |
| rsi14 | 12D | 1T | -0.269 | 0.0097 |
| bb_pct | 12D | 1T | -0.247 | 0.0097 |
| zscore20 | 12D | 1T | -0.247 | 0.0097 |
| fib_382_k1.5 | 12D | 1T | -0.240 | 0.0097 |
| atr_pct | 5m | 1T | +0.237 | 0.0392 |
| fib_382_k2 | 1W | 7T | -0.233 | 0.0213 |
| stoch_k | 12D | 1T | -0.224 | 0.0097 |
| fib_dir_k2 | 12D | 1T | +0.222 | 0.0418 |
| atr_pct | 1m | 1T | +0.212 | 0.0262 |

Am häufigsten signifikant:

| Indikator | Treffer | Ø |IC| |
|---|---:|---:|
| fib_382_k2 | 9 | 0.159 |
| fib_382_k5 | 9 | 0.155 |
| rsi14 | 9 | 0.148 |
| fib_382_k1.5 | 8 | 0.139 |
| plus_di | 8 | 0.115 |
| minus_di | 8 | 0.137 |
| ema20_d | 7 | 0.112 |
| fib_382_k3 | 7 | 0.126 |
| fib_618_k5 | 7 | 0.138 |
| ema50_d | 7 | 0.117 |
| fib_618_k2 | 7 | 0.126 |
| fib_618_k3 | 7 | 0.125 |

Die Ränge zeigen einen Zusammenhang über die gesamte Historie, keine Handelsregel.

