# IonTrader – Gameplan

**Ziel:** Ticker eingeben → Live-Chart mit Overlays → alle 5 Sekunden Bullish/Bearish-Wahrscheinlichkeit und Risiko für +1 Tag, +7 Tage, +1 Monat, +6 Monate, +1 Jahr, gelernt aus der Vergangenheit genau dieser Aktie.

**Verbindliche Grundlage:** deine IonTrader-Notizen, deine fünf Phasen, deine erste Nachricht und das Chart-Pattern-Bild. Abschnitt 4 belegt Punkt für Punkt, wo jede Vorgabe umgesetzt wird.

---

## 1. Wie alles zusammenhängt

Deine Punkte sind keine lose Tool-Liste, sondern eine Kette. Jede Stufe liefert der nächsten ihren Input.

```text
THESE       Fraktale Markthypothese: Märkte haben Gedächtnis, Muster wiederholen sich über Timeframes
               │
MESSEN         ├─ Hurst/DFA je Timeframe: Gibt es dieses Gedächtnis bei diesem Ticker gerade?
               │     H > 0,5 → Trend hält an  → Momentum zählt
               │     H < 0,5 → Trend kehrt um → Mean Reversion zählt
               ├─ Bollinger, Z-Score, Fibonacci: Wie weit ist der Kurs vom Mittelwert/Niveau entfernt?
               └─ 20 Chartmuster: diskrete Ereignisse mit Entry, SL, TP
               │
ALPHA          ├─ Pattern-Matching: Muster wiederholen sich → direkt nachgeschlagen
               ├─ LSTM/GRU: Gedächtnis → gelernt
               └─ Transformer/TFT: Beziehung beliebig ferner Kurspunkte → gelernt per Attention
               │
RISIKO         Monte Carlo: Millionen Pfade mit erhaltenem Gedächtnis, Peer-Schocks aus dem Graphen
               │
MATRIX         Alle Signale → gewichtet und kalibriert → 68 % Bullish / 32 % Bearish je Horizont
               │
DASHBOARD      Chart, Overlays, Matrix, Risiko, 5-Sekunden-Takt
```

Daraus folgen drei Querverbindungen:

- **Hurst ist der Schalter zwischen deinen beiden Thesen.** Fraktalität und Mean Reversion/Momentum sind dieselbe Frage: Hält die Bewegung an oder kehrt sie um? (Hypothese; bei META nicht bestätigt, siehe Abschnitt 6.)
- **Das Bild liefert die Bewertungsregel.** Jedes Muster hat Entry, SL und TP. Damit lässt sich exakt zählen, was zuerst getroffen wurde.
- **Matching und neuronale Netze prüfen sich gegenseitig.** Stimmen sie nicht überein, sinkt die angezeigte Verlässlichkeit.

---

## 2. Spannungen in den Vorgaben und ihre Auflösung

| # | Vorgabe | Befund | Entscheidung |
|---|---|---|---|
| 1 | „Millionen historische Sequenzen von Meta“ im 5-Minuten-Verlauf | 5m seit 2016 ergibt nur rund 212.000 Bars | Fraktaler Ansatz: normierte Fenster über 1m bis 1D ergeben rund 1,3 Mio., mit 3 Fensterlängen rund **3,9 Mio. Sequenzen**. Zusätzlich speichern wir 1m als Basis. |
| 2 | Überlappende Sequenzen | Sie sind fast identisch und zählen nicht als unabhängige Beispiele | Matching dedupliziert per Mindestabstand und zeigt die effektive Fallzahl an |
| 3 | Vorhersage für 1 Jahr aus Meta-Daten | Nur rund 14 unabhängige Jahre, 6 Monate: rund 29, 1 Monat: rund 170, 7 Tage: rund 750, 1 Tag: rund 3.600 | Reines Meta-Training bleibt. Zusätzlich läuft Training auf liquiden US-Aktien plus Feinschliff auf den Ticker. Die Messung entscheidet. |
| 4 | C++ für „extrem schnelle Execution“ | Bei 5-Sekunden-Takt zählt keine Mikrosekunde, und in deinen Phasen steht keine Orderausführung | C++ wird der **Rechenkern**: geht jeden Bar einzeln durch, identisch in Historie und Live. Es werden keine Orders gesendet. |
| 5 | „TFT oder LSTM“, dazu GRU und Transformer | Alle stehen in deinen Notizen | **Alle vier** werden trainiert, gemessen und als Ensemble kombiniert |
| 6 | Datenquellen | Yahoo: 5m nur rund 60 Tage. Binance: nur Krypto, kein META. IB: echte 5-Sekunden-Bars, aber Konto und Marktdaten-Abo nötig. Polygon: kostenpflichtig | **Yahoo** für Tagesdaten, **Alpaca** für 1m seit 2016 und Live-Trades. Ohne Key läuft der Yahoo-Modus. |
| 7 | Echtzeit-5-Sekunden-Daten | Alpaca liefert Einzel-Trades, frei nur von IEX (rund 2,5 % des Volumens) | Trades → selbst gebaute 5-Sekunden-Bars. Intraday-Volumen sieht das Modell erst nach 16 Minuten, in Training und Live gleich, weil dann die Vollmarkt-Daten (SIP) da sind |
| 8 | SQLite oder TimescaleDB | TimescaleDB braucht einen Server | **SQLite**, ohne Installation |
| 9 | Relationale und Graph-Datenbank | Für Aladdin sind Monte Carlo und Szenarien belegt, eine Graph-DB konnte ich nicht belegen. Sinnvoll bleibt die Idee trotzdem | `nodes`- und `edges`-Tabellen in derselben SQLite-Datei; kein Neo4j-Server |
| 10 | PyTorch oder TensorFlow | TensorFlow unterstützt die Windows-GPU nativ seit Version 2.11 nicht mehr (aus meinem Wissen) | **PyTorch** |
| 11 | Dash oder PyQt | Beides genügt | **Dash/Plotly**, „Overlay“ = zuschaltbare Ebenen im Chart |
| 12 | Fraktale Hypothese und Fibonacci als gesetzt | Die Belege für Hurst-Effekte sind gemischt und hängen vom Schätzverfahren ab | Alles wird gebaut, aber **pro Ticker getestet**. Der Thesen-Report zeigt, ob es hier wirkt |
| 13 | Deine Phasen enthalten kein Backtesting | Ohne das ist „68 %“ nur eine Behauptung | Purged Walk-Forward und Kalibrierung in Phase 5 |
| 14 | Risiko, C++, 20 Muster, Fraktal fehlen in den Phasen | Sie stehen aber in den Notizen | Eingearbeitet; Risiko bekommt eine eigene Phase |
| 15 | „100 %“ | Umsetzung ja, Treffsicherheit nein | Jede Vorgabe wird gebaut. Die Trefferquote wird offen gemessen und angezeigt, auch wenn sie keinen Vorsprung zeigt |

**Reihenfolge:** Deine fünf Phasen bleiben erhalten. Die Risiko-Säule kommt als neue Phase 4 davor, weil die Matrix ihre Ergebnisse braucht. Deine Phase 4 wird dadurch zu 5, deine Phase 5 zu 6.

---

## 3. Die Phasen

### Phase 1 – Datenbeschaffung und Speicher
- [x] 1.1 SQLite-Datenbank. Jeder Bar trägt sein **Ende** als Zeitstempel, damit nichts vor seiner Zeit sichtbar ist
- [x] 1.2 Yahoo: Tagesdaten seit Börsengang, dazu 5m und 1h als Modus ohne Key
- [x] 1.3 Alpaca: 1m seit 2016, reguläre Handelszeit, split- und dividendenbereinigt
- [x] 1.4 Aggregation: 5m, 15m, 1h, 4h, 1D, 1W, 12D, 1M, 12W, 12M
- [x] 1.5 Live-Feed: Trades → 5-Sekunden-Bars
- [x] 1.6 Datencheck: unmögliche Kerzen, fehlende Bars, Abweichung zwischen den Quellen

**Abnahme:** `ingest META`, `check META` und `live META` laufen auf echten Daten. Erfüllt mit Alpaca: 1.059.314 1m-Bars, keine kaputten Kerzen.

### Phase 2 – Indikatoren-Schmiede
- [x] 2.1 TA-Lib auf jedem Timeframe: RSI, MACD, Bollinger, SMA/EMA, ADX, ATR, OBV, MFI, Stochastik
- [x] 2.2 C++-Kern `ioncore` (nanobind, MSVC, OpenMP): geht jeden Bar einzeln durch
- [x] 2.3 Swing-Hochs/-Tiefs und Fibonacci (0,236 / 0,382 / 0,5 / 0,618 / 0,786 plus Extensions). Ein Swing zählt erst ab seiner Bestätigung
- [x] 2.4 Scanner für die 20 Muster mit Entry, SL, TP wie im Bild; Auswertung, was zuerst getroffen wurde (Triple Barrier), und Vergleich mit einer Kontrollgruppe
- [x] 2.5 Fraktal: rollender Hurst, DFA, Multifraktal-Breite, Lo-Test gegen Scheineffekte durch Kurzfrist-Abhängigkeit
- [x] 2.6 Mean Reversion und Momentum: Z-Score, Bollinger %B, ADF, Variance Ratio, Halbwertszeit, 12-1-Momentum, ROC
- [x] 2.7 Ereignisstudie: was nach jedem Signal je Timeframe und Horizont passierte. Bei META 983 Tests, deshalb Korrektur nach Benjamini-Hochberg

**Abnahme:** Test mit abgeschnittenen Daten zeigt keinen Blick in die Zukunft; synthetische Muster werden erkannt; erster META-Report steht. Erfüllt: `python main.py scan META`, Ergebnis in `reports/META_phase2.md`.

### Phase 3 – CUDA-Gehirn
- [x] 3.1 PyTorch mit CUDA in `.venv`
- [x] 3.2 Datensatz: ein Fenster je Timeframe, zeitlich sauber ausgerichtet, Skalierung nur aus Trainingsdaten
- [x] 3.3 LSTM, GRU, Transformer, TFT: je Timeframe ein Encoder, verbunden per Cross-Timeframe-Attention, mit 5 Ausgängen. Start auf Basisrate (Richtung) und HAR-Schwankung (Spanne)
- [x] 3.4 Training: nur Ticker gegen Universum plus Feinschliff, Mixed Precision auf der RTX 3060, Walk-Forward über 5 Testjahre, je Ziel eigene Auswahl mit Beleg (t ≥ 2)
- [x] 3.5 Pattern-Matching: rund 4,1 Mio. Fenster, exakter Vergleich auf der GPU, Feinvergleich der Besten per DTW in C++, Ergebnis ist die Verteilung des Folgeverlaufs

**Abnahme:** `torch.cuda.is_available()` ist `True`; ein eingepflanztes Muster wird wiedergefunden; eine Matching-Abfrage dauert messbar unter 5 Sekunden. Erfüllt: `python main.py train META`, Median 11 ms je Abfrage, Ergebnis in `reports/META_phase3.md`.

### Phase 4 – Risiko-Säule (neu)
- [x] 4.1 Beziehungsgraph: Ticker, Sektor, Index, Makro; Kanten für Korrelation, Beta, Lead-Lag mit Datum
- [x] 4.2 Monte Carlo auf der GPU, mindestens 1 Mio. Pfade je Lauf:
  - Filtered Historical Simulation: GJR-GARCH plus gezogene Residuen (Volatilitäts-Cluster, dicke Enden)
  - Block-Bootstrap: erhält das Gedächtnis der Kursreihe
  - Korrelierte Schocks von Markt und Sektor aus dem Graphen; Sprünge an Earnings-Terminen
- [x] 4.3 Stresstests: Replay der schlimmsten historischen Phasen
- [x] 4.4 Ausgabe je Horizont: VaR 95/99, CVaR, maximaler Drawdown, Wahrscheinlichkeit TP vor SL
- [x] 4.5 VaR-Backtest nach Kupiec und Christoffersen

**Abnahme:** VaR-Tests bestehen außerhalb der Trainingsdaten; Laufzeit für 1 Mio. Pfade ist gemessen. Erfüllt: `python main.py risk META`, alle 4 testbaren Kombinationen bestanden, 1 Mio. Pfade in 0,46 s, Ergebnis in `reports/META_phase4.md`.

### Phase 5 – Wahrscheinlichkeits-Matrix
- [x] 5.1 Fünf Ausgänge: Bullish/Bearish, Trend, Spanne (Quantile)
- [x] 5.2 Purged Walk-Forward mit Embargo gleich Horizont (Vorhersagen aus Phase 3 liegen in `data/oos`); die letzten 24 Monate bleiben bis zum Schluss unangetastet
- [x] 5.3 Stacking aus LSTM, GRU, Transformer, TFT, Matching, Mustern und Monte Carlo
- [x] 5.4 Kalibrierung (Isotonic, Conformal, jeweils nur wo im Walk-Forward besser); lange Horizonte werden Richtung Basisrate gezogen
- [x] 5.5 Setup- und Thesen-Report je Ticker: welche Indikatoren, Muster und Thesen hier wirklich helfen

**Abnahme:** Brier Skill Score gegen die Basisrate je Horizont liegt vor; aus „70 %“ werden in Tests rund 70 % Treffer; fehlender Vorsprung wird angezeigt statt versteckt. Erfüllt mit einer Einschränkung: Die Anzeige liegt überall innerhalb der Zufallsstreuung, ist aber bei langen Horizonten kaum prüfbar und lag in beiden Prüfzeiträumen stets über der Wirklichkeit. Ablauf: `python main.py matrix META`, dann `python main.py finalcheck META`, Ergebnis in `reports/META_phase5.md`.

### Phase 6 – Live-Dashboard und Overlay
- [x] 6.1 Ticker-Eingabe, ein neuer Ticker startet die Pipeline automatisch
- [x] 6.2 Candlesticks in allen Timeframes; Overlays: Bollinger, Fibonacci, Muster mit Entry/SL/TP, Top-Analogien, Monte-Carlo-Fächer
- [x] 6.3 Anzeige „Meta in 7 Tagen: 68 % Bullish / 32 % Bearish“ plus Risikopanel; darüber je Horizont ein Block mit der Chance, höher zu stehen, und der typischen Bewegung nach oben und unten (Median aus Monte Carlo). Das ist Statistik, kein Kaufsignal: Solange „Richtung belegt“ fehlt, entspricht die Chance im Kern der früheren Steigquote
- [x] 6.4 Drei Takte:
  - **Alle 5 Sekunden:** Kurs, laufender Bar, Stack, 1 Million neue Monte-Carlo-Pfade ab dem aktuellen Kurs. Die Netze gehen mit ihrer letzten Ausgabe aus dem Nachtlauf ein (Abschnitt 9: Ihre Abweichung von der Basisrate ist nicht belastbar)
  - **Bei Bar-Schluss:** Scanner, Matching, Mean Reversion und Momentum
  - **Nachts/wöchentlich:** Daten-Refresh, Neutraining, Rekalibrierung
- [x] 6.5 Prognose-Logbuch: jede Prognose wird gespeichert und später mit dem echten Kurs verglichen

**Abnahme:** `python main.py run META` hält während der Handelszeit den 5-Sekunden-Takt; ein zweiter Ticker funktioniert ohne Codeänderung. Zweiter Ticker erfüllt: NVDA lief ohne tickerspezifischen Code durch und deckte dabei zwei Anzeigefehler auf, die behoben sind (Abschnitt 10). **Takt im echten Handel noch offen:** Bisher ist er nur in der Wiedergabe und bei geschlossenem Markt gemessen, frühester Termin ist 2026-11-02, 15:30 deutscher Zeit.

### Phase 7 – Strategie-Backtest (neu)

Frage: Hätte ein Signal nach Kosten und Steuern mehr gebracht als einfaches Halten? Die Regeln stehen hier **vor** dem ersten Lauf und werden danach nicht geändert. Neue Regeln brauchen neue Daten.

- [x] 7.1 Simulator: Signal zum Handelsschluss, Ausführung zur nächsten Eröffnung, nur Long, 10.000 $ Start, Cash verzinst mit ^IRX
- [x] 7.2 Kosten: 5 Basispunkte je Seite plus 1 $ je Order; Stress mit 20 Basispunkten. Orders erst ab 5 Prozentpunkten Gewichtsänderung
- [x] 7.3 Steuer: 26,375 % auf realisierte Gewinne je Kalenderjahr, Verlustvortrag, Depot wird am Ende verkauft. Ohne Sparerpauschbetrag und Kirchensteuer
- [x] 7.4 Vergleich: Halten der Aktie, Halten von SPY, Cash
- [x] 7.5 Zehn feste Strategien, jede über ihren Horizont gestaffelt, damit der Starttag kein Glück ist (Gewicht = Mittel der Signale der letzten h Handelstage):
  - Stack über Basisrate, 1 Tag / 5 Tage / 21 Tage
  - Monte Carlo über Basisrate, 1 Tag / 5 Tage / 21 Tage
  - Muster netto bullisch, 5 Tage
  - Kurs über 200-Tage-Linie
  - 12-1-Momentum positiv, 21 Tage
  - Volatilitätssteuerung: Gewicht = min(1, Median der bisher prognostizierten Schwankung / heutige Prognose aus FHS)
- [x] 7.6 Zeitraum: Testjahre des Stacks, 2020-10 bis 2026-10, dazu Walk-Forward und Abschlussprüfung getrennt
- [x] 7.7 Beleg: Block-Bootstrap (21 Tage, 5.000 Läufe) auf Rendite- und Sharpe-Differenz gegen Halten der Aktie, vor Steuern. Benjamini-Hochberg über alle Tests beider Ticker (40). „Belegt“ heißt q < 0,05 und positiv in beiden Teilzeiträumen
- [x] 7.8 Bericht und Dashboard-Bereich, auch auf der öffentlichen Seite

**Abnahme:** Simulator besteht Tests auf Zukunftsblick, Kosten und Steuer; `python main.py backtest META` und `NVDA` liefern den Bericht, auch wenn keine Strategie gewinnt. Erfüllt: Beide laufen zusammen mit `python main.py backtest`, 12 Tests, Ergebnis in `reports/META_phase7.md` und `reports/NVDA_phase7.md`.

### Phase 8 – Rangliste über viele Aktien (neu)

Frage: Schlägt eine Auswahl aus dem ganzen S&P 500 nach Kosten den Index, wenn auch spätere Verlierer im Test sind? Die Regeln stehen hier **vor** dem ersten Lauf. Bilanzdaten (Profitabilität, Bewertung) und Modelle darauf kommen erst in einer eigenen Phase, weil dafür die Firmenkennungen der verschwundenen Firmen fehlen.

- [x] 8.1 Universum: historische S&P-500-Mitglieder, von der heutigen Liste rückwärts aus den Änderungen rekonstruiert (Wikipedia). Tageskurse von Alpaca, bereinigt um Splits und Dividenden, ab 2016
- [x] 8.2 Abgleich: META und SPY von Alpaca gegen die vorhandenen Yahoo-Kurse, Abweichung der Jahresrendite höchstens 1 Punkt; Tagessprünge über 60 % zählen und prüfen
- [x] 8.3 Verschwundene Aktien: Verkauf zum letzten Schluss. War die Aktie in den letzten 21 Handelstagen über 30 % gefallen, gilt zusätzlich ein Abschlag von 30 % (Shumway 1997), sonst keiner
- [x] 8.4 Simulator: Signal zum letzten Handelstag des Monats, Ausführung zur nächsten Eröffnung, nur Long. Kosten und Steuer wie Phase 7, Start 100.000 $. Eine Order erst ab 25 % Abweichung vom Zielgewicht, Verkauf auf null immer. Zusätzlich gerechnet mit 10.000 $ Start, weil dort die 1 $ je Order stark wirkt
- [x] 8.5 Auswahl: nur Mitglieder am Signaltag ohne Tagessprung über 60 % im Rückblick. Kauf der besten 50 gleichgewichtet, gehalten bis außerhalb der besten 100
- [x] 8.6 Sieben feste Strategien, Zeitraum 2017-01 bis 2026-10:
  - Momentum 12-1: Rendite von vor 252 bis vor 21 Handelstagen
  - Geringe Schwankung: Standardabweichung der letzten 252 Tage
  - Kombination: Mittel der Ränge aus beiden
  - Umkehr: Verlierer des letzten Monats
  - Alle Mitglieder gleichgewichtet
  - Alle Mitglieder mit Volatilitätssteuerung: je Aktie Gewicht × min(1, Median der bisherigen 21-Tage-Schwankung / heutige)
  - SPY mit derselben Volatilitätssteuerung
- [x] 8.7 Vergleich: Halten von SPY, zusätzlich zur Information Halten nur der heutigen Mitglieder, um die Überlebensverzerrung zu zeigen
- [x] 8.8 Beleg: Block-Bootstrap wie Phase 7 auf Rendite- und Sharpe-Differenz vor Steuern. 14 Tests gegen SPY plus 4 Tests der beiden Volatilitäts-Strategien gegen ihre ungesteuerte Fassung, Benjamini-Hochberg über alle 18. „Belegt“ heißt q < 0,05 und positiv in 2017–2021 und in 2022–2026
- [x] 8.9 Rang-IC je Faktor gegen die Rendite der folgenden 21 Tage, monatlich
- [x] 8.10 Dashboard: Rang des Tickers je Faktor, Top 10 und Ergebnis; auf der öffentlichen Seite nur das Ergebnis, keine Liste einzelner Aktien

**Abnahme:** Tests für Mitgliedschaft, Auswahl, Verschwinden einer Aktie, Kosten und Steuer; `python main.py rank` liefert den Bericht, auch wenn keine Strategie gewinnt. Erfüllt: 16 Tests, Ergebnis in `reports/SP500_phase8.md`.

### Phase 9 – Bilanzdaten und Insiderkäufe (neu)

Frage: Schlagen Bilanz- und Insiderdaten nach Kosten den Index, wenn jede Zahl erst ab ihrem Veröffentlichungstag zählt? Die Regeln stehen hier **vor** dem ersten Lauf.

- [x] 9.1 Quellen: SEC EDGAR Company Facts (10-K, 10-Q) und Insider Transactions Data Sets. Absender mit Kontakt aus `.env`, höchstens 8 Abfragen je Sekunde
- [x] 9.2 Firmen zuordnen: heutige Mitglieder über die Wikipedia-Kennung, frühere über Ticker und Firmennamen. Passt der Name nicht, bleibt die Firma ohne Daten. Die Abdeckung wird je Monat gemessen und berichtet, auch für verschwundene Firmen
- [x] 9.3 Zeitpunkt: Jede Zahl zählt erst ab dem Tag nach ihrer ersten Veröffentlichung, immer in der ersten gemeldeten Fassung. Spätere Korrekturen bleiben außen vor
- [x] 9.4 Marktwert: unbereinigter Schlusskurs von Alpaca mal zuletzt gemeldete Aktienzahl, höchstens 200 Tage alt
- [x] 9.5 Simulator, Kosten, Steuer, Zeitraum und Auswahl (beste 50, gehalten bis außerhalb der besten 100) unverändert aus Phase 8. Ohne Wert nimmt eine Aktie nicht teil
- [x] 9.6 Acht feste Strategien:
  - Profitabilität: Nettogewinn der letzten 12 Monate / Bilanzsumme
  - Gewinnrendite: Nettogewinn der letzten 12 Monate / Marktwert
  - Buchwert: Eigenkapital / Marktwert
  - Geringes Bilanzwachstum: niedriges Wachstum der Bilanzsumme gegen vor einem Jahr
  - Gewinnüberraschung: Änderung des 12-Monats-Gewinns zum Quartal davor / Bilanzsumme, Meldung höchstens 92 Tage alt
  - Insiderkäufe: Zahl verschiedener Insider mit offenem Marktkauf (Code P) in den letzten 180 Tagen, mindestens einer
  - Kombination: Mittel der Ränge aus Profitabilität, Gewinnrendite und Momentum 12-1
  - Modell: LightGBM auf den Rängen aller Faktoren aus Phase 8 und 9, Ziel ist der Rang der Rendite der folgenden 21 Tage. Neu gelernt jeden Januar, nur aus Monaten, deren Ergebnis vorher feststand. Einsatz ab 2019, davor Halten von SPY. Feste Einstellungen: 200 Bäume, Lernrate 0,05, 15 Blätter, mindestens 100 Fälle je Blatt, Stichprobe und Spalten 0,8, Startwert 0
- [x] 9.7 Beleg: wie Phase 8, 16 Tests gegen SPY, Benjamini-Hochberg über diese 16. Dazu Rang-IC je Faktor
- [x] 9.8 Dashboard wie Phase 8: lokal Rang und Top 10, öffentlich nur das Ergebnis

**Abnahme:** Tests für 12-Monats-Gewinn, erste Fassung, Zeitpunkt, Namensprüfung und Insiderzählung; `python main.py fundamentals` liefert den Bericht, auch wenn keine Strategie gewinnt. Erfüllt: 11 Tests, Ergebnis in `reports/SP500_phase9.md`.

---

## 4. Abdeckung: jede Vorgabe, ihre Umsetzung

### IonTrader-Notizen
| Vorgabe | Umsetzung |
|---|---|
| Name „IonTrader“ | Paket `iontrader` |
| Vorbilder Renaissance, Citadel, Two Sigma | Prinzipien: viele Signale, strenge Validierung, Trennung von Alpha und Risiko (5.2, 5.3, Phase 4) |
| Säule Risikoanalyse (Aladdin) | Phase 4 |
| Monte Carlo, Millionen Fälle | 4.2 |
| Relationale/Graph-Datenbank | 1.1 und 4.1 |
| Säule Alpha-Generierung | Phasen 2, 3, 5 |
| C++ für schnelle Ausführung | 2.2, 2.4, 3.5 (Auflösung #4) |
| Fraktale Markthypothese | 2.5, 3.2, 3.5, Test in 5.5 |
| Mean Reversion und Momentum, permanent getestet | 2.6, je Bar in 6.4 |
| Fibonacci-Retracement | 2.3 |
| Bollinger-Bänder | 2.1, 2.6 |
| LSTM und GRU | 3.3 |
| Transformer und Attention | 3.3 |

### Deine Phasen
| Vorgabe | Umsetzung |
|---|---|
| API-Setup und 5-Sekunden-Daten | 1.2, 1.3, 1.5 (Auflösung #6, #7) |
| Lokale Datenbank, 5m/1h/1D/1W parallel | 1.1, 1.4 |
| RSI, MACD, Bollinger mit TA-Lib | 2.1 |
| Fibonacci und Struktur (0,382 / 0,618) | 2.3 |
| CUDA-Setup | 3.1 |
| TFT oder LSTM, Multi-Timeframe | 3.3 |
| Abgleich mit Millionen Sequenzen | 3.5 (Auflösung #1) |
| Fünf Ausgänge: Trend und Wahrscheinlichkeit | 3.3, 5.1 |
| Dash/Plotly, 5-Sekunden-Update, 68/32-Anzeige | 6.2 bis 6.4 |

### Deine erste Nachricht und das Bild
| Vorgabe | Umsetzung |
|---|---|
| Beliebiger Ticker als Eingabe | `main.py`, 6.1 |
| Live-Overlay auf dem aktuellen Graphen | 6.2 |
| Alle Timeframes von 5 Minuten bis 12 Tage/Wochen/Monate | 1.4 |
| Jede Aktie individuell, bestes Setup je Aktie | 3.4, 5.5 |
| Heavy Machine und Deep Learning, CUDA | Phase 3 |
| Jeden einzelnen Zeitpunkt durchgehen | 2.2 |
| Retracements, Trends, alle Indikatoren | 2.1, 2.3, 2.6 |
| 20 Chartmuster aus dem Bild | 2.4 |
| Was auf jede Bewegung folgte | 2.7, 3.5 |
| PyCharm | `.venv` ist als Interpreter eingetragen |
| Aktueller Kurs und alle 5 Sekunden die Prozente | 6.3, 6.4 |

---

## 5. Grenzen

- **Treffsicherheit:** Einzelaktien sind schwer vorherzusagen. Forschung zu Chartbildern meldet laut Sekundärquelle 52–53 % Trefferquote über einen Monat. IonTrader misst den eigenen Vorsprung, er garantiert keinen.
- **Vorbilder:** Interne Systeme von Renaissance, Citadel und Two Sigma sind nicht öffentlich. Ihr Vorsprung beruht auch auf Daten und Handelskosten, die wir nicht nachbauen können.
- **Keine Orders:** IonTrader ist ein Analysewerkzeug und handelt nicht.
- **Geltungsbereich:** vorerst nur US-Aktien; Zeitraster und Alpaca sind darauf ausgelegt.

---

## 6. Befunde aus Phase 2 (META, 2016 bis 2026)

Diese Befunde gelten für META und für Einzelsignale ohne Handelskosten. Kombinationen mehrerer Signale prüft erst Phase 3, andere Ticker sind noch nicht getestet.

| These | Ergebnis | Folge für den Plan |
|---|---|---|
| Chartmuster sagen die Richtung voraus | 0 von 87 Muster-Timeframe-Kombinationen schlagen die Kontrollgruppe; Trefferquoten liegen fast überall am Break-even | Muster bleiben Eingabe für die Modelle, ihr Beitrag wird in 5.5 gemessen |
| Indikatoren und Fibonacci sagen die Richtung voraus | 0 von 983 Tests nach FDR; ohne Korrektur 39 Treffer, bei Zufall rund 49 | Wie oben |
| Märkte haben Gedächtnis (Richtung) | H rund 0,5, Lo-Test auf keinem Timeframe signifikant | Richtungs-Prozente werden nahe an der Basisrate liegen, bis ein Modell das Gegenteil außerhalb der Trainingsdaten belegt |
| Märkte haben Gedächtnis (Schwankung) | H 0,71 bis 0,84, Lo-Test auf allen 9 Timeframes signifikant | **Stärkstes Signal bisher.** Es stützt die Risiko-Säule und die Spannen in der Matrix |
| Hurst schaltet zwischen Mean Reversion und Momentum | 1 von 28 Vergleichen, also Zufallsniveau | Hurst bleibt Eingabe, aber kein fester Schalter |
| Mean Reversion ist häufig | ADF-Stationarität in 2 bis 6 % der Fenster, nur bei 1m rund 10 % (bei Zufall rund 5 %) | Kein allgemeiner Umkehr-Effekt ab 5m |

## 7. Befunde aus Phase 3 (META, Testjahre 2019-11 bis 2024-10)

Gemessen im Walk-Forward: Training, Auswahl und Test überlappen nie. Geprüft wurde eine Konfiguration je Modelltyp ohne Hyperparameter-Suche, die letzten 2 Jahre sind weiterhin unangetastet.

| Frage | Ergebnis | Folge für den Plan |
|---|---|---|
| Schlagen die Netze die Basisrate bei der Richtung? | Nein. Kein Modell und kein Horizont liegt mit dem 95 %-Intervall über null; einige liegen klar darunter | Die Matrix bleibt nahe an der Basisrate, Stacking in 5.3 muss das Gegenteil erst belegen |
| Hilft das Universum? | Kein messbarer Vorteil gegenüber nur META | Modus bleibt im Vergleich, Mehrwert ist nicht belegt |
| Hilft das Matching bei der Richtung? | Nein, -0,2 bis -0,9 % Brier Skill | Bleibt für Analogien und Overlay, in 5.3 ohne Vorschuss |
| Lässt sich die Spanne vorhersagen? | Ja. HAR schlägt feste Quantile bei 1 Tag, 7 Tagen und 1 Monat belegbar (+3,5 / +2,7 / +3,8 %) | **Risiko-Säule und Spannen haben das stärkste Fundament** |
| Schlagen die Netze HAR bei der Spanne? | Nein, kein Intervall liegt über null | Siehe Abschnitt 8: Monte Carlo schlägt HAR |

## 8. Befunde aus Phase 4 (META, Backtest 2016-01 bis 2024-10)

Das Modell wurde für jeden Handelstag nur mit der Vergangenheit neu geschätzt. Die letzten 2 Jahre sind weiterhin unangetastet.

| Frage | Ergebnis | Folge für den Plan |
|---|---|---:|
| Stimmen die VaR-Werte? | Ja, bei 1 Tag (95 und 99), 7 Tagen (95) und 1 Monat (95): Kupiec und Christoffersen bestanden | Risikozahlen bis 1 Monat dürfen im Dashboard als geprüft gelten |
| Sind die VaR-Werte für 6 Monate und 1 Jahr belegt? | Nein, zu wenige unabhängige Zeiträume; 2 Treffer bei 0,9 bzw. 0,4 erwarteten deuten auf eher zu kleines Risiko | Im Dashboard als nicht belegt kennzeichnen |
| FHS oder Block-Bootstrap? | FHS ist bei der Spanne auf allen Horizonten besser (1 Tag +6,45 % gegen +1,73 % zu festen Quantilen) | FHS ist das Standardverfahren |
| Schlägt Monte Carlo HAR bei der Spanne? | Ja, belastbar bis 1 Monat (+2,5 / +4,0 / +4,1 %); bei 6 Monaten und 1 Jahr nur wenige unabhängige Zeiträume | **FHS wird die Basis der Spannen in der Matrix** |
| Sagt Monte Carlo die Richtung voraus? | Nein, kein Intervall liegt über null | Die Richtung bleibt nahe der Basisrate |
| Bringt die Trennung der Earnings etwas? | Ja, ohne sie steigt der VaR 99 auf 1 Monat von -29,8 auf -34,6 %, weil Earnings die normale Schwankung verfälschen | Bleibt im Modell |
| Gibt es Vorlauf zwischen Aktien? | Kein Beleg, alle Werte liegen im Rauschbereich der Mehrfachtests | Lead-Lag-Kanten bleiben im Graphen, aber ohne Vorschuss |

## 9. Endergebnis aus Phase 5 (META)

Walk-Forward 2020-10 bis 2024-10, Abschlussprüfung 2024-10 bis 2026-10. Die Modelleinstellungen wurden vor der Abschlussprüfung eingefroren. Die Regel für „Richtung belegt“ wurde danach verschärft (Vorsprung muss in beiden Zeiträumen bestehen); das macht die Aussage nur vorsichtiger.

| Frage | Ergebnis | Folge für das Dashboard |
|---|---|---|
| Schlägt der Stack die Basisrate bei der Richtung? | Nein. Über 6 Testjahre -0,08 / +0,01 / -0,05 / +0,07 / -0,01 %, kein Intervall über null | Anzeige „Richtung nicht belegt“ auf allen Horizonten |
| Stimmen die angezeigten Prozente? | Innerhalb der Zufallsstreuung, aber stets zu hoch: 76,2 % angezeigt gegen 56,9 % echt bei 1 Jahr (nur 6 unabhängige Zeiträume) | Lange Horizonte als wahrscheinlich zu optimistisch kennzeichnen |
| Schlägt Monte Carlo HAR auch in der Abschlussprüfung? | Ja, belegt bei 1 Tag (+3,4 %) und 7 Tagen (+3,4 %); bei 1 Monat +1,4 % ohne Beleg | **FHS bleibt die Basis der Spannen** |
| Bestehen die VaR-Werte die Abschlussprüfung? | Ja, alle 3 testbaren: 1 Tag (95 und 99), 7 Tage (95) | Risikozahlen bis 7 Tage sind zweifach geprüft, 1 Monat nur im Backtest |
| Helfen Isotonic und Conformal? | Isotonic nirgends, Conformal nur bei 1 Tag und dort kaum | Conformal nur bei 1 Tag aktiv |
| Welche Indikatoren helfen? | Richtung: 1 von 1.592 Tests, also Zufallsniveau. Schwankung: 209 von 1.592, vorn ATR, Bollinger-Breite und Abstand zur 200er-Linie | Diese Indikatoren erklären die Spanne, nicht die Richtung |
| Weichen die Netze belastbar ab? | Nein. Zwei Läufe des aktuellen Trainings unterscheiden sich um bis zu 1 Prozentpunkt, das ist so viel wie der Abstand zur Basisrate | Netze laufen als nächtlicher Job, nicht im 5-Sekunden-Takt |

**Korrektur:** Bis Phase 4 war die Zahl der unabhängigen Fälle zu hoch angegeben, weil Blöcke in Handelstagen auf Kalendertage angewendet wurden. Richtig sind über 5 Testjahre 1.255 / 260 / 61 / 10 / 5. Die Intervalle wurden neu berechnet, die Kernaussagen bleiben gleich.

## 10. Ergebnis aus Phase 6 und zweiter Ticker (NVDA)

NVDA lief mit den bei META eingefrorenen Regeln, seine Abschlussprüfung 2024-10 bis 2026-10 war vorher unberührt. Der Bericht steht in `reports/NVDA_phase5.md`.

| Frage | Ergebnis | Folge |
|---|---|---|
| Hält das Dashboard den Takt? | In der Wiedergabe Ø 5,00 s, längster 5,02 s, Rechenzeit rund 800 ms bei 1 Million Pfaden. Mit Bar-Schluss in jedem Takt Ø 5,00 s. Neben dem Wochenlauf Ø 5,00 s, längster 5,09 s, Rechenzeit Ø 1.250 ms über 412 Läufe | **Im echten Handel noch nicht gemessen** |
| Zeigt das Dashboard dieselben Zahlen wie die Matrix? | Ja, bei ruhendem Kurs auf 0,1 Prozentpunkte genau, per Test bei META und im Dashboard bei NVDA (52,8 / 58,6 / 66,0 / 82,3 / 82,0 %) | Die 5-Sekunden-Anzeige und der Report widersprechen sich nicht |
| Laufen Hintergrund-Jobs? | Pipeline NVDA startete aus dem Dashboard, Nachtlauf META und Wochenlauf NVDA (33,8 min) liefen je einmal von Hand. Die Zeitsteuerung ist nur per Test geprüft | Ein echter Nachtlauf nach Handelsschluss steht noch aus |
| Schlägt der Stack bei NVDA die Basisrate? | Nein. Über 6 Testjahre +0,04 / -0,13 / -0,18 / -0,57 / -0,04 %, kein Intervall über null | Dasselbe Bild wie bei META: „Richtung nicht belegt“ auf allen Horizonten |
| Übertragen sich Muster, Fibonacci und Signale? | Nein. 0 von 92 Mustern, 0 von 140 Fibonacci-, 0 von 240 Mean-Reversion-, 0 von 220 Momentum-Tests. Gedächtnis der Schwankung dagegen auf 9 von 9 Timeframes | Die Befunde aus Abschnitt 6 gelten nun für zwei Aktien, nicht für den Markt allgemein |
| Überträgt sich der Vorsprung von Monte Carlo gegen HAR? | **Nein.** Im Walk-Forward +0,23 / +0,27 / -0,30 %, in der Abschlussprüfung -0,94 / -1,32 / +4,15 % bei 1 Tag, 7 Tagen und 1 Monat, kein Intervall über null. Gegen feste Werte belegt nur 1 Tag (+4,47 %) | Der stärkste META-Befund ist nicht allgemein. FHS bleibt Standard, HAR ist aber nicht schlechter |
| Bestehen die VaR-Werte? | Nur 2 von 4: 7 Tage und 1 Monat ja. 1 Tag fällt im Backtest durch (VaR 95 in 5,9 % der Fälle überschritten, p = 0,047; VaR 99 in 1,5 %), besteht aber die Abschlussprüfung (5,8 %) | Die Karte nennt den Durchfall und die gemessene Quote |
| Stimmt die Spanne bei langen Horizonten? | Nein. Die rohe Spanne wurde nach oben viel zu oft verfehlt (6 Monate 29 %, 1 Jahr 40 %, Ziel je 10 %), nach unten kaum (9 %). Conformal weitet beide Seiten, die Untergrenze bei 1 Jahr fällt auf -94 % und passt nicht mehr zum VaR 95 von 47,5 % | Die Karte weist darauf hin. Die Regel bleibt, solange neue Daten fehlen, um eine Änderung fair zu prüfen |

Der zweite Ticker hat zwei Fehler sichtbar gemacht, die bei META nie auftraten: Ein durchgefallener Backtest hieß auf der Karte „zu wenige Zeiträume“, und der Phase-4-Bericht enthielt einen fest verdrahteten Satz aus den META-Ergebnissen. Beide sind behoben.

## 11. Ergebnis aus Phase 7 (META und NVDA, 2020-11 bis 2026-10)

Nach dem ersten Lauf wurden zwei Rechenfehler behoben, keine Regel: Die Rendite enthielt fälschlich schon Steuerzahlungen, und der Zins war um einen Tag verschoben. Die Regeln aus Phase 7 blieben unverändert.

| Frage | Ergebnis | Folge |
|---|---|---|
| Schlägt eine Strategie das Halten der Aktie belegt? | **Nein.** 0 von 40 Tests, alle q = 0,999 | Kein Signal im Dashboard als Kaufsignal ausweisen |
| Bringen die Modellsignale nach Kosten Geld? | Stack nach Steuer: META -0,4 / -6,2 / +6,0 % p. a., NVDA +11,4 / +0,6 / +3,9 %, gegen Halten +12,3 und +52,0 % | Das Stack-Signal taugt nicht als Handelsregel |
| Warum ist Monte Carlo so selten investiert? | Seine Steigquote liegt fast immer unter der Basisrate (META 1 Monat und NVDA 7 Tage, 1 Monat: nie investiert). Das misst den Abstand zweier Schätzungen, keine Marktlage | „Über der Basisrate“ ist bei Monte Carlo kein sinnvolles Signal. Die Regel bleibt für diesen Test stehen |
| Lohnt Volatilitätssteuerung? | Sharpe +0,15 und +0,17, in allen Teilzeiträumen nicht negativ, untere Intervallgrenze bei -0,04 und -0,00, nach Korrektur nicht belegt. Nach Steuer META +13,1 gegen +12,3 %, NVDA +43,7 gegen +52,0 % | Beste Spur und am selben Teil des Tools, der schon die Risikotests besteht. Neu prüfen an vielen Aktien |
| Wie stark wirken Kosten und Steuern? | Stack 1 Tag bei META: -0,4 % bei 5 Basispunkten, -14,5 % bei 20. Steuer kostet Halten rund 3 Punkte (META) und 7 Punkte (NVDA) | Tägliche Signale sind für Privatanleger kaum tragbar |
| Halten oder Index? | META nach Steuer +12,3 %, SPY +13,0 % bei Sharpe 0,25 gegen 0,71 und Einbruch -76,7 gegen -24,5 %. NVDA +52,0 % ist mit Wissen um den Verlauf ausgewählt | Künftige Tests messen sich auch an SPY |

Zwei Aktien können wenig belegen, die Intervalle sind teils 50 Punkte breit. Der nächste Schritt ist die Rangliste über viele Aktien.

## 12. Ergebnis aus Phase 8 (S&P 500, 2017-01 bis 2026-10)

737 Aktien mit Kursen, im Schnitt 505 Mitglieder, auch später verschwundene Firmen wie SVB. Beim Prüfen fiel auf, dass Alpaca Abspaltungen nicht bereinigt. Die Regeln blieben, alle Strategien wurden aber zusätzlich mit Yahoo-Kursen für 597 Aktien gerechnet; die Zahlen ändern sich kaum, das Urteil gar nicht. Behoben wurde außerdem eine überflüssige Order zum Jahreswechsel im Simulator.

| Frage | Ergebnis | Folge |
|---|---|---|
| Schlägt eine Auswahl den Index belegt? | **Nein.** 0 von 18 Tests, alle q = 0,999, auch mit Yahoo-Kursen | Die Rangliste ist kein Kaufsignal |
| Was bringen die Faktoren vor Steuern? | SPY +14,8 % p. a.; Momentum +13,3, gleichgewichtet +11,6, geringe Schwankung +9,4, Kombination +8,9, Umkehr +8,1 | Kein reiner Kursfaktor lag über SPY |
| Haben die Faktoren Vorhersagekraft? | Rang-IC +0,001 / -0,007 / -0,001 / +0,000, t höchstens 0,3 | In diesem Zeitraum und Universum nicht messbar |
| Wie groß ist die Überlebensverzerrung? | Nur heutige Mitglieder: +16,9 % p. a., alle damaligen: +11,6 % | Rund 5 Punkte Scheingewinn. Backtests auf heutigen Listen täuschen stark |
| Hält die Spur aus Phase 7? | SPY mit Volatilitätssteuerung: Sharpe 0,73 gegen 0,63, Einbruch -20,2 gegen -33,8 %, aber Rendite +11,6 gegen +14,8 % und nach Steuer +8,8 gegen +12,3 %; nicht belegt. Je Aktie gesteuert schadet sie (Sharpe 0,32 gegen 0,46) | Bleibt ein Risikowerkzeug, keine Renditequelle |
| Wie stark wirken kleine Depots? | Gleichgewichtet: +11,6 % bei 100.000 $, +7,5 % bei 10.000 $. Umkehr -1,8 %. Volatilität je Aktie: Gebühren zehren das Depot auf | Viele kleine Orders sind mit 1 $ je Order nicht tragbar |

Der Zeitraum war von großen Technologiewerten geprägt, das begünstigt den nach Marktwert gewichteten Index. Momentum lag 2022–2026 +5,0 Punkte über SPY, 2017–2021 -7,6 Punkte: Das Ergebnis hängt also stark von der Marktphase ab, das Intervall reicht von -8,4 bis +5,9 Punkten. Bilanzdaten sind noch nicht getestet.

## 13. Ergebnis aus Phase 9 (S&P 500, 2017-01 bis 2026-10)

723 von 737 Symbolen mit SEC-Kennung. Mitglieder mit Wert 89 bis 97 %, verschwundene Firmen 79 bis 86 %, Insiderkäufe 24 % (die übrigen hatten keinen Kauf). Stichproben gegen bekannte Firmen passen: AAPL Marktwert 5,0 Billionen, JPM Gesamtkapitalrendite und KGV plausibel, Zuordnung von SVB, First Republic, Twitter und Aetna richtig.

| Frage | Ergebnis | Folge |
|---|---|---|
| Schlägt eine Bilanz- oder Insider-Strategie den Index belegt? | **Nein.** 0 von 16 Tests, alle q = 0,966 | Auch das ist kein Kaufsignal |
| Was bringen sie vor Steuern? | SPY +14,8 %; Profitabilität +14,9, Gewinnüberraschung +13,8, Kombination +13,8, Modell +13,1, Bilanzwachstum +12,5, Buchwert +11,1, Insider +10,4, Gewinnrendite +9,8 | Profitabilität liegt gleichauf mit SPY, 2017–2021 +4,7 Punkte, 2022–2026 -4,6 Punkte |
| Haben die Faktoren Vorhersagekraft? | Rang-IC höchstens +0,015, t höchstens 1,3 | Bei Profitabilität und Kombination eine schwache Spur, nicht belegt |
| Hilft maschinelles Lernen? | LightGBM IC +0,001, t 0,1, kein Merkmal sticht heraus | Mehr Modell ersetzt keine Vorhersagekraft |
| Nach Steuer? | SPY +12,3 %, Profitabilität +12,0 %, Kombination +10,7 % | Halten bleibt steuerlich im Vorteil |

Stand nach den Phasen 7 bis 9: 74 vorab festgelegte Tests, keiner belegt. Der Zeitraum ist dabei immer derselbe: Weitere Backtests darauf erhöhen vor allem das Risiko eines Zufallstreffers. Neue Belege kann nur noch die Zukunft liefern (Musterdepot).
