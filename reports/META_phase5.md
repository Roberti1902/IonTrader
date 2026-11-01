# META: Phase-5-Report

Stand 2026-10-31 09:36. Statistische Auswertung der Kursgeschichte, keine Anlageberatung.

## 1. Die Matrix heute

Stand: Handelsschluss 2026-10-30.

| Horizont | Bullish | Bearish | Basisrate | Richtung belegt? | Median | Spanne 80 % | VaR 95 | VaR 99 | Risiko geprüft? |
|---|---:|---:|---:|---|---:|---:|---:|---:|---|
| 1T | 52.2% | 47.8% | 52.5% | nein | +0.1 % | -3.3 bis +3.5 % | 4.7 % | 7.8 % | ja |
| 7T | 55.1% | 44.9% | 55.9% | nein | +0.5 % | -7.4 bis +8.2 % | 10.0 % | 15.5 % | ja |
| 1M | 61.3% | 38.7% | 61.8% | nein | +1.8 % | -13.8 bis +17.8 % | 18.7 % | 29.8 % | ja |
| 6M | 69.8% | 30.2% | 70.5% | nein | +10.2 % | -26.9 bis +57.3 % | 37.0 % | 57.1 % | nein |
| 1J | 73.2% | 26.8% | 73.3% | nein | +19.7 % | -31.8 bis +95.0 % | 44.3 % | 67.2 % | nein |

Richtung belegt heißt: Der Stack schlägt die Basisrate in Walk-Forward und Abschlussprüfung mit einem Intervall ganz über null. Diese Regel wurde nach dem ersten Blick auf die Abschlussprüfung verschärft: Vorher genügte die Abschlussprüfung allein. Risiko geprüft heißt: FHS besteht den VaR-95-Backtest auf diesem Horizont.

## 2. Abschlussprüfung auf den unangetasteten 2 Jahren

Zeitraum ab 2024-10-30. Die Modelleinstellungen wurden am 2026-10-31 vor dieser Prüfung eingefroren und danach nicht verändert. Brier Skill gegen die Basisrate, in Klammern das 95 %-Intervall; fett, wenn es ganz über null liegt.

| Quelle | 1T | 7T | 1M | 6M | 1J |
|---|---:|---:|---:|---:|---:|
| Stack | **+0.23 %** (+0.0 bis +0.4) | +0.10 % (-0.1 bis +0.3) | +0.66 % (-1.1 bis +2.4) | +0.75 % (-2.1 bis +1.1) | +0.01 % (zu wenig Fälle) |
| Monte Carlo allein | +0.12 % (-0.3 bis +0.5) | +0.60 % (-0.8 bis +1.9) | +3.42 % (-2.5 bis +8.0) | +9.78 % (-33.2 bis +15.6) | +0.51 % (zu wenig Fälle) |

| Stack im Detail | 1T | 7T | 1M | 6M | 1J |
|---|---:|---:|---:|---:|---:|
| Unabhängige Fälle | 501 | 105 | 24 | 4 | 2 |
| Ø angezeigte Bullish-Quote | 53.0 % | 56.8 % | 64.0 % | 73.9 % | 73.7 % |
| Tatsächlich gestiegen | 50.1 % | 52.3 % | 52.2 % | 48.4 % | 45.6 % |
| Zufallsstreuung bei dieser Fallzahl | ±4.5 Pkt. | ±9.7 Pkt. | ±20.4 Pkt. | ±50.0 Pkt. | ±70.4 Pkt. |
| Anzeige innerhalb der Streuung? | ja | ja | ja | ja | ja |
| Treffer Stack | 50.1 % | 52.3 % | 52.2 % | 48.4 % | 45.6 % |
| Treffer Basisrate | 50.1 % | 52.3 % | 52.2 % | 48.4 % | 45.6 % |

### Beide Prüfzeiträume zusammen

Walk-Forward und Abschlussprüfung als durchgehender Test. Das ist die aussagekräftigste Zahl dieses Reports.

| Quelle | 1T | 7T | 1M | 6M | 1J |
|---|---:|---:|---:|---:|---:|
| Stack | -0.08 % (-0.2 bis +0.1) | +0.01 % (-0.1 bis +0.1) | -0.05 % (-0.8 bis +0.7) | +0.07 % (-0.6 bis +0.5) | -0.01 % (-0.1 bis +0.0) |
| Monte Carlo allein | +0.12 % (-0.1 bis +0.3) | +0.49 % (-0.3 bis +1.2) | +2.41 % (-1.3 bis +5.4) | +12.82 % (-6.0 bis +21.8) | +3.00 % (-9.2 bis +7.2) |

| Stack im Detail | 1T | 7T | 1M | 6M | 1J |
|---|---:|---:|---:|---:|---:|
| Unabhängige Fälle | 1504 | 313 | 73 | 12 | 6 |
| Ø angezeigte Bullish-Quote | 53.3 % | 56.8 % | 63.4 % | 75.1 % | 76.2 % |
| Tatsächlich gestiegen | 51.1 % | 54.4 % | 59.2 % | 60.4 % | 56.9 % |
| Zufallsstreuung bei dieser Fallzahl | ±2.6 Pkt. | ±5.6 Pkt. | ±11.5 Pkt. | ±28.2 Pkt. | ±40.4 Pkt. |
| Anzeige innerhalb der Streuung? | ja | ja | ja | ja | ja |
| Treffer Stack | 51.1 % | 54.4 % | 59.2 % | 60.4 % | 56.9 % |
| Treffer Basisrate | 51.1 % | 54.4 % | 59.2 % | 60.4 % | 56.9 % |

### Stimmt, was angezeigt wird?

Nur Abschlussprüfung. Bei wenigen unabhängigen Fällen ist die tatsächliche Quote stark zufallsabhängig.

**1T**

| Bereich | Fälle | Unabhängig | Angezeigt | Tatsächlich |
|---|---:|---:|---:|---:|
| 50–55 % | 500 | 500 | 53.0% | 50.0% |
| 55–60 % | 1 | 1 | 55.2% | 100.0% |

**7T**

| Bereich | Fälle | Unabhängig | Angezeigt | Tatsächlich |
|---|---:|---:|---:|---:|
| 55–60 % | 497 | 105 | 56.8% | 52.3% |

**1M**

| Bereich | Fälle | Unabhängig | Angezeigt | Tatsächlich |
|---|---:|---:|---:|---:|
| 60–65 % | 355 | 23 | 63.2% | 49.3% |
| 65–70 % | 126 | 15 | 66.0% | 60.3% |

**6M**

| Bereich | Fälle | Unabhängig | Angezeigt | Tatsächlich |
|---|---:|---:|---:|---:|
| 70–75 % | 270 | 4 | 73.5% | 55.2% |
| 75–80 % | 106 | 2 | 75.1% | 31.1% |

**1J**

| Bereich | Fälle | Unabhängig | Angezeigt | Tatsächlich |
|---|---:|---:|---:|---:|
| 70–75 % | 250 | 2 | 73.7% | 45.6% |

### Spanne gegen HAR und feste Werte in der Abschlussprüfung

Pinball Skill. MC ist FHS; in Klammern das 95 %-Intervall, fett, wenn es ganz über null liegt.

| Horizont | Fälle | Unabhängig | MC gegen fest | HAR gegen fest | MC gegen HAR |
|---|---:|---:|---:|---:|---:|
| 1T | 501 | 501 | **+4.76 %** (+2.1 bis +7.6) | +1.40 % | **+3.41 %** (+0.8 bis +6.5) |
| 7T | 497 | 105 | **+5.41 %** (+2.9 bis +7.9) | +2.11 % | **+3.38 %** (+0.4 bis +6.3) |
| 1M | 481 | 24 | **+3.67 %** (+0.7 bis +6.8) | +2.33 % | +1.37 % (-1.5 bis +4.4) |
| 6M | 376 | 4 | **+7.11 %** (+4.9 bis +10.0) | -1.60 % | **+8.57 %** (+5.9 bis +13.0) |
| 1J | 250 | 2 | +9.95 % (zu wenig Fälle) | -6.35 % | +15.32 % (zu wenig Fälle) |

### Spanne und Risiko in der Abschlussprüfung

| Horizont | Fälle | Unabhängig | 80 %-Spanne roh | mit Conformal | Breite roh | Breite Conformal |
|---|---:|---:|---:|---:|---:|---:|
| 1T | 501 | 501 | 80.0% | 81.2% | 5.2 % | 5.3 % |
| 7T | 497 | 99 | 74.4% | 74.4% | 12.5 % | 12.4 % |
| 1M | 481 | 22 | 78.8% | 76.1% | 26.4 % | 25.0 % |
| 6M | 376 | 2 | 96.5% | 98.1% | 71.8 % | 76.8 % |
| 1J | 250 | 0 | 93.2% | 100.0% | 116.2 % | 137.6 % |

| Verfahren | Horizont | Kennzahl | Fälle | Erwartet | Treffer | Quote | p Kupiec | p Christoffersen | Ergebnis |
|---|---|---|---:|---:|---:|---:|---:|---:|---|
| FHS | 1T | VaR 95 | 501 | 25.1 | 22.0 | 4.4% | 0.524 | 0.296 | bestanden |
| FHS | 1T | VaR 99 | 501 | 5.0 | 3.0 | 0.6% | 0.329 | 0.610 | bestanden |
| FHS | 7T | VaR 95 | 100 | 5.0 | 3.0 | 3.0% | 0.323 | 0.559 | bestanden |
| FHS | 7T | VaR 99 | 100 | 1.0 | 1.0 | 1.0% | 1.000 | 0.990 | zu wenig Fälle |
| FHS | 1M | VaR 95 | 23 | 1.2 | 1.0 | 4.3% | 0.883 | 0.943 | zu wenig Fälle |
| FHS | 1M | VaR 99 | 23 | 0.2 | 0.0 | 0.0% | 0.497 | 0.794 | zu wenig Fälle |
| FHS | 6M | VaR 95 | 3 | 0.2 | 0.0 | 0.0% | 0.579 | 0.857 | zu wenig Fälle |
| FHS | 6M | VaR 99 | 3 | 0.0 | 0.0 | 0.0% | 0.806 | 0.970 | zu wenig Fälle |
| FHS | 1J | VaR 95 | 1 | 0.1 | 0.0 | 0.0% | 0.749 | 0.950 | zu wenig Fälle |
| FHS | 1J | VaR 99 | 1 | 0.0 | 0.0 | 0.0% | 0.887 | 0.990 | zu wenig Fälle |

## 3. Walk-Forward

Testjahre 2020-10-31 bis 2024-10-30. Das erste Jahr ab 2019-11-01 dient nur zum Lernen der Gewichte. Für jedes Testjahr gilt: Gewichte nur aus Tagen, deren Ergebnis vorher feststand. Brier Skill gegen die Basisrate, in Klammern das 95 %-Intervall; fett, wenn es ganz über null liegt.

| Quelle | 1T | 7T | 1M | 6M | 1J |
|---|---:|---:|---:|---:|---:|
| Stack | -0.23 % (-0.5 bis -0.0) | -0.03 % (-0.1 bis +0.0) | -0.42 % (-0.9 bis +0.0) | -0.27 % (-1.1 bis -0.0) | -0.02 % (-0.2 bis +0.0) |
| Monte Carlo allein | +0.12 % (-0.1 bis +0.4) | +0.43 % (-0.5 bis +1.4) | +1.88 % (-2.9 bis +5.8) | +14.35 % (-22.1 bis +24.7) | +3.97 % (-23.4 bis +8.4) |
| Stack + Isotonic | -23.55 % (-30.9 bis -17.0) | -53.24 % (-75.0 bis -31.7) | -22.45 % (-44.6 bis -5.9) | -90.44 % (-269.2 bis -53.3) | -120.79 % (-605.1 bis +0.0) |

| Stack im Detail | 1T | 7T | 1M | 6M | 1J |
|---|---:|---:|---:|---:|---:|
| Unabhängige Fälle | 1003 | 208 | 49 | 8 | 4 |
| Ø angezeigte Bullish-Quote | 53.4 % | 56.8 % | 63.1 % | 75.6 % | 77.0 % |
| Tatsächlich gestiegen | 51.6 % | 55.5 % | 62.7 % | 65.6 % | 60.6 % |
| Zufallsstreuung bei dieser Fallzahl | ±3.2 Pkt. | ±6.9 Pkt. | ±13.8 Pkt. | ±33.6 Pkt. | ±48.9 Pkt. |
| Anzeige innerhalb der Streuung? | ja | ja | ja | ja | ja |
| Treffer Stack | 51.6 % | 55.5 % | 62.7 % | 65.6 % | 60.6 % |
| Treffer Basisrate | 51.6 % | 55.5 % | 62.7 % | 65.6 % | 60.6 % |

Isotonic und Conformal werden nur genutzt, wo sie im Walk-Forward besser waren. Isotonic: bei keinem Horizont. Conformal: 1T.

### Gewichte im Stack

Abweichung von der Basisrate je Quelle. Strafe L2 = 10, vorab festgelegt. 0 heißt: Diese Quelle hat beim Lernen nichts beigetragen.

| Horizont | lstm solo | lstm universe | gru solo | gru universe | transformer solo | transformer universe | tft solo | tft universe | monte carlo | matching | muster |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1T | 0.00 | 0.00 | 0.00 | 0.17 | 0.00 | 0.21 | 0.16 | 0.00 | 0.11 | 0.25 | 0.07 |
| 7T | 0.04 | 0.00 | 0.00 | 0.00 | 0.00 | 0.18 | 0.00 | 0.00 | 0.09 | 0.11 | 0.00 |
| 1M | 0.00 | 0.00 | 0.02 | 0.01 | 0.01 | 0.12 | 0.15 | 0.07 | 0.10 | 0.03 | 0.00 |
| 6M | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.10 | 0.01 | 0.00 |
| 1J | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.02 | 0.00 | 0.00 |

### 80 %-Spanne im Walk-Forward

| Horizont | Fälle | Unabhängig | Roh | Mit Conformal | Breite roh | Breite Conformal |
|---|---:|---:|---:|---:|---:|---:|
| 1T | 1,255 | 1255 | 76.8% | 77.5% | 5.5 % | 5.5 % |
| 7T | 1,251 | 250 | 78.7% | 77.8% | 12.8 % | 12.5 % |
| 1M | 1,235 | 58 | 78.6% | 72.1% | 27.0 % | 23.6 % |
| 6M | 1,130 | 8 | 63.6% | 52.7% | 72.0 % | 54.2 % |
| 1J | 1,004 | 3 | 57.6% | 45.3% | 113.8 % | 89.3 % |

## 4. Deine Thesen für META

| These | Messung | Urteil |
|---|---|---|
| 20 Chartmuster sagen die Richtung voraus | 0 von 88 Kombinationen schlagen zufällige Einstiege | nicht gestützt |
| Fibonacci-Niveaus wirken | 0 von 125 Tests in erwarteter Richtung nach FDR; ohne Korrektur p<5 %: 6 (Zufall: rund 6) | nicht gestützt |
| Mean-Reversion-Signale wirken | 0 von 235 Tests in erwarteter Richtung nach FDR; ohne Korrektur p<5 %: 3 (Zufall: rund 12) | nicht gestützt |
| Momentum-Signale wirken | 0 von 190 Tests in erwarteter Richtung nach FDR; ohne Korrektur p<5 %: 3 (Zufall: rund 10) | nicht gestützt |
| Märkte haben Gedächtnis: Richtung | H 0.49 bis 0.60; Lo-Test auf 0 von 9 Timeframes signifikant | nicht gestützt |
| Märkte haben Gedächtnis: Schwankung | H 0.71 bis 0.83; Lo-Test auf 9 von 9 Timeframes signifikant | gestützt |
| Hurst schaltet zwischen Mean Reversion und Momentum | 1 von 28 Vergleichen stützen das | nicht gestützt |
| Mean Reversion ist häufig | Kurs in 2 bis 10 % der Fenster stationär (Zufall: rund 5 %) | nicht gestützt |
| LSTM, GRU, Transformer und TFT sagen die Richtung voraus | 0 von 40 Modell-Horizont-Kombinationen liegen mit dem Intervall über der Basisrate | nicht gestützt |
| Monte Carlo erfasst das Risiko | FHS besteht 4 von 4 testbaren VaR-Backtests | gestützt |

## Setup: Welche Indikatoren helfen bei diesem Ticker?

5,304 Tests: jeder Indikator gegen die spätere Rendite (Richtung) und ihren Betrag (Schwankung), je Timeframe und Horizont, mit je 5,000 Verschiebungen. IC ist die Rangkorrelation, q die Fehlerquote nach Korrektur für viele Tests.

### Richtung: 1 von 1,592 Tests signifikant bei 1 Tag, 7 Tagen und 1 Monat

Bei 6 Monaten und 1 Jahr zusätzlich 3 von 1,060; das stützt sich aber nur auf wenige unabhängige Zeiträume und zählt hier nicht.

| Indikator | Timeframe | Horizont | IC | q |
|---|---|---|---:|---:|
| fib_near_k8 | 1W | 1M | -0.182 | 0.0486 |

Am häufigsten signifikant:

| Indikator | Treffer | Ø |IC| |
|---|---:|---:|
| fib_near_k8 | 1 | 0.182 |

### Schwankung: 209 von 1,592 Tests signifikant bei 1 Tag, 7 Tagen und 1 Monat

Bei 6 Monaten und 1 Jahr zusätzlich 27 von 1,060; das stützt sich aber nur auf wenige unabhängige Zeiträume und zählt hier nicht.

| Indikator | Timeframe | Horizont | IC | q |
|---|---|---|---:|---:|
| atr_pct | 15m | 1T | +0.330 | 0.0420 |
| ema200_d | 1W | 1M | -0.310 | 0.0118 |
| atr_pct | 5m | 1T | +0.296 | 0.0331 |
| sma200_d | 1W | 1M | -0.267 | 0.0118 |
| atr_pct | 1m | 1T | +0.267 | 0.0299 |
| fib_618_k8 | 4h | 1M | -0.262 | 0.0118 |
| fib_382_k8 | 1D | 1M | -0.260 | 0.0118 |
| ema200_d | 1W | 7T | -0.254 | 0.0118 |
| fib_382_k3 | 1W | 1M | -0.242 | 0.0465 |
| fib_618_k5 | 1D | 1M | -0.228 | 0.0118 |
| sma200_d | 1W | 7T | -0.221 | 0.0118 |
| bb_width | 15m | 1T | +0.220 | 0.0299 |

Am häufigsten signifikant:

| Indikator | Treffer | Ø |IC| |
|---|---:|---:|
| fib_382_k3 | 9 | 0.131 |
| fib_382_k2 | 9 | 0.078 |
| ema200_d | 9 | 0.182 |
| sma200_d | 8 | 0.164 |
| minus_di | 8 | 0.117 |
| fib_618_k5 | 8 | 0.158 |
| fib_618_k1.5 | 8 | 0.121 |
| fib_382_k8 | 7 | 0.144 |
| rsi14 | 7 | 0.137 |
| fib_618_k3 | 7 | 0.130 |
| fib_618_k8 | 7 | 0.158 |
| stoch_k | 6 | 0.072 |

Die Ränge zeigen einen Zusammenhang über die gesamte Historie, keine Handelsregel.

