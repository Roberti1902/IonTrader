# META: Phase-7-Report

Stand 2026-11-01 17:32. Statistische Auswertung der Kursgeschichte, keine Anlageberatung. Es wurden keine Orders gesendet.

Zeitraum 2020-11-03 bis 2026-10-30. Signal zum Handelsschluss, Ausführung zur nächsten Eröffnung, nur Long. Start 10,000 $, Kosten 5 Basispunkte je Seite plus 1 $ je Order, Cash verzinst mit ^IRX. Steuer 26.375 % auf realisierte Gewinne je Jahr mit Verlustvortrag, Depot am Ende verkauft. Alle Regeln standen vor dem ersten Lauf fest (GAMEPLAN, Phase 7).

## Ergebnis

| Strategie | Rendite p. a. | Nach Steuer p. a. | Endwert nach Steuer | Sharpe | Schwankung | Max. Einbruch | Investiert | Orders | Kosten $ | Steuer $ | Mit 20 Bp. |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Halten Aktie | +15.4 % | +12.3 % | 19,988 $ | 0.25 | 43.5 % | -76.7 % | 100.0 % | 2 | 19 | 3,578 | +15.4 % |
| Halten SPY | +16.2 % | +13.0 % | 20,696 $ | 0.71 | 16.5 % | -24.5 % | 100.0 % | 2 | 19 | 3,832 | +16.2 % |
| Cash | +3.2 % | +2.4 % | 11,517 $ | 0.00 | 0.1 % | 0.0 % | 0.0 % | 0 | 0 | 543 | +3.2 % |
| Stack 1T | -0.4 % | -0.4 % | 9,749 $ | -0.11 | 33.3 % | -70.8 % | 53.1 % | 574 | 2,683 | 0 | -14.5 % |
| Stack 7T | -6.2 % | -6.2 % | 6,820 $ | -0.32 | 29.8 % | -69.1 % | 43.1 % | 534 | 928 | 0 | -8.8 % |
| Stack 1M | +8.1 % | +6.0 % | 14,124 $ | 0.21 | 21.8 % | -45.1 % | 42.1 % | 256 | 373 | 1,477 | +7.4 % |
| Monte Carlo 1T | +18.0 % | +13.5 % | 21,345 $ | 0.62 | 21.5 % | -28.0 % | 18.7 % | 200 | 1,823 | 4,064 | +12.2 % |
| Monte Carlo 7T | +4.4 % | +3.1 % | 12,030 $ | 0.05 | 18.4 % | -31.2 % | 8.6 % | 206 | 442 | 805 | +3.3 % |
| Monte Carlo 1M | +3.2 % | +2.4 % | 11,517 $ | 0.00 | 0.1 % | 0.0 % | 0.0 % | 0 | 0 | 543 | +3.2 % |
| Muster 7T | +2.0 % | +1.5 % | 10,913 $ | -0.04 | 27.9 % | -70.7 % | 49.1 % | 763 | 1,435 | 346 | -2.0 % |
| 200-Tage-Linie | +16.1 % | +12.3 % | 19,953 $ | 0.42 | 27.6 % | -41.0 % | 66.0 % | 36 | 350 | 5,257 | +15.1 % |
| Momentum 12-1 | +13.6 % | +10.9 % | 18,523 $ | 0.30 | 31.6 % | -50.9 % | 71.8 % | 71 | 128 | 3,053 | +13.4 % |
| Volatilitaet | +17.6 % | +13.1 % | 20,865 $ | 0.41 | 31.7 % | -56.5 % | 79.8 % | 413 | 947 | 4,371 | +15.8 % |

## Besser als Halten der Aktie?

Vor Steuern, nach Kosten. Block-Bootstrap über 21 Tage, 5,000 Läufe, in Klammern das 95 %-Intervall. q ist korrigiert über alle 40 Tests beider Ticker. Belegt heißt q < 0,05 und positiv in Walk-Forward und Abschlussprüfung.

| Strategie | Rendite-Differenz p. a. | Walk-Forward | Abschluss | q | Belegt | Sharpe-Differenz | Walk-Forward | Abschluss | q | Belegt |
|---|---:|---:|---:|---:|---|---:|---:|---:|---:|---|
| Stack 1T | -14.7 % (-35.0 % bis +5.6 %) | -30.1 % | +16.2 % | 0.999 | nein | -0.36 (-0.88 bis +0.13) | -0.74 | +0.56 | 0.999 | nein |
| Stack 7T | -20.7 % (-39.1 % bis -3.5 %) | -26.4 % | -9.1 % | 0.999 | nein | -0.58 (-0.97 bis -0.19) | -0.64 | -0.66 | 0.999 | nein |
| Stack 1M | -6.5 % (-29.4 % bis +15.7 %) | -15.4 % | +11.4 % | 0.999 | nein | -0.04 (-0.53 bis +0.40) | -0.28 | +0.42 | 0.999 | nein |
| Monte Carlo 1T | +2.3 % (-28.1 % bis +33.4 %) | +0.2 % | +6.6 % | 0.999 | nein | +0.37 (-0.56 bis +1.17) | +0.31 | +0.51 | 0.999 | nein |
| Monte Carlo 7T | -10.0 % (-37.2 % bis +17.0 %) | -15.0 % | -0.2 % | 0.999 | nein | -0.20 (-0.93 bis +0.55) | -0.26 | -0.10 | 0.999 | nein |
| Monte Carlo 1M | -11.1 % (-43.6 % bis +20.8 %) | -17.5 % | +1.8 % | 0.999 | nein | -0.25 (-1.07 bis +0.45) | -0.39 | +0.05 | 0.999 | nein |
| Muster 7T | -12.3 % (-27.6 % bis +2.7 %) | -20.2 % | +3.6 % | 0.999 | nein | -0.30 (-0.64 bis +0.07) | -0.48 | +0.11 | 0.999 | nein |
| 200-Tage-Linie | +0.6 % (-24.8 % bis +25.8 %) | +9.8 % | -17.7 % | 0.999 | nein | +0.17 (-0.53 bis +0.84) | +0.60 | -0.67 | 0.999 | nein |
| Momentum 12-1 | -1.6 % (-23.2 % bis +20.0 %) | -2.8 % | +0.9 % | 0.999 | nein | +0.05 (-0.49 bis +0.63) | +0.08 | +0.02 | 0.999 | nein |
| Volatilitaet | +1.9 % (-8.3 % bis +12.5 %) | +2.6 % | +0.5 % | 0.999 | nein | +0.15 (-0.04 bis +0.33) | +0.25 | +0.00 | 0.999 | nein |

## Was das heißt

Belegt besser als Halten: keine Strategie.

**Grenzen:** META wurde ausgewählt, als der Kursverlauf schon bekannt war, Halten ist hier also eine hohe Latte und Halten von SPY die fairere Referenz. Beträge in Dollar ohne Wechselkurs. Dividenden stecken als bereinigte Kurse in der Rendite und werden erst beim Verkauf besteuert. Kosten sind eine Annahme, nicht gemessen.
