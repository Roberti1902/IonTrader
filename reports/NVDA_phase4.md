# NVDA: Phase-4-Report

Stand 2026-10-31 10:56. Letzter Handelsschluss: 2026-10-30, Kurs 204.64 $.

Statistische Auswertung der Kursgeschichte, keine Anlageberatung.

## 1. Aktuelles Risikobild

Filtered Historical Simulation mit 1,000,000 Pfaden. Nächste geschätzte Earnings-Reaktion: 2026-11-18.

| Horizont | VaR 95 | VaR 99 | CVaR 95 | CVaR 99 | Spanne 10–90 % | Median | P(steigt) | Drawdown 95 % |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1T | -3.9 % | -6.0 % | -5.3 % | -7.7 % | -2.8 % bis +3.0 % | +0.2 % | 53.2% | -3.9 % |
| 7T | -8.4 % | -13.5 % | -11.7 % | -17.3 % | -6.1 % bis +7.2 % | +0.7 % | 55.4% | -9.8 % |
| 1M | -20.7 % | -33.6 % | -28.7 % | -40.7 % | -14.6 % bis +22.9 % | +3.8 % | 61.0% | -26.2 % |
| 6M | -37.2 % | -62.1 % | -52.2 % | -75.1 % | -25.4 % bis +69.0 % | +16.6 % | 68.8% | -54.7 % |
| 1J | -47.5 % | -75.9 % | -64.3 % | -86.6 % | -31.8 % bis +134.4 % | +33.5 % | 72.7% | -70.2 % |

VaR 95 heißt: In 95 % der Pfade ist die Rendite über diesem Wert. CVaR ist der Durchschnitt der schlechtesten 5 % bzw. 1 %. Drawdown ist der größte zwischenzeitliche Rückgang bis zum Horizont.

## 2. Was die einzelnen Bausteine ausmachen

VaR 99 je Variante. Rekordniveau setzt Markt, Sektor und Eigenanteil gleichzeitig auf ihre jeweils höchste bisherige Schwankung; das ist ein bewusst extremes Szenario, keine Erwartung.

| Horizont | Basis | Ohne Earnings-Sprünge | Schwankung auf Rekordniveau | Block-Bootstrap |
|---|---:|---:|---:|---:|
| 1T | -6.0 % | -6.6 % | -38.0 % | -9.3 % |
| 7T | -13.5 % | -14.7 % | -66.6 % | -20.7 % |
| 1M | -33.6 % | -29.4 % | -90.7 % | -36.1 % |
| 6M | -62.1 % | -61.0 % | -99.6 % | -57.6 % |
| 1J | -75.9 % | -74.7 % | -99.9 % | -66.2 % |

## 3. Stresstests

Ausgangskurs 204.64 $. Über Betas: Markt-Einbruch umgerechnet mit den heutigen Betas aus dem Graphen, ohne Eigenanteil der Aktie. Vor dem Start des Sektor-ETF zählt nur das Marktbeta; der tatsächliche Verlust einer Aktie kann deutlich höher liegen.

| Art | Von | Bis | Handelstage | Markt | Basis | Wirkung | Kurs |
|---|---|---|---:|---:|---|---:|---:|
| Eigene Historie | 2002-01-03 | 2002-10-09 | 193 | – | echter Verlauf | -89.7 % | 21 $ |
| Eigene Historie | 2007-10-17 | 2008-11-20 | 277 | – | echter Verlauf | -85.1 % | 31 $ |
| Eigene Historie | 2000-06-21 | 2000-12-21 | 128 | – | echter Verlauf | -67.8 % | 66 $ |
| Eigene Historie | 2021-11-29 | 2022-10-14 | 221 | – | echter Verlauf | -66.3 % | 69 $ |
| Eigene Historie | 2004-04-05 | 2004-08-06 | 85 | – | echter Verlauf | -65.4 % | 71 $ |
| Markt-Einbruch über Betas | 2007-10-09 | 2009-03-09 | 355 | -55.2 % | Markt + Sektor | -61.3 % | 79 $ |
| Markt-Einbruch über Betas | 2000-03-24 | 2002-10-09 | 637 | -47.5 % | Markt + Sektor | -81.5 % | 38 $ |
| Markt-Einbruch über Betas | 2020-02-19 | 2020-03-23 | 23 | -33.7 % | Markt + Sektor | -38.7 % | 125 $ |
| Markt-Einbruch über Betas | 2022-01-03 | 2022-10-12 | 195 | -24.5 % | Markt + Sektor | -36.6 % | 130 $ |
| Markt-Einbruch über Betas | 2018-09-20 | 2018-12-24 | 65 | -19.3 % | Markt + Sektor | -26.5 % | 150 $ |

## 4. Take Profit vor Stop Loss

Geprüft jeweils zum Tagesschluss, Treffer innerhalb des Tages sind nicht erfasst.

| TP | SL | Horizont | TP zuerst | SL zuerst | Keines |
|---:|---:|---|---:|---:|---:|
| +5% | -5% | 1M | 56.2% | 41.0% | 2.8% |
| +5% | -5% | 6M | 57.9% | 42.1% | 0.0% |
| +10% | -5% | 1M | 38.2% | 48.4% | 13.3% |
| +10% | -5% | 6M | 46.3% | 53.7% | 0.0% |
| +20% | -10% | 1M | 16.7% | 28.0% | 55.3% |
| +20% | -10% | 6M | 50.2% | 47.3% | 2.4% |

## 5. VaR-Backtest außerhalb der Trainingsdaten

2,221 Handelstage von 2016-01-04 bis 2024-10-29. Für jeden Tag wurde das Modell nur mit der Vergangenheit neu geschätzt. Getestet wird auf Stichtagen ohne Überlappung. Bestanden heißt: Kupiec und Christoffersen liegen beide bei p ≥ 5 %. Die letzten 2 Jahre bleiben unangetastet.

| Verfahren | Horizont | Kennzahl | Fälle | Erwartet | Treffer | Quote | p Kupiec | p Christoffersen | Ergebnis |
|---|---|---|---:|---:|---:|---:|---:|---:|---|
| FHS | 1T | VaR 95 | 2,220 | 111.0 | 132.0 | 5.9% | 0.047 | 0.073 | **durchgefallen** |
| FHS | 1T | VaR 99 | 2,220 | 22.2 | 33.0 | 1.5% | 0.032 | 0.060 | **durchgefallen** |
| FHS | 7T | VaR 95 | 444 | 22.2 | 23.0 | 5.2% | 0.862 | 0.975 | bestanden |
| FHS | 7T | VaR 99 | 444 | 4.4 | 4.0 | 0.9% | 0.831 | 0.942 | zu wenig Fälle |
| FHS | 1M | VaR 95 | 105 | 5.2 | 5.0 | 4.8% | 0.910 | 0.772 | bestanden |
| FHS | 1M | VaR 99 | 105 | 1.1 | 1.0 | 1.0% | 0.961 | 0.989 | zu wenig Fälle |
| FHS | 6M | VaR 95 | 17 | 0.9 | 2.0 | 11.8% | 0.272 | 0.411 | zu wenig Fälle |
| FHS | 6M | VaR 99 | 17 | 0.2 | 0.0 | 0.0% | 0.559 | 0.843 | zu wenig Fälle |
| FHS | 1J | VaR 95 | 8 | 0.4 | 0.0 | 0.0% | 0.365 | 0.663 | zu wenig Fälle |
| FHS | 1J | VaR 99 | 8 | 0.1 | 0.0 | 0.0% | 0.688 | 0.923 | zu wenig Fälle |
| Block | 1T | VaR 95 | 2,220 | 111.0 | 81.0 | 3.6% | 0.002 | 0.008 | **durchgefallen** |
| Block | 1T | VaR 99 | 2,220 | 22.2 | 7.0 | 0.3% | 0.000 | 0.000 | **durchgefallen** |
| Block | 7T | VaR 95 | 444 | 22.2 | 13.0 | 2.9% | 0.030 | 0.065 | **durchgefallen** |
| Block | 7T | VaR 99 | 444 | 4.4 | 0.0 | 0.0% | 0.003 | 0.012 | zu wenig Fälle |
| Block | 1M | VaR 95 | 105 | 5.2 | 3.0 | 2.9% | 0.275 | 0.504 | bestanden |
| Block | 1M | VaR 99 | 105 | 1.1 | 0.0 | 0.0% | 0.146 | 0.348 | zu wenig Fälle |
| Block | 6M | VaR 95 | 17 | 0.9 | 1.0 | 5.9% | 0.871 | 0.923 | zu wenig Fälle |
| Block | 6M | VaR 99 | 17 | 0.2 | 0.0 | 0.0% | 0.559 | 0.843 | zu wenig Fälle |
| Block | 1J | VaR 95 | 8 | 0.4 | 1.0 | 12.5% | 0.409 | 0.602 | zu wenig Fälle |
| Block | 1J | VaR 99 | 8 | 0.1 | 0.0 | 0.0% | 0.688 | 0.923 | zu wenig Fälle |

6 Monate und 1 Jahr sind damit nicht belegt: Dafür gibt es zu wenige unabhängige Zeiträume. Die Treffer dort deuten eher auf ein zu kleines als auf ein zu großes Risiko hin.

Anteil der Fälle innerhalb der 80 %-Spanne (Ziel 80 %):

| Verfahren | 1T | 7T | 1M | 6M | 1J |
|---|---:|---:|---:|---:|---:|
| Block | 84.0% | 83.8% | 81.0% | 70.6% | 62.5% |
| FHS | 76.3% | 78.4% | 75.2% | 64.7% | 50.0% |

## 6. Monte Carlo gegen die Modelle aus Phase 3

Dieselben Testjahre, je Tag zum Handelsschluss. MC ist hier FHS. Skill in Prozent, in Klammern das 95 %-Intervall; fett, wenn es ganz über null liegt. Bei 6 Monaten und 1 Jahr stehen nur wenige unabhängige Zeiträume dahinter, die Intervalle sind dort trotz Fettdruck nicht belastbar.

| Horizont | Fälle | Unabhängig | Spanne: MC gegen fest | Block gegen fest | HAR gegen fest | Spanne: MC gegen HAR | Richtung: MC gegen Basisrate |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1T | 1,255 | 1255 | **+4.47 %** (+2.7 bis +6.4) | +2.22 % | +4.24 % | +0.23 % (-1.4 bis +2.0) | -0.06 % (-0.7 bis +0.6) |
| 7T | 1,251 | 260 | +1.57 % (-0.9 bis +4.0) | +0.67 % | +1.30 % | +0.27 % (-2.2 bis +2.7) | -0.86 % (-3.2 bis +1.3) |
| 1M | 1,235 | 61 | -0.44 % (-5.7 bis +4.5) | +0.48 % | -0.15 % | -0.30 % (-5.7 bis +4.5) | -1.56 % (-13.3 bis +6.9) |
| 6M | 1,130 | 10 | -7.28 % (-30.8 bis +13.5) | -2.75 % | -3.56 % | -3.59 % (-28.5 bis +14.0) | -12.35 % (-153.1 bis +22.3) |
| 1J | 1,004 | 5 | -28.65 % (-67.8 bis +6.0) | -17.71 % | -3.92 % | -23.79 % (-59.6 bis +7.6) | -1.82 % (-33.3 bis +10.2) |

## 7. Beziehungsgraph

Sektor von NVDA: XLK. Betas zum letzten Stichtag (2026-10-30): Markt 1.93, Sektor über den Markt hinaus 0.82 (gemessen an XLK). Hat der Ticker selbst großes Gewicht im Sektor-ETF, misst das Sektor-Beta teils die Aktie selbst.

Über den Sektor erreichbar: AAPL, CSCO, IBM, INTC, MSFT, ORCL, XLK.

| Stärkste Korrelation | Wert | Stärkster Vorlauf | Wert |
|---|---:|---|---:|
| XLK | +0.73 | BA | -0.14 |
| QQQ | +0.69 | MRK | -0.13 |
| SPY | +0.66 | INTC | -0.13 |
| ^VIX | -0.54 | GILD | -0.13 |
| ORCL | +0.44 | ^TNX | +0.13 |

Vorlauf: Korrelation von NVDA heute mit dem Ziel morgen. Bei 252 Tagen liegt schon ein einzelner Zufallswert in 95 % der Fälle bis ±0,12, und hier ist das Maximum aus 45 Paaren gelistet. Die Vorlauf-Werte sind deshalb kein Beleg für einen Zusammenhang.

## 8. Laufzeit

1,000,000 Pfade x 252 Schritte: 0.47 s, 1.0 GB Grafikspeicher. 10,000,000 Pfade in Portionen: 3.9 s.
