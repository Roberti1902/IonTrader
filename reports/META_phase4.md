# META: Phase-4-Report

Stand 2026-10-31 00:20. Letzter Handelsschluss: 2026-10-30, Kurs 614.99 $.

Statistische Auswertung der Kursgeschichte, keine Anlageberatung.

## 1. Aktuelles Risikobild

Filtered Historical Simulation mit 1,000,000 Pfaden. Nächste geschätzte Earnings-Reaktion: 2027-01-28.

| Horizont | VaR 95 | VaR 99 | CVaR 95 | CVaR 99 | Spanne 10–90 % | Median | P(steigt) | Drawdown 95 % |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1T | -4.7 % | -7.8 % | -6.5 % | -9.2 % | -3.2 % bis +3.4 % | +0.1 % | 51.8% | -4.7 % |
| 7T | -10.0 % | -15.5 % | -13.5 % | -19.1 % | -7.4 % bis +8.2 % | +0.5 % | 53.5% | -11.6 % |
| 1M | -18.7 % | -29.8 % | -25.8 % | -38.0 % | -13.8 % bis +17.8 % | +1.8 % | 56.1% | -24.0 % |
| 6M | -37.0 % | -57.1 % | -49.5 % | -68.9 % | -26.9 % bis +57.3 % | +10.2 % | 63.0% | -50.8 % |
| 1J | -44.3 % | -67.2 % | -58.3 % | -78.5 % | -31.8 % bis +95.0 % | +19.7 % | 67.1% | -62.1 % |

VaR 95 heißt: In 95 % der Pfade ist die Rendite über diesem Wert. CVaR ist der Durchschnitt der schlechtesten 5 % bzw. 1 %. Drawdown ist der größte zwischenzeitliche Rückgang bis zum Horizont.

## 2. Was die einzelnen Bausteine ausmachen

VaR 99 je Variante. Rekordniveau setzt Markt, Sektor und Eigenanteil gleichzeitig auf ihre jeweils höchste bisherige Schwankung; das ist ein bewusst extremes Szenario, keine Erwartung.

| Horizont | Basis | Ohne Earnings-Sprünge | Schwankung auf Rekordniveau | Block-Bootstrap |
|---|---:|---:|---:|---:|
| 1T | -7.8 % | -8.2 % | -28.8 % | -6.4 % |
| 7T | -15.5 % | -17.8 % | -55.3 % | -13.9 % |
| 1M | -29.8 % | -34.6 % | -82.2 % | -30.4 % |
| 6M | -57.1 % | -63.0 % | -93.5 % | -43.3 % |
| 1J | -67.2 % | -74.2 % | -94.3 % | -50.8 % |

## 3. Stresstests

Ausgangskurs 614.99 $. Über Betas: Markt-Einbruch umgerechnet mit den heutigen Betas aus dem Graphen, ohne Eigenanteil der Aktie. Vor dem Start des Sektor-ETF zählt nur das Marktbeta; der tatsächliche Verlust einer Aktie kann deutlich höher liegen.

| Art | Von | Bis | Handelstage | Markt | Basis | Wirkung | Kurs |
|---|---|---|---:|---:|---|---:|---:|
| Eigene Historie | 2021-09-07 | 2022-11-03 | 293 | – | echter Verlauf | -76.7 % | 143 $ |
| Eigene Historie | 2012-05-21 | 2012-09-04 | 73 | – | echter Verlauf | -47.9 % | 320 $ |
| Eigene Historie | 2018-07-25 | 2018-12-24 | 105 | – | echter Verlauf | -43.0 % | 351 $ |
| Eigene Historie | 2020-01-29 | 2020-03-16 | 32 | – | echter Verlauf | -34.6 % | 402 $ |
| Eigene Historie | 2025-02-14 | 2025-04-21 | 44 | – | echter Verlauf | -34.2 % | 405 $ |
| Markt-Einbruch über Betas | 2007-10-09 | 2009-03-09 | 355 | -55.2 % | nur Markt | -67.7 % | 199 $ |
| Markt-Einbruch über Betas | 2000-03-24 | 2002-10-09 | 637 | -47.5 % | nur Markt | -59.7 % | 248 $ |
| Markt-Einbruch über Betas | 2020-02-19 | 2020-03-23 | 23 | -33.7 % | Markt + Sektor | -50.2 % | 306 $ |
| Markt-Einbruch über Betas | 2022-01-03 | 2022-10-12 | 195 | -24.5 % | Markt + Sektor | -57.3 % | 263 $ |
| Markt-Einbruch über Betas | 2018-09-20 | 2018-12-24 | 65 | -19.3 % | Markt + Sektor | -34.3 % | 404 $ |

## 4. Take Profit vor Stop Loss

Geprüft jeweils zum Tagesschluss, Treffer innerhalb des Tages sind nicht erfasst.

| TP | SL | Horizont | TP zuerst | SL zuerst | Keines |
|---:|---:|---|---:|---:|---:|
| +5% | -5% | 1M | 53.0% | 43.7% | 3.3% |
| +5% | -5% | 6M | 54.8% | 45.2% | 0.0% |
| +10% | -5% | 1M | 33.8% | 50.9% | 15.3% |
| +10% | -5% | 6M | 42.5% | 57.4% | 0.0% |
| +20% | -10% | 1M | 10.8% | 29.0% | 60.3% |
| +20% | -10% | 6M | 43.7% | 52.9% | 3.4% |

## 5. VaR-Backtest außerhalb der Trainingsdaten

2,221 Handelstage von 2016-01-04 bis 2024-10-29. Für jeden Tag wurde das Modell nur mit der Vergangenheit neu geschätzt. Getestet wird auf Stichtagen ohne Überlappung. Bestanden heißt: Kupiec und Christoffersen liegen beide bei p ≥ 5 %. Die letzten 2 Jahre bleiben unangetastet.

| Verfahren | Horizont | Kennzahl | Fälle | Erwartet | Treffer | Quote | p Kupiec | p Christoffersen | Ergebnis |
|---|---|---|---:|---:|---:|---:|---:|---:|---|
| FHS | 1T | VaR 95 | 2,220 | 111.0 | 110.0 | 5.0% | 0.922 | 0.795 | bestanden |
| FHS | 1T | VaR 99 | 2,220 | 22.2 | 24.0 | 1.1% | 0.705 | 0.716 | bestanden |
| FHS | 7T | VaR 95 | 444 | 22.2 | 26.0 | 5.9% | 0.420 | 0.644 | bestanden |
| FHS | 7T | VaR 99 | 444 | 4.4 | 8.0 | 1.8% | 0.127 | 0.269 | zu wenig Fälle |
| FHS | 1M | VaR 95 | 105 | 5.2 | 5.0 | 4.8% | 0.910 | 0.448 | bestanden |
| FHS | 1M | VaR 99 | 105 | 1.1 | 2.0 | 1.9% | 0.407 | 0.682 | zu wenig Fälle |
| FHS | 6M | VaR 95 | 17 | 0.9 | 2.0 | 11.8% | 0.272 | 0.411 | zu wenig Fälle |
| FHS | 6M | VaR 99 | 17 | 0.2 | 1.0 | 5.9% | 0.165 | 0.357 | zu wenig Fälle |
| FHS | 1J | VaR 95 | 8 | 0.4 | 2.0 | 25.0% | 0.058 | 0.073 | zu wenig Fälle |
| FHS | 1J | VaR 99 | 8 | 0.1 | 1.0 | 12.5% | 0.068 | 0.161 | zu wenig Fälle |
| Block | 1T | VaR 95 | 2,220 | 111.0 | 114.0 | 5.1% | 0.771 | 0.423 | bestanden |
| Block | 1T | VaR 99 | 2,220 | 22.2 | 23.0 | 1.0% | 0.865 | 0.775 | bestanden |
| Block | 7T | VaR 95 | 444 | 22.2 | 26.0 | 5.9% | 0.420 | 0.644 | bestanden |
| Block | 7T | VaR 99 | 444 | 4.4 | 4.0 | 0.9% | 0.831 | 0.942 | zu wenig Fälle |
| Block | 1M | VaR 95 | 105 | 5.2 | 5.0 | 4.8% | 0.910 | 0.448 | bestanden |
| Block | 1M | VaR 99 | 105 | 1.1 | 2.0 | 1.9% | 0.407 | 0.682 | zu wenig Fälle |
| Block | 6M | VaR 95 | 17 | 0.9 | 2.0 | 11.8% | 0.272 | 0.411 | zu wenig Fälle |
| Block | 6M | VaR 99 | 17 | 0.2 | 1.0 | 5.9% | 0.165 | 0.357 | zu wenig Fälle |
| Block | 1J | VaR 95 | 8 | 0.4 | 2.0 | 25.0% | 0.058 | 0.073 | zu wenig Fälle |
| Block | 1J | VaR 99 | 8 | 0.1 | 1.0 | 12.5% | 0.068 | 0.161 | zu wenig Fälle |

6 Monate und 1 Jahr sind damit nicht belegt: Dafür gibt es zu wenige unabhängige Zeiträume. Die Treffer dort deuten eher auf ein zu kleines als auf ein zu großes Risiko hin.

Anteil der Fälle innerhalb der 80 %-Spanne (Ziel 80 %):

| Verfahren | 1T | 7T | 1M | 6M | 1J |
|---|---:|---:|---:|---:|---:|
| Block | 80.8% | 80.4% | 76.2% | 76.5% | 62.5% |
| FHS | 78.5% | 78.4% | 78.1% | 70.6% | 62.5% |

## 6. Monte Carlo gegen die Modelle aus Phase 3

Dieselben Testjahre, je Tag zum Handelsschluss. MC ist hier FHS. Skill in Prozent, in Klammern das 95 %-Intervall; fett, wenn es ganz über null liegt. Bei 6 Monaten und 1 Jahr stehen nur wenige unabhängige Zeiträume dahinter, die Intervalle sind dort trotz Fettdruck nicht belastbar.

| Horizont | Fälle | Unabhängig | Spanne: MC gegen fest | Block gegen fest | HAR gegen fest | Spanne: MC gegen HAR | Richtung: MC gegen Basisrate |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1T | 1,255 | 1255 | **+6.45 %** (+4.7 bis +8.2) | +1.73 % | +4.04 % | **+2.51 %** (+1.1 bis +4.0) | +0.06 % (-0.2 bis +0.3) |
| 7T | 1,251 | 260 | **+6.74 %** (+4.4 bis +9.0) | +2.34 % | +2.83 % | **+4.03 %** (+1.9 bis +6.2) | +0.25 % (-0.7 bis +1.1) |
| 1M | 1,235 | 61 | **+7.83 %** (+4.1 bis +11.3) | +3.79 % | +3.94 % | **+4.05 %** (+1.4 bis +6.5) | +0.76 % (-3.5 bis +4.6) |
| 6M | 1,130 | 10 | **+17.35 %** (+9.9 bis +22.3) | +13.28 % | +3.66 % | **+14.21 %** (+8.6 bis +18.2) | +10.00 % (-27.6 bis +21.8) |
| 1J | 1,004 | 5 | **+15.52 %** (+9.3 bis +25.1) | +10.60 % | -1.81 % | **+17.03 %** (+9.3 bis +32.1) | +4.64 % (-13.6 bis +9.1) |

## 7. Beziehungsgraph

Sektor von META: XLC. Betas zum letzten Stichtag (2026-10-30): Markt 1.41, Sektor über den Markt hinaus 1.51 (gemessen an XLC). Hat der Ticker selbst großes Gewicht im Sektor-ETF, misst das Sektor-Beta teils die Aktie selbst.

Über den Sektor erreichbar: CMCSA, DIS, GOOGL, T, VZ, XLC.

| Stärkste Korrelation | Wert | Stärkster Vorlauf | Wert |
|---|---:|---|---:|
| XLC | +0.67 | AAPL | +0.16 |
| XLY | +0.46 | PFE | +0.15 |
| SPY | +0.44 | GILD | +0.15 |
| AMZN | +0.40 | INTC | -0.14 |
| QQQ | +0.39 | PG | +0.10 |

Vorlauf: Korrelation von META heute mit dem Ziel morgen. Bei 252 Tagen liegt schon ein einzelner Zufallswert in 95 % der Fälle bis ±0,12, und hier ist das Maximum aus 45 Paaren gelistet. Die Vorlauf-Werte sind deshalb kein Beleg für einen Zusammenhang.

## 8. Laufzeit

1,000,000 Pfade x 252 Schritte: 0.48 s, 6.6 GB Grafikspeicher. 10,000,000 Pfade in Portionen: 3.8 s.
