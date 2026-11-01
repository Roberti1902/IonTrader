# S&P 500: Phase-8-Report

Stand 2026-11-01 17:52. Statistische Auswertung der Kursgeschichte, keine Anlageberatung. Es wurden keine Orders gesendet.

Zeitraum 2017-01-31 bis 2026-10-30. Auswahl am letzten Handelstag des Monats aus den damaligen Mitgliedern, Ausführung zur nächsten Eröffnung, nur Long. Beste 50 gleichgewichtet, gehalten bis außerhalb der besten 100. Start 100,000 $, Kosten 5 Basispunkte je Seite plus 1 $ je Order. Alle Regeln standen vor dem ersten Lauf fest (GAMEPLAN, Phase 8).

**Daten:** 737 von 747 Symbolen mit Kursen, 505 Mitglieder im Schnitt. Tagessprünge über 60 %: 80, davon als Mitglied 12. Darunter sind unbereinigte Abspaltungen, gegen Yahoo bestätigt bei RTX 2020 und APTV 2017; echt sind etwa SVB und First Republic 2023. Die Spalten mit Yahoo rechnen dieselben Regeln mit Yahoo-Kursen für 597 Aktien, weil Yahoo Abspaltungen bereinigt. Yahoo-Belegt: 0 von 18 Tests.

| Abgleich | Alpaca p. a. | Yahoo p. a. | Tage |
|---|---:|---:|---:|
| SPY | +14.8 % | +14.9 % | 2,723 |
| META | +18.2 % | +18.2 % | 2,723 |

## Ergebnis

| Strategie | Rendite p. a. | Nach Steuer p. a. | Endwert nach Steuer | Sharpe | Schwankung | Max. Einbruch | Investiert | Orders | Kosten $ | Mit 10,000 $ Start | Rendite mit Yahoo | Sharpe mit Yahoo |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Halten SPY | +14.8 % | +12.3 % | 308,599 $ | 0.63 | 17.9 % | -33.8 % | 100.0 % | 2 | 244 | +14.8 % | +14.9 % | 0.63 |
| Momentum 12-1 | +13.3 % | +10.2 % | 256,731 $ | 0.42 | 23.9 % | -37.5 % | 99.6 % | 2,020 | 4,947 | +11.9 % | +13.1 % | 0.41 |
| Geringe Schwankung | +9.4 % | +7.2 % | 197,236 $ | 0.43 | 15.1 % | -35.5 % | 99.5 % | 572 | 1,383 | +9.0 % | +9.5 % | 0.44 |
| Kombination | +8.9 % | +6.7 % | 187,920 $ | 0.37 | 16.4 % | -34.3 % | 99.8 % | 1,417 | 3,474 | +7.9 % | +8.9 % | 0.37 |
| Umkehr | +8.1 % | +6.0 % | 175,487 $ | 0.21 | 25.6 % | -51.5 % | 97.7 % | 8,797 | 21,248 | -1.8 % | +8.2 % | 0.21 |
| Alle gleichgewichtet | +11.6 % | +8.9 % | 229,082 $ | 0.46 | 18.4 % | -38.8 % | 99.8 % | 4,475 | 4,891 | +7.5 % | +11.6 % | 0.46 |
| Alle mit Volatilitaet | +7.0 % | +5.2 % | 164,285 $ | 0.32 | 13.4 % | -30.1 % | 83.6 % | 18,364 | 19,337 | – | +7.0 % | 0.32 |
| SPY mit Volatilitaet | +11.6 % | +8.8 % | 227,115 $ | 0.73 | 11.7 % | -20.2 % | 79.6 % | 38 | 1,218 | +11.6 % | +11.7 % | 0.72 |

„–“ beim kleinen Depot heißt: Die Gebühren je Order haben das Depot aufgezehrt.

Zur Information, nicht getestet: Nur die heutigen Mitglieder gleichgewichtet hätten +17.0 % p. a. gebracht. Die Differenz zu „Alle gleichgewichtet“ zeigt die Überlebensverzerrung.

## Belegt besser?

Vor Steuern, nach Kosten. Block-Bootstrap wie Phase 7, in Klammern das 95 %-Intervall. q ist korrigiert über alle 18 Tests. Belegt heißt q < 0,05 und positiv in 2017–2021 und in 2022–2026.

| Strategie | Gegen | Kennzahl | Differenz | 2017–2021 | 2022–2026 | q | Belegt |
|---|---|---|---:|---:|---:|---:|---|
| Momentum 12-1 | SPY | Rendite p. a. | -1.4 % (-8.4 % bis +6.0 %) | -7.6 % | +5.0 % | 0.999 | nein |
| Momentum 12-1 | SPY | Sharpe | -0.22 (-0.58 bis +0.11) | -0.50 | +0.09 | 0.999 | nein |
| Geringe Schwankung | SPY | Rendite p. a. | -4.8 % (-12.5 % bis +2.7 %) | -4.3 % | -5.4 % | 0.999 | nein |
| Geringe Schwankung | SPY | Sharpe | -0.20 (-0.66 bis +0.31) | -0.18 | -0.28 | 0.999 | nein |
| Kombination | SPY | Rendite p. a. | -5.3 % (-11.8 % bis +1.1 %) | -5.2 % | -5.4 % | 0.999 | nein |
| Kombination | SPY | Sharpe | -0.27 (-0.66 bis +0.13) | -0.29 | -0.29 | 0.999 | nein |
| Umkehr | SPY | Rendite p. a. | -6.1 % (-15.9 % bis +3.8 %) | -4.4 % | -7.8 % | 0.999 | nein |
| Umkehr | SPY | Sharpe | -0.43 (-0.81 bis -0.06) | -0.43 | -0.44 | 0.999 | nein |
| Alle gleichgewichtet | SPY | Rendite p. a. | -2.8 % (-6.9 % bis +1.3 %) | -2.7 % | -2.9 % | 0.999 | nein |
| Alle gleichgewichtet | SPY | Sharpe | -0.17 (-0.40 bis +0.07) | -0.21 | -0.15 | 0.999 | nein |
| Alle mit Volatilitaet | SPY | Rendite p. a. | -7.0 % (-11.6 % bis -2.4 %) | -9.4 % | -4.5 % | 0.999 | nein |
| Alle mit Volatilitaet | SPY | Sharpe | -0.31 (-0.57 bis -0.05) | -0.40 | -0.21 | 0.999 | nein |
| SPY mit Volatilitaet | SPY | Rendite p. a. | -2.8 % (-7.5 % bis +1.9 %) | -5.5 % | -0.1 % | 0.999 | nein |
| SPY mit Volatilitaet | SPY | Sharpe | +0.09 (-0.16 bis +0.32) | +0.06 | +0.16 | 0.999 | nein |
| Alle mit Volatilitaet | ungesteuert | Rendite p. a. | -4.1 % (-7.9 % bis -0.7 %) | -6.7 % | -1.5 % | 0.999 | nein |
| Alle mit Volatilitaet | ungesteuert | Sharpe | -0.14 (-0.28 bis -0.01) | -0.19 | -0.06 | 0.999 | nein |
| SPY mit Volatilitaet | ungesteuert | Rendite p. a. | -2.8 % (-7.5 % bis +1.9 %) | -5.5 % | -0.1 % | 0.999 | nein |
| SPY mit Volatilitaet | ungesteuert | Sharpe | +0.09 (-0.16 bis +0.32) | +0.06 | +0.16 | 0.999 | nein |

## Rang-IC

Rangkorrelation zwischen Faktor und der Rendite der folgenden 21 Handelstage, je Monatsende unter den damaligen Mitgliedern.

| Faktor | Ø IC | t | Monate |
|---|---:|---:|---:|
| Momentum 12-1 | +0.001 | +0.0 | 117 |
| Geringe Schwankung | -0.007 | -0.3 | 117 |
| Umkehr | -0.001 | -0.1 | 117 |
| Kombination | +0.000 | +0.0 | 117 |

## Was das heißt

Belegt: keine Strategie.

**Grenzen:** Nur Kurse, keine Bilanzdaten. Ein Zeitraum von knapp zehn Jahren mit starkem Markt. Die Mitgliedschaft stammt aus einer rückwärts rekonstruierten Wikipedia-Liste. Der Abschlag für verschwundene Aktien ist eine Annahme. Beträge in Dollar ohne Wechselkurs.
