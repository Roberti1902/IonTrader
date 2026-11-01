"""Phase 6: Dashboard. Chart mit Overlays, Matrix, Risiko und Logbuch. Liest nur, was der Motor bereitstellt."""
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from dash import Dash, Input, Output, State, callback_context, dcc, html
from plotly.subplots import make_subplots

from . import ROOT
from .engine import ANALOG_BARS, MINUTES, TICK, Engine
from .ingest import NY, TIMEFRAMES
from .matrix import HORIZON_NAMES
from .train import OOS

SURFACE, INK, INK_2, MUTED, GRID = "#1a1a19", "#f0efec", "#c3c2b7", "#898781", "#2c2c2a"
UP, DOWN, FAN, FIB, ANALOG = "#3987e5", "#e66767", "#199e70", "#c98500", "#9085e9"  # geprueft mit dem Palette-Validator, gegen die dunkle Flaeche
OVERLAYS = {"bollinger": "Bollinger", "fib": "Fibonacci", "patterns": "Muster mit Entry/SL/TP", "analogs": "Top-Analogien", "fan": "Monte-Carlo-Fächer"}
BARS_PER_DAY = {"1m": 390, "5m": 78, "15m": 26, "1h": 7, "4h": 2, "1D": 1, "1W": 1 / 5, "12D": 1 / 12, "1M": 1 / 21, "12W": 1 / 60, "12M": 1 / 252}
HORIZON_TEXT = {"1T": "1 Tag", "7T": "7 Tagen", "1M": "1 Monat", "6M": "6 Monaten", "1J": "1 Jahr"}
SEND_BARS, VIEW_BARS, FAN_REACH = 800, 150, 120
STATUS_TEXT = {"fertig": "fertig", "laeuft": "läuft", "fehler": "Fehler", "uebersprungen": "übersprungen"}


def number(x, digits=2):
    return f"{x:,.{digits}f}".replace(",", " ").replace(".", ",").replace(" ", ".")


def pct(x, digits=1, sign=False):
    return f"{number(100 * x, digits) if not sign else ('+' if x >= 0 else '') + number(100 * x, digits)} %"


def chip(kind, icon, text):
    return html.Div([html.Span(icon, className="icon"), html.Span(text)], className=f"chip {kind}")


def fact(label, value):
    return html.Div([html.Span(label), html.Span(value)], className="fact")


def table(header, rows, class_name=None):
    return html.Table([html.Thead(html.Tr([html.Th(h) for h in header])), html.Tbody([html.Tr([html.Td(c) for c in row]) for row in rows])], className=class_name)


# ---------------------------------------------------------------------------
# Chart
# ---------------------------------------------------------------------------

def time_labels(index, tf):
    ny = index.tz_convert(NY)
    return ny.strftime("%d.%m. %H:%M" if tf in MINUTES else "%d.%m.%Y")


def fan_points(fan, tf, price, last_x):
    """Quantile je Handelstag auf der Bar-Achse. Innerhalb des ersten Tages wie die Wurzel der Zeit, das ist nur Darstellung."""
    per_day = BARS_PER_DAY[tf]
    reach = min(fan.shape[1], FAN_REACH / per_day)
    days = np.linspace(0, reach, 60)
    steps = np.arange(1, fan.shape[1] + 1)
    out = {}
    for name, q in zip(("q05", "q10", "q50", "q90", "q95"), fan):
        late = np.interp(days, steps, q)
        early = q[0] * np.sqrt(days)
        out[name] = price * np.exp(np.where(days < 1, early, late))
    return last_x + days * per_day, out


def chart(live, snapshot, tf, shown):
    frame = live.frame(tf).tail(SEND_BARS)
    if frame.empty:
        return go.Figure().add_annotation(text=f"Für {tf} sind noch keine Kurse da. Der Ladejob läuft im Hintergrund, die Tages-Timeframes gehen schon.", showarrow=False, font={"color": INK_2, "size": 14}).update_layout(
            paper_bgcolor=SURFACE, plot_bgcolor=SURFACE, xaxis_visible=False, yaxis_visible=False)
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.84, 0.16], vertical_spacing=0.02)
    n, x, labels = len(frame), np.arange(len(frame)), time_labels(frame.index, tf)
    now, price = snapshot["now"], snapshot["price"]
    fig.add_trace(go.Candlestick(x=x, open=frame.open, high=frame.high, low=frame.low, close=frame.close, name="Kurs", text=labels, hoverinfo="text+y",
                                 increasing={"line": {"color": UP, "width": 1}, "fillcolor": UP}, decreasing={"line": {"color": DOWN, "width": 1}, "fillcolor": DOWN}), row=1, col=1)
    fig.add_trace(go.Bar(x=x, y=frame.volume, name="Volumen", marker={"color": MUTED, "line": {"width": 0}}, showlegend=False, customdata=labels, hovertemplate="%{customdata}<br>Volumen %{y:,.0f}<extra></extra>"), row=2, col=1)

    overlay = live.overlays(tf, now)
    times = frame.index
    position = lambda ts: int(np.searchsorted(times, ts))
    low_view, high_view = frame.low.tail(VIEW_BARS).min(), frame.high.tail(VIEW_BARS).max()
    x_end = n + 5

    if "bollinger" in shown and overlay["bollinger"]:
        band = overlay["bollinger"]
        keep = np.searchsorted(band["ts"], times[0])
        bx = np.searchsorted(times, band["ts"][keep:])
        for name, key, width in (("Bollinger", "upper", 1), ("Bollinger Mitte", "middle", 1), ("Bollinger unten", "lower", 1)):
            fig.add_trace(go.Scatter(x=bx, y=band[key][keep:], mode="lines", name=name, line={"color": INK_2, "width": width}, opacity=0.55, legendgroup="bb", showlegend=key == "upper", hoverinfo="skip"), row=1, col=1)

    if "fan" in shown and snapshot["fan"] is not None:
        fx, q = fan_points(snapshot["fan"], tf, price, n - 1)
        x_end = max(x_end, fx[-1] + 2)
        wash = "rgba(25,158,112,0.10)"
        for low, high, group in (("q05", "q95", "5–95 %"), ("q10", "q90", "10–90 %")):
            fig.add_trace(go.Scatter(x=fx, y=q[high], mode="lines", line={"width": 0}, showlegend=False, hoverinfo="skip", legendgroup="fan"), row=1, col=1)
            fig.add_trace(go.Scatter(x=fx, y=q[low], mode="lines", line={"width": 0}, fill="tonexty", fillcolor=wash, showlegend=False, hoverinfo="skip", legendgroup="fan", name=group), row=1, col=1)
        fig.add_trace(go.Scatter(x=fx, y=q["q50"], mode="lines", name="Monte Carlo: Median, 10–90 %, 5–95 %", line={"color": FAN, "width": 2}, legendgroup="fan", hoverinfo="skip"), row=1, col=1)
        low_view, high_view = min(low_view, q["q10"].min()), max(high_view, q["q90"].max())

    if "analogs" in shown and overlay["analogs"]:
        for i, analog in enumerate(overlay["analogs"]):
            fig.add_trace(go.Scatter(x=n - 1 + analog["steps"], y=price * np.exp(analog["path"]), mode="lines", name="Top-Analogien (Folgeverlauf)", legendgroup="analog", showlegend=i == 0,
                                     line={"color": ANALOG, "width": 1}, hovertemplate=f"Analogie {analog['label']}<extra></extra>"), row=1, col=1)
        x_end = max(x_end, n + ANALOG_BARS + 2)

    view_left = max(n - VIEW_BARS, -1)
    pad = 0.03 * (high_view - low_view or high_view)
    y_range = [low_view - pad, high_view + pad]

    if "fib" in shown and overlay["fib"]:
        first = True
        labeled = -np.inf
        for level in sorted(overlay["fib"], key=lambda f: f["price"]):
            if not y_range[0] <= level["price"] <= y_range[1]:
                continue
            start = max(position(level["ts"]), 0)
            fig.add_trace(go.Scatter(x=[start, n + 2], y=[level["price"]] * 2, mode="lines", name="Fibonacci", legendgroup="fib", showlegend=first, line={"color": FIB, "width": 1},
                                     hovertemplate=f"Fibonacci {number(100 * level['level'], 1)} %: {number(level['price'])} $<extra></extra>"), row=1, col=1)
            if level["price"] - labeled > 0.025 * (y_range[1] - y_range[0]):  # Liegen Niveaus eng beieinander, bleibt der Rest im Tooltip
                fig.add_annotation(x=n + 2, y=level["price"], text=f"{number(100 * level['level'], 1)} %", showarrow=False, xanchor="left", font={"size": 11, "color": INK_2}, row=1, col=1)
                labeled = level["price"]
            first = False

    if "patterns" in shown and overlay["patterns"]:
        first = True
        for event in overlay["patterns"]:
            if event["ts"] < times[0]:
                continue
            start, bar = position(event["start"]), position(event["ts"])
            end = min(bar + max(10, 3 * (bar - start)), n + 2)
            detail = f"{event['name']} ({'bullisch' if event['side'] > 0 else 'bärisch'}), Skala {event['k']:g} ATR<br>Entry {number(event['entry'])} · SL {number(event['sl'])} · TP {number(event['tp'])}"
            for key, color, label in (("entry", INK, "Entry"), ("sl", DOWN if event["side"] > 0 else UP, "SL"), ("tp", UP if event["side"] > 0 else DOWN, "TP")):
                fig.add_trace(go.Scatter(x=[bar, end], y=[event[key]] * 2, mode="lines", name="Muster: Entry, SL, TP", legendgroup="patterns", showlegend=first, line={"color": color, "width": 1, "dash": "dot"},
                                         hovertemplate=f"{detail}<br>{label}<extra></extra>"), row=1, col=1)
                first = False
        event = overlay["patterns"][-1]
        if event["ts"] >= times[0]:  # Nur das juengste Muster bekommt Flaeche und Namen, die uebrigen stehen im Tooltip
            fig.add_vrect(x0=position(event["start"]), x1=position(event["ts"]), fillcolor=INK, opacity=0.05, line_width=0, row=1, col=1)
            fig.add_annotation(x=position(event["ts"]), y=event["entry"], text=event["name"], showarrow=True, arrowcolor=MUTED, arrowhead=0, ay=-34, ax=0, font={"size": 12, "color": INK}, row=1, col=1)

    step = max(1, n // 40)
    tick_positions = list(range(0, n, step))
    fig.update_layout(paper_bgcolor=SURFACE, plot_bgcolor=SURFACE, font={"color": INK_2, "family": "system-ui, -apple-system, Segoe UI, sans-serif", "size": 12}, margin={"l": 8, "r": 60, "t": 8, "b": 8},
                      uirevision=f"{snapshot['symbol']}-{tf}", dragmode="pan", hovermode="x", hoverlabel={"bgcolor": "#2c2c2a", "font": {"color": INK}}, spikedistance=-1, bargap=0.2, legend={"orientation": "h", "y": 1.0, "x": 0, "yanchor": "top", "bgcolor": "rgba(26,26,25,0.7)", "font": {"size": 12, "color": INK_2}},
                      xaxis_rangeslider_visible=False)
    fig.update_xaxes(showgrid=True, gridcolor=GRID, zeroline=False, linecolor=GRID, range=[view_left, x_end], tickvals=tick_positions, ticktext=[labels[i] for i in tick_positions], showticklabels=False, showspikes=True, spikemode="across", spikesnap="cursor", spikecolor=MUTED, spikethickness=1, spikedash="solid", row=1, col=1)
    fig.update_xaxes(showgrid=True, gridcolor=GRID, zeroline=False, linecolor=GRID, range=[view_left, x_end], tickvals=tick_positions, ticktext=[labels[i] for i in tick_positions], tickfont={"color": MUTED}, row=2, col=1)
    fig.update_yaxes(side="right", showgrid=True, gridcolor=GRID, zeroline=False, linecolor=GRID, tickfont={"color": MUTED}, range=y_range, row=1, col=1)
    fig.update_yaxes(side="right", showgrid=False, zeroline=False, linecolor=GRID, tickfont={"color": MUTED}, nticks=3, row=2, col=1)
    fig.add_hline(y=price, line={"color": MUTED, "width": 1}, row=1, col=1)
    return fig


# ---------------------------------------------------------------------------
# Panels
# ---------------------------------------------------------------------------

def market_state(snapshot):
    if snapshot["fraction"] is None:
        return "Markt geschlossen"
    if not snapshot["traded_today"]:
        return "Handelszeit, noch kein Trade"
    return f"Markt offen, letzter Trade vor {max(snapshot['now'] - snapshot['trade_ts'], 0):.0f} s"


def hero(snapshot):
    when = pd.Timestamp(snapshot["now"], unit="s", tz="UTC").tz_convert(NY)
    return [html.Span(snapshot["symbol"], className="symbol"), html.Span(f"{number(snapshot['price'])} $", className="price"),
            html.Span(f"{pct(snapshot['change'], 2, sign=True)} seit dem letzten Schluss", className="change"),
            html.Span(f"{market_state(snapshot)} · Stand {when:%d.%m.%Y %H:%M:%S} New York", className="state")]


def known_tickers():
    return sorted(path.name.removesuffix("_now.npz") for path in OOS.glob("*_now.npz"))


def known_line():
    return f"Voll geprüft: {', '.join(known_tickers()) or 'noch keine'}. Jeder andere US-Ticker geht auch: Kurse und Basisrate sofort, die Prüfung läuft dann mehrere Stunden im Hintergrund."


def chances(snapshot):
    tiles = []
    for r in snapshot["rows"]:
        items = [html.Div(f"In {HORIZON_TEXT[r['horizont']]}", className="when"), html.Div(pct(r["p_bull"], 0), className="value"), html.Div("Chance, höher zu stehen als jetzt", className="what")]
        if "median" in r:
            items += [fact("Typischer Fall", pct(r["median"], 1, True)), fact("Wenn höher, typisch", pct(r["mid_up"], 1, True)), fact("Wenn tiefer, typisch", pct(r["mid_down"], 1, True))]
        items.append(fact("Früher so oft gestiegen", pct(r["basisrate"], 0)))
        tiles.append(html.Div(items, className="card chance"))
    return tiles


def verdict(live, snapshot):
    proven = [r["horizont"] for r in snapshot["rows"] if r["beleg"]]
    if not live.stack:
        return [html.Strong("Noch nichts geprüft. "), "Die Prozente sind die reine Basisrate dieser Aktie. Monte Carlo und Spanne laufen, sobald der Graph steht; Netze und Prüfung entstehen im Hintergrund."]
    if proven:
        return [html.Strong(f"Richtung belegt bei {', '.join(HORIZON_TEXT[h] for h in proven)}. "), "Vorsprung gegen die Basisrate in beiden Prüfzeiträumen."]
    checked = [r["horizont"] for r in snapshot["rows"] if r["geprueft"]]
    risk_part = f" Belastbar sind Spanne und Risiko bei {', '.join(HORIZON_TEXT[h] for h in checked)}." if checked else ""
    return [html.Strong("Kein Kaufsignal: Keine Richtung belegt. "), f"Die Chancen entsprechen im Kern der Quote, mit der diese Aktie früher gestiegen ist. Das Modell hat diese Quote in den Prüfzeiträumen nicht geschlagen.{risk_part}"]


def card(live, snapshot, row):
    p, base = row["p_bull"], row["basisrate"]
    name = row["horizont"]
    price = snapshot["price"]
    items = [html.H3(f"{snapshot['symbol']} in {HORIZON_TEXT[name]}: {pct(p, 0)} Bullish / {pct(1 - p, 0)} Bearish"),
             html.Div([html.Div(className="bull", style={"width": f"{100 * p:.1f}%"}), html.Div(className="bear", style={"width": f"{100 * (1 - p):.1f}%"}),
                       html.Div(className="tick", style={"left": f"{100 * base:.1f}%"}, title=f"Basisrate {pct(base)}")], className="split"),
             fact("Genau", f"{pct(p)} / {pct(1 - p)}"), fact("Basisrate (Strich)", pct(base))]
    if "von" in row:
        items += [fact("Spanne 80 %", f"{number(price * (1 + row['von']))} bis {number(price * (1 + row['bis']))} $"), fact("in Prozent", f"{pct(row['von'], 1, True)} bis {pct(row['bis'], 1, True)}"),
                  fact("VaR 95 / 99", f"{pct(row['var95'])} / {pct(row['var99'])}")]
    items.append(chip("good", "✓", "Richtung belegt") if row["beleg"] else chip("none", "–", "Richtung nicht belegt"))
    if row["geprueft"]:
        items.append(chip("good", "✓", "Risiko im Backtest bestanden"))
    elif row["var_quote"] is not None:
        items.append(chip("warn", "!", f"Risiko im Backtest durchgefallen: VaR 95 in {pct(row['var_quote'])} statt 5 % der Fälle überschritten"))
    else:
        items.append(chip("warn", "!", "Risiko nicht geprüft: zu wenige Zeiträume" if live.stack else "Risiko noch nicht geprüft"))
    if "von" in row and row["von"] < -row["var95"]:  # Conformal weitet beide Seiten, auch wenn die Spanne nur nach oben verfehlt wurde
        items.append(chip("warn", "!", "Spanne im Test zu oft verfehlt und deshalb geweitet, ihre Untergrenze liegt jetzt unter dem VaR 95"))
    track = live.track.get(name)
    if track and track["n_unabh"] < 100 and track["p_mittel"] > track["quote"] + 0.03:
        items.append(chip("warn", "!", f"Anzeige lag bisher höher: {pct(track['p_mittel'], 0)} angezeigt, {pct(track['quote'], 0)} eingetreten, {int(track['n_unabh'])} unabhängige Zeiträume"))
    return html.Div(items, className="card")


def risk_panel(snapshot):
    rows = []
    for r in snapshot["rows"]:
        if "von" in r:
            rows.append([HORIZON_TEXT[r["horizont"]], pct(r["median"], 1, True), f"{pct(r['von'], 1, True)} bis {pct(r['bis'], 1, True)}", pct(r["var95"]), pct(r["var99"]), pct(r["cvar95"]), pct(r["drawdown95"]), pct(r["mc_up"])])
    if not rows:
        return html.Div([html.H2("Risiko"), html.P("Monte Carlo startet, sobald der Beziehungsgraph diesen Ticker kennt.")], className="panel")
    children = [html.H2(f"Risiko aus {number(snapshot['paths'], 0)} Monte-Carlo-Pfaden, alle {TICK:.0f} s ab dem aktuellen Kurs"),
                table(["Horizont", "Median", "Spanne 80 %", "VaR 95", "VaR 99", "CVaR 95", "Drawdown 95", "P(steigt)"], rows)]
    event = snapshot.get("tp_sl")
    if event:
        when = event["ts"].tz_convert(NY)
        head = f"Jüngstes Muster heute: {event['name']} auf {event['tf']}, {when:%H:%M}. Entry {number(event['entry'])}, SL {number(event['sl'])}, TP {number(event['tp'])}. "
        tail = "Der Kurs steht schon jenseits von TP oder SL." if event.get("p_tp") is None else f"Laut Monte Carlo bis 1 Monat: TP zuerst {pct(event['p_tp'], 0)}, SL zuerst {pct(event['p_sl'], 0)}, keines {pct(event['p_keins'], 0)}. Zum Tagesschluss geprüft."
        children.append(html.P(head + tail))
    return html.Div(children, className="panel")


def regime_panel(live, snapshot, tf):
    state = live.overlays(tf, snapshot["now"])["regime"]
    known = lambda key: key in state and np.isfinite(state[key])
    rows = []
    for key, label, text in (("zscore20", "Z-Score 20", lambda v: number(v)), ("bb_pct", "Bollinger %B", lambda v: number(v)), ("rsi14", "RSI 14", lambda v: number(v, 0)),
                             ("adf", "ADF", lambda v: f"{number(v)}: {'stationär' if v < -2.86 else 'nicht stationär'}"), ("half_life", "Halbwertszeit", lambda v: f"{number(v, 0)} Bars"),
                             ("vr2", "Variance Ratio", lambda v: number(v)), ("hurst", "Hurst, 256 Bars", lambda v: number(v)), ("macd_hist", "MACD-Histogramm", lambda v: pct(v, 2, True)),
                             ("roc10", "ROC 10", lambda v: f"{number(v, 1)} %"), ("mom_12_1", "12-1-Momentum", lambda v: pct(v, 1, True))):
        if known(key):
            rows.append([label, text(state[key])])
    return html.Div([html.H2(f"Mean Reversion und Momentum auf {tf}, je fertigem Bar neu getestet"), table(["", ""], rows, "text") if rows else html.P("Für diesen Timeframe zu wenige Bars."),
                     html.P("Ob diese Signale bei dieser Aktie je einen Vorsprung hatten, steht bei den Thesen.")], className="panel")


def logbook_panel(live):
    children = [html.H2("Prognose-Logbuch")]
    score = live.score
    if score.empty:
        children.append(html.P("Noch nichts fällig. Jede Prognose im Handel wird gespeichert und nach dem Nachtlauf mit dem echten Kurs verglichen."))
    else:
        rows = []
        for r in score.to_dict("records"):
            due = int(r["faellig"]) > 0
            rows.append([HORIZON_TEXT[r["horizont"]], number(r["prognosen"], 0), number(r["faellig"], 0), number(r["unabhaengig"], 0) if due else "–", pct(r["angezeigt"]) if due else "–",
                         pct(r["tatsaechlich"]) if due else "–", pct(r["brier_skill"], 2, True) if due else "–", pct(r["in_spanne"]) if due else "–"])
        children.append(table(["Horizont", "Prognosen", "Fällig", "Unabhängig", "Angezeigt", "Eingetreten", "Brier Skill", "In der Spanne"], rows))
    return html.Div(children, className="panel")


def theses_panel(live):
    if not live.theses:
        return html.Div([html.H2("Thesen"), html.P("Die Messungen entstehen im Hintergrund.")], className="panel")
    return html.Div([html.H2(f"Deine Thesen, gemessen an {live.symbol}"), table(["These", "Messung", "Urteil"], [list(t) for t in live.theses], "text")], className="panel")


def backtest_panel(live):
    frame = live.backtest
    if frame.empty:
        return html.Div([html.H2("Strategie-Backtest"), html.P("Für diesen Ticker noch nicht gerechnet.")], className="panel")
    rows = []
    for r in frame.to_dict("records"):
        proven = "–" if pd.isna(r["rendite_p"]) else ("Rendite" if r["rendite_belegt"] else "Sharpe" if r["sharpe_belegt"] else "nein")
        rows.append([r["strategie"].replace("Volatilitaet", "Volatilität"), pct(r["rendite"], 1, True), pct(r["nach_steuer"], 1, True), number(r["sharpe"]), pct(r["drawdown"]), pct(r["investiert"], 0), number(r["orders"], 0), proven])
    return html.Div([html.H2("Strategie-Backtest: Was hätte das Signal nach Kosten gebracht?"),
                     table(["Strategie", "Rendite p. a.", "Nach Steuer", "Sharpe", "Max. Einbruch", "Investiert", "Orders", "Besser als Halten belegt"], rows),
                     html.P("Vergangenheit im selben Zeitraum, Regeln vorab festgelegt. Die Aktie wurde mit Wissen um ihren Verlauf ausgewählt, Halten von SPY ist deshalb die fairere Referenz.")], className="panel")


def umlauts(text):
    return text.replace("Volatilitaet", "Volatilität").replace("Profitabilitaet", "Profitabilität").replace("Gewinnueberraschung", "Gewinnüberraschung").replace("Insiderkaeufe", "Insiderkäufe")


def factor_panel(title, command, frame, tests, today, symbol, public):
    """Rang des Tickers und Top 10 nur lokal: Eine oeffentliche Liste einzelner Aktien saehe aus wie eine Empfehlung."""
    if frame.empty:
        return html.Div([html.H2(title), html.P(f"Noch nicht gerechnet: python main.py {command}")], className="panel")
    children = [html.H2(f"{title}: Schlägt eine Auswahl den Index?")]
    proven = tests[tests.belegt == 1]
    children.append(html.P(html.Strong("Keine Strategie ist belegt besser. " if proven.empty else f"Belegt: {umlauts(', '.join(sorted(set(proven.strategie))))}. ")))
    children.append(table(["Strategie", "Rendite p. a.", "Nach Steuer", "Sharpe", "Max. Einbruch", "Mit 10.000 $"],
                          [[umlauts(r["strategie"]), pct(r["rendite"], 1, True), pct(r["nach_steuer"], 1, True), number(r["sharpe"]), pct(r["drawdown"]), "–" if pd.isna(r["klein"]) else pct(r["klein"], 1, True)] for r in frame.to_dict("records")]))
    if not public and not today.empty:
        own = today[today.aktie == symbol]
        children.append(html.P(f"{symbol} am {today.stand.iloc[0]}: " + (", ".join(f"{umlauts(r['faktor'])} Rang {r['rang']} von {r['von']}" for r in own.to_dict("records")) if len(own) else "nicht im S&P 500 oder ohne Rang") + ". Rang ist Statistik, kein Kaufsignal."))
        rows = [[umlauts(name), ", ".join(group.sort_values("rang").aktie.head(10))] for name, group in today.groupby("faktor")]
        children.append(table(["Top 10 je Faktor", ""], rows, "text"))
    return html.Div(children, className="panel")


def ranking_panel(live, public=False):
    return factor_panel("Rangliste S&P 500", "rank", live.rank_result, getattr(live, "rank_test", None), getattr(live, "rank_today", None), getattr(live, "symbol", None), public)


def paper_panel(live, public=False):
    """Der Vorwaertstest. Die Aktien selbst nur lokal, wie bei der Rangliste."""
    children = [html.H2("Musterdepot: kein echtes Geld, keine Orders")]
    frame, held = live.paper_result, live.paper_held
    if held.empty:
        children.append(html.P("Noch keine Entscheidung eingefroren: python main.py paper"))
        return html.Div(children, className="panel")
    if frame.empty or "rendite" not in frame or frame.rendite.isna().all():
        children.append(html.P(f"Entscheidung für {held.monat.iloc[0]} ist eingefroren, die erste Ausführung steht noch aus."))
    else:
        first = frame.iloc[0]
        children.append(html.P(f"Seit {first['seit']}, {int(first['handelstage'])} Handelstage. Vor 12 Monaten gibt es kein Urteil, die Zahlen sind bis dahin fast nur Zufall."))
        children.append(table(["Strategie", "Rendite gesamt", "Nach Steuer", "Max. Einbruch", "Orders"],
                              [[umlauts(r["strategie"]), pct(r["rendite"], 1, True), pct(r["nach_steuer"], 1, True), pct(r["drawdown"]), number(r["orders"], 0)] for r in frame.to_dict("records")]))
    if not public:
        rows = [[umlauts(name), ", ".join(sorted(group.aktie))] for name, group in held.groupby("strategie")]
        children.append(table([f"Aktien, Stand {held.monat.iloc[0]}", ""], rows, "text"))
    return html.Div(children, className="panel")


def fundamentals_panel(live, public=False):
    return factor_panel("Bilanz und Insider, S&P 500", "fundamentals", live.fund_result, live.fund_test, live.fund_today, live.symbol, public)


def clock_panel(engine, live):
    children = [html.H2("Takt und Hintergrund")]
    periods, durations = np.array(engine.periods), np.array(engine.durations)
    rows = []
    if len(periods):
        rows.append(["5-Sekunden-Takt", f"Ø {number(periods.mean())} s, längster {number(periods.max())} s, {len(periods)} Läufe"])
    if len(durations):
        rows.append(["Rechenzeit je Takt", f"Ø {number(1000 * durations.mean(), 0)} ms, längste {number(1000 * durations.max(), 0)} ms"])
    rows.append(["Matching", f"{number(len(live.index), 0)} Sequenzen" if live.index is not None else "wird geladen"])
    if live.nets_day is not None:
        rows.append(["Netze trainiert bis", f"{pd.Timestamp(live.nets_day, unit='D'):%d.%m.%Y}"])
    rows.append(["Live-Volumen", "nur IEX, nach dem Nachtlauf Vollmarkt"])
    if engine.replay_seconds is not None:
        rows.append(["Modus", f"Wiedergabe: 1 Minute je {number(engine.replay_seconds, 1)} s, kein Logbuch"])
    if len(engine.steps):
        for step, r in engine.steps.iterrows():
            rows.append([step.replace("pruefung", "prüfung"), STATUS_TEXT.get(r["status"], r["status"]) + (f": {r['message']}" if r["message"] else "")])
    if live.risk_note and live.state is None:
        rows.append(["Risiko", "wartet auf den Graphen"])
    children.append(table(["", ""], rows, "text"))
    return html.Div(children, className="panel")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

def create(engine):
    app = Dash("iontrader", assets_folder=str(ROOT / "assets"), title="IonTrader", update_title=None)
    app.layout = html.Div([
        html.Div([html.Span("IonTrader", className="brand"),
                  html.Div([html.Label(["Ticker ", dcc.Input(id="ticker", value=engine.wanted, type="text", debounce=False, maxLength=10, autoComplete="off", list="known-list")]),
                            html.Datalist(id="known-list"), html.Button("Laden", id="go", n_clicks=0)], className="ticker-form"),
                  dcc.RadioItems(id="tf", options=TIMEFRAMES, value="5m", className="choices segments", inline=True),
                  dcc.Checklist(id="shown", options=[{"label": v, "value": k} for k, v in OVERLAYS.items()], value=list(OVERLAYS), className="choices", inline=True),
                  html.Span(id="message", className="message")], className="bar"),
        html.Div(id="known", className="known"),
        html.Div(id="hero", className="hero"),
        html.Div(id="chances", className="cards"),
        html.Div(id="verdict", className="verdict"),
        html.Div(id="cards", className="cards"),
        html.Div(dcc.Graph(id="chart", responsive=True, style={"height": "660px"}, config={"displaylogo": False, "scrollZoom": True, "modeBarButtonsToRemove": ["select2d", "lasso2d", "autoScale2d"]}), className="chart-card"),
        html.Div(id="panels", className="panels"),
        html.Div("Statistische Auswertung der Kursgeschichte, keine Anlageberatung. Es werden keine Orders gesendet.", className="foot"),
        dcc.Interval(id="clock", interval=int(TICK * 1000)),
    ], className="page")

    @app.callback(Output("message", "children"), Input("go", "n_clicks"), Input("ticker", "n_submit"), State("ticker", "value"), prevent_initial_call=True)
    def choose(_, __, value):
        if value and value.strip():
            engine.request(value)
            return f"{value.strip().upper()} wird geladen"
        return "Bitte einen Ticker eingeben"

    @app.callback(Output("known", "children"), Output("known-list", "children"), Input("clock", "n_intervals"))
    def known(_):
        return known_line(), [html.Option(value=symbol) for symbol in known_tickers()]

    @app.callback(Output("chart", "figure"), Output("hero", "children"), Output("chances", "children"), Output("verdict", "children"), Output("cards", "children"), Output("panels", "children"), Output("message", "children", allow_duplicate=True),
                  Input("clock", "n_intervals"), Input("tf", "value"), Input("shown", "value"), prevent_initial_call="initial_duplicate")
    def refresh(_, tf, shown):
        live = engine.live
        snapshot = live.snapshot if live is not None else None
        waiting = f"{engine.wanted} wird geladen" if engine.wanted and (live is None or live.symbol != engine.wanted) else ""
        if snapshot is None:
            empty = go.Figure().update_layout(paper_bgcolor=SURFACE, plot_bgcolor=SURFACE, xaxis_visible=False, yaxis_visible=False)
            return empty, "", [], "", [], [], engine.error or f"{engine.wanted} wird geladen"
        return (chart(live, snapshot, tf, shown or []), hero(snapshot), chances(snapshot), verdict(live, snapshot), [card(live, snapshot, r) for r in snapshot["rows"]],
                [risk_panel(snapshot), paper_panel(live), fundamentals_panel(live), ranking_panel(live), backtest_panel(live), regime_panel(live, snapshot, tf), theses_panel(live), clock_panel(engine, live), logbook_panel(live)], engine.error or waiting)

    return app


def run(symbol, replay_seconds=None, open_browser=True, port=8050):
    import logging

    from . import exit_now

    logging.getLogger("werkzeug").setLevel(logging.ERROR)  # Sonst eine Zeile je Takt in der Konsole
    engine = Engine(replay_seconds)
    engine.start(symbol)
    app = create(engine)
    if open_browser:  # Erst wenn der Server sicher lauscht
        import threading
        import webbrowser

        threading.Timer(2.0, webbrowser.open, args=(f"http://127.0.0.1:{port}",)).start()
    print(f"IonTrader laeuft auf http://127.0.0.1:{port}, beenden mit Strg+C", flush=True)
    try:
        app.run(host="127.0.0.1", port=port, debug=False)
    finally:
        exit_now()
