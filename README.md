# IonTrader

Statistische Auswertung einer Aktie aus ihrer eigenen Kursgeschichte: Bullish/Bearish-Wahrscheinlichkeit und Risiko für 1 Tag, 7 Tage, 1 Monat, 6 Monate und 1 Jahr. Keine Anlageberatung, es werden keine Orders gesendet.

**Ergebnis der Prüfung:** Bei META und NVDA ist keine Richtung belegt. Das Modell hat die historische Steigquote in den Prüfzeiträumen nicht geschlagen. Die Messungen stehen in [reports](reports) und [GAMEPLAN.md](GAMEPLAN.md).

**Öffentliche Momentaufnahme:** https://roberti1902.github.io/IonTrader/

## Live-Dashboard starten

Windows, Python 3.12, NVIDIA-GPU mit CUDA. Die Abhängigkeiten stehen in `requirements.txt`, der C++-Teil in `native`.

Kursdaten und Modelle sind nicht im Repository. Trage deine eigenen Alpaca-Keys in `.env` ein, Vorlage ist `.env.example`. Ohne Keys läuft der Yahoo-Modus. Der erste Lauf für einen Ticker baut alles im Hintergrund auf und dauert mehrere Stunden.

```bash
python main.py run META
```

Das Dashboard läuft dann unter http://127.0.0.1:8050.

## Momentaufnahme erzeugen

```bash
python main.py snapshot --push
```

Das erzeugt `docs/index.html` für alle voll geprüften Ticker und lädt die Seite hoch.
