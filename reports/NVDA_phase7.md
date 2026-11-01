# NVDA: Phase-7-Report

Stand 2026-11-01 17:32. Statistische Auswertung der Kursgeschichte, keine Anlageberatung. Es wurden keine Orders gesendet.

Zeitraum 2020-11-03 bis 2026-10-30. Signal zum Handelsschluss, Ausführung zur nächsten Eröffnung, nur Long. Start 10,000 $, Kosten 5 Basispunkte je Seite plus 1 $ je Order, Cash verzinst mit ^IRX. Steuer 26.375 % auf realisierte Gewinne je Jahr mit Verlustvortrag, Depot am Ende verkauft. Alle Regeln standen vor dem ersten Lauf fest (GAMEPLAN, Phase 7).

## Ergebnis

| Strategie | Rendite p. a. | Nach Steuer p. a. | Endwert nach Steuer | Sharpe | Schwankung | Max. Einbruch | Investiert | Orders | Kosten $ | Steuer $ | Mit 20 Bp. |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Halten Aktie | +59.4 % | +52.0 % | 121,708 $ | 0.87 | 49.7 % | -66.3 % | 100.0 % | 2 | 88 | 40,018 | +59.3 % |
| Halten SPY | +16.2 % | +13.0 % | 20,696 $ | 0.71 | 16.5 % | -24.5 % | 100.0 % | 2 | 19 | 3,832 | +16.2 % |
| Cash | +3.2 % | +2.4 % | 11,517 $ | 0.00 | 0.1 % | 0.0 % | 0.0 % | 0 | 0 | 543 | +3.2 % |
| Stack 1T | +15.3 % | +11.4 % | 19,028 $ | 0.37 | 29.6 % | -66.8 % | 32.2 % | 618 | 5,462 | 3,234 | -1.7 % |
| Stack 7T | +2.3 % | +0.6 % | 10,339 $ | -0.05 | 18.3 % | -50.1 % | 17.0 % | 299 | 639 | 1,457 | +0.7 % |
| Stack 1M | +5.4 % | +3.9 % | 12,546 $ | 0.13 | 16.4 % | -44.8 % | 17.6 % | 148 | 215 | 1,423 | +5.2 % |
| Monte Carlo 1T | -1.7 % | -2.3 % | 8,683 $ | -0.52 | 9.5 % | -26.9 % | 1.3 % | 40 | 248 | 400 | -2.7 % |
| Monte Carlo 7T | +3.2 % | +2.4 % | 11,517 $ | 0.00 | 0.1 % | 0.0 % | 0.0 % | 0 | 0 | 543 | +3.2 % |
| Monte Carlo 1M | +3.2 % | +2.4 % | 11,517 $ | 0.00 | 0.1 % | 0.0 % | 0.0 % | 0 | 0 | 543 | +3.2 % |
| Muster 7T | +15.2 % | +10.5 % | 18,106 $ | 0.36 | 30.5 % | -50.1 % | 50.4 % | 802 | 2,355 | 4,996 | +10.6 % |
| 200-Tage-Linie | +50.8 % | +42.6 % | 83,149 $ | 0.90 | 41.7 % | -47.7 % | 82.1 % | 24 | 647 | 26,205 | +49.9 % |
| Momentum 12-1 | +44.2 % | +36.7 % | 64,751 $ | 0.74 | 44.5 % | -53.2 % | 85.0 % | 31 | 112 | 19,614 | +44.0 % |
| Volatilitaet | +57.7 % | +43.7 % | 87,074 $ | 1.03 | 40.7 % | -56.0 % | 86.1 % | 295 | 1,884 | 27,611 | +55.6 % |

## Besser als Halten der Aktie?

Vor Steuern, nach Kosten. Block-Bootstrap über 21 Tage, 5,000 Läufe, in Klammern das 95 %-Intervall. q ist korrigiert über alle 40 Tests beider Ticker. Belegt heißt q < 0,05 und positiv in Walk-Forward und Abschlussprüfung.

| Strategie | Rendite-Differenz p. a. | Walk-Forward | Abschluss | q | Belegt | Sharpe-Differenz | Walk-Forward | Abschluss | q | Belegt |
|---|---:|---:|---:|---:|---|---:|---:|---:|---:|---|
| Stack 1T | -32.0 % (-62.3 % bis -2.3 %) | -42.2 % | -11.5 % | 0.999 | nein | -0.49 (-1.24 bis +0.23) | -0.62 | -0.20 | 0.999 | nein |
| Stack 7T | -44.0 % (-74.9 % bis -14.5 %) | -57.9 % | -16.3 % | 0.999 | nein | -0.92 (-1.70 bis -0.16) | -1.12 | -1.04 | 0.999 | nein |
| Stack 1M | -41.0 % (-72.1 % bis -11.3 %) | -54.0 % | -14.9 % | 0.999 | nein | -0.74 (-1.51 bis -0.01) | -0.94 | -0.74 | 0.999 | nein |
| Monte Carlo 1T | -48.0 % (-86.4 % bis -11.6 %) | -56.0 % | -32.0 % | 0.999 | nein | -1.39 (-2.44 bis -0.34) | -0.95 | -1.86 | 0.999 | nein |
| Monte Carlo 7T | -43.1 % (-81.7 % bis -5.5 %) | -57.2 % | -14.8 % | 0.999 | nein | -0.87 (-1.67 bis -0.11) | -1.09 | -0.34 | 0.999 | nein |
| Monte Carlo 1M | -43.1 % (-81.7 % bis -5.5 %) | -57.2 % | -14.8 % | 0.999 | nein | -0.87 (-1.67 bis -0.11) | -1.09 | -0.34 | 0.999 | nein |
| Muster 7T | -32.1 % (-50.6 % bis -13.2 %) | -30.4 % | -35.5 % | 0.999 | nein | -0.51 (-0.94 bis -0.11) | -0.27 | -1.16 | 0.999 | nein |
| 200-Tage-Linie | -5.5 % (-26.7 % bis +15.0 %) | -0.5 % | -15.5 % | 0.999 | nein | +0.03 (-0.42 bis +0.50) | +0.20 | -0.36 | 0.999 | nein |
| Momentum 12-1 | -10.0 % (-29.7 % bis +7.8 %) | -14.1 % | -1.9 % | 0.999 | nein | -0.12 (-0.50 bis +0.25) | -0.14 | -0.04 | 0.999 | nein |
| Volatilitaet | -0.9 % (-10.1 % bis +8.0 %) | -3.3 % | +3.8 % | 0.999 | nein | +0.17 (-0.00 bis +0.33) | +0.16 | +0.18 | 0.999 | nein |

## Was das heißt

Belegt besser als Halten: keine Strategie.

**Grenzen:** NVDA wurde ausgewählt, als der Kursverlauf schon bekannt war, Halten ist hier also eine hohe Latte und Halten von SPY die fairere Referenz. Beträge in Dollar ohne Wechselkurs. Dividenden stecken als bereinigte Kurse in der Rendite und werden erst beim Verkauf besteuert. Kosten sind eine Annahme, nicht gemessen.
