"""Oeffentliche Momentaufnahme fuer GitHub Pages: dieselben Kacheln wie im Dashboard, als fertige Seite ohne Server."""
import subprocess
import time
from html import escape

import pandas as pd
from dash.development.base_component import Component

from . import ROOT, ingest
from .app import card, chances, hero, known_tickers, logbook_panel, regime_panel, risk_panel, theses_panel, verdict
from .engine import Live
from .ingest import NY
from .store import connect

OUT = ROOT / "docs" / "index.html"


def to_html(node):
    """Dash-Bausteine als HTML. Die Seite bleibt so automatisch gleich zum Dashboard."""
    if node is None:
        return ""
    if isinstance(node, (list, tuple)):
        return "".join(to_html(child) for child in node)
    if not isinstance(node, Component):
        return escape(str(node))
    props = node.to_plotly_json()["props"]
    attrs = {"class": props.get("className"), "title": props.get("title")}
    if props.get("style"):
        attrs["style"] = "; ".join(f"{key}: {value}" for key, value in props["style"].items())
    attrs = "".join(f' {key}="{escape(str(value))}"' for key, value in attrs.items() if value)
    tag = type(node).__name__.lower()
    return f"<{tag}{attrs}>{to_html(props.get('children'))}</{tag}>"


def section(con, symbol, now):
    live = Live(symbol, con, with_index=False)
    live._load_index()  # Wie im Dashboard, aber die Seite wartet auf das Matching
    try:
        live.seed(ingest.yahoo_intraday(symbol, "1m", "5d", 1))
    except Exception as error:  # Dann gilt der letzte Schlusskurs aus der Datenbank, die Zeile oben nennt den Stand
        print(f"{symbol}: heutige Bars nicht geladen: {error}", flush=True)
    live.tick(now)
    snapshot = live.snapshot
    if snapshot["dist"] is None:  # GPU belegt, etwa vom Nachtlauf: Dann bleibt die alte Seite stehen, statt nur Basisraten zu zeigen
        raise SystemExit(f"{symbol}: Monte Carlo nicht gelaufen, Seite bleibt unveraendert")
    tf = "1D"
    parts = [("hero", hero(snapshot)), ("cards", chances(snapshot)), ("verdict", verdict(live, snapshot)), ("cards", [card(live, snapshot, row) for row in snapshot["rows"]]),
             ("panels", [risk_panel(snapshot), regime_panel(live, snapshot, tf), theses_panel(live), logbook_panel(live)])]
    body = "".join(f'<div class="{name}">{to_html(body)}</div>' for name, body in parts)
    return f'<section id="{symbol}">' + body.replace(", alle 5 s ab dem aktuellen Kurs", ", ab dem Kurs dieser Momentaufnahme").replace("Deine Thesen", "Thesen") + "</section>"


def page(sections, now):
    when = pd.Timestamp(now, unit="s", tz="UTC").tz_convert(NY)
    links = " · ".join(f'<a href="#{symbol}">{symbol}</a>' for symbol in sections)
    css = (ROOT / "assets" / "style.css").read_text(encoding="utf-8")
    return f"""<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>IonTrader</title>
<style>{css}</style>
</head>
<body>
<div class="page">
<div class="bar"><span class="brand">IonTrader</span> {links}</div>
<div class="known">Momentaufnahme vom {when:%d.%m.%Y, %H:%M} New York, keine Live-Daten. Die Kacheln zeigen diesen Stand, bis die Seite neu erzeugt wird.</div>
{"".join(sections.values())}
<div class="foot">Statistische Auswertung der Kursgeschichte, keine Anlageberatung. Es werden keine Orders gesendet.</div>
</div>
</body>
</html>
"""


def build():
    con, now = connect(), time.time()
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(page({symbol: section(con, symbol, now) for symbol in known_tickers()}, now), encoding="utf-8")
    print(f"Momentaufnahme: {OUT}", flush=True)


def push():
    for command in (["add", "docs"], ["commit", "-m", "Momentaufnahme aktualisiert"], ["push"]):
        subprocess.run(["git", *command], cwd=ROOT, check=True)
