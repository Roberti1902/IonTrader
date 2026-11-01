"""Phase 8: Rangliste ueber den S&P 500. Auswahl aus allen damaligen Mitgliedern, auch den spaeter verschwundenen."""
import io
import os
from datetime import datetime

import numpy as np
import pandas as pd
import requests

from . import ROOT, ingest
from .backtest import DAYS_PER_YEAR, TAX, Run, boot_indices, cash_return, compare, stats
from .store import connect, load, replace_rows
from .study import fdr_q
from .train import REPORTS

CAPITAL, SMALL_CAPITAL = 100_000.0, 10_000.0
COST, FEE = 0.0005, 1.0
TOP, KEEP = 50, 100
MIN_CHANGE = 0.25  # Anteil am Zielgewicht
LOOKBACK, SKIP, MONTH = 252, 21, 21
JUMP = 0.6  # Tagesspruenge darueber gelten als Datenfehler-Verdacht
DELIST_DROP, DELIST_PENALTY = -0.30, 0.30
START, SPLIT = pd.Timestamp("2017-01-01", tz="UTC"), pd.Timestamp("2022-01-01", tz="UTC")
BENCHMARK, RATE_SYMBOL = "SPY", "^IRX"
PRICES = ROOT / "data" / "universe_daily.pkl"
CHANGES = ROOT / "data" / "sp500_changes.csv"
AGENT = {"User-Agent": "IonTrader research (github.com/Roberti1902/IonTrader)"}
WIKI = "https://en.wikipedia.org/wiki/"


# ---------------------------------------------------------------------------
# Mitglieder
# ---------------------------------------------------------------------------

def membership(current, changes, days):
    """Mitglieder je Tag, von heute rueckwaerts. changes: Spalten date, add, rem. Liefert {Symbol: bool-Array}."""
    members = set(current)
    frame = changes.sort_values("date", ascending=False)
    out = {symbol: np.zeros(len(days), dtype=bool) for symbol in set(current) | set(frame["add"].dropna()) | set(frame["rem"].dropna())}
    rows = list(frame.itertuples())
    i = 0
    for t in range(len(days) - 1, -1, -1):
        while i < len(rows) and rows[i].date > days[t]:  # Eine Aenderung gilt ab ihrem Stichtag
            if pd.notna(rows[i].add):
                members.discard(rows[i].add)
            if pd.notna(rows[i].rem):
                members.add(rows[i].rem)
            i += 1
        for symbol in members:
            out[symbol][t] = True
    return out


def fetch_members():
    tables = pd.read_html(io.StringIO(requests.get(WIKI + "List_of_S%26P_500_companies", headers=AGENT, timeout=60).text))
    current = tables[0].Symbol.tolist()
    changes = pd.read_html(io.StringIO(requests.get(WIKI + "Historical_components_of_the_S%26P_500", headers=AGENT, timeout=60).text))[0]
    changes.columns = ["date", "add", "add_name", "rem", "rem_name", "reason", "refs"]
    changes["date"] = pd.to_datetime(changes["date"], format="%B %d, %Y", errors="coerce", utc=True)
    changes = changes.dropna(subset=["date"])[["date", "add", "rem", "reason"]]
    changes.to_csv(CHANGES, index=False)
    return current, changes


def ingest_prices(symbols, log):
    """Tagesbars von Alpaca in einer Datei. Enthaelt auch Aktien, die heute nicht mehr gehandelt werden."""
    from alpaca.data.enums import Adjustment
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame

    client = StockHistoricalDataClient(os.environ["ALPACA_API_KEY"], os.environ["ALPACA_SECRET_KEY"])
    end = pd.Timestamp.now(tz="UTC") - pd.Timedelta(minutes=16)
    parts = []
    for i in range(0, len(symbols), 100):
        parts.append(client.get_stock_bars(StockBarsRequest(symbol_or_symbols=symbols[i:i + 100], timeframe=TimeFrame.Day, adjustment=Adjustment.ALL, start=pd.Timestamp("2016-01-01", tz="UTC"), end=end)).df)
        log(f"Kurse: {min(i + 100, len(symbols))} von {len(symbols)}")
    frame = pd.concat(parts).reset_index()[["symbol", "timestamp", "open", "close"]]
    frame.to_pickle(PRICES)
    return frame


def yahoo_check(days, open_, close, log):
    """Yahoo bereinigt auch Abspaltungen, Alpaca nicht; dafuer fehlen bei Yahoo verschwundene Aktien. Ersetzt, wo Yahoo die Zeit abdeckt."""
    import yfinance as yf

    symbols = [s for s in close.columns if close[s].notna().iloc[-1]]
    raw = yf.download([s.replace(".", "-") for s in symbols], start="2016-01-01", auto_adjust=True, threads=True, progress=False)
    raw.index = pd.to_datetime(raw.index).tz_localize("UTC")
    o, c, swapped = open_.copy(), close.copy(), 0
    for s in symbols:
        yc = raw["Close"][s.replace(".", "-")].reindex(days)
        if yc.notna().sum() >= 0.98 * close[s].notna().sum():
            c[s], o[s], swapped = yc, raw["Open"][s.replace(".", "-")].reindex(days), swapped + 1
    log(f"Yahoo ersetzt {swapped} von {close.shape[1]} Aktien")
    return o, c, swapped


def to_matrix(frame):
    """Tage mal Aktien auf dem Kalender des Index. Fehlt ein Bar, steht dort NaN."""
    frame = frame.assign(day=pd.to_datetime(frame.timestamp, utc=True).dt.normalize())
    days = pd.DatetimeIndex(sorted(frame.day[frame.symbol == BENCHMARK].unique()))
    open_ = frame.pivot(index="day", columns="symbol", values="open").reindex(days)
    close = frame.pivot(index="day", columns="symbol", values="close").reindex(days)
    return days, open_, close


# ---------------------------------------------------------------------------
# Faktoren und Auswahl
# ---------------------------------------------------------------------------

def month_ends(days):
    """Letzter Handelstag je Monat, als Position im Kalender."""
    months = days.tz_localize(None).to_period("M")
    return np.flatnonzero(months[:-1] != months[1:])


def factor_scores(close):
    """Hoeher ist besser. Jeder Wert nutzt nur Schlusskurse bis zum jeweiligen Tag."""
    ret = close.pct_change(fill_method=None)
    momentum = close.shift(SKIP) / close.shift(LOOKBACK) - 1
    low_vol = -ret.rolling(LOOKBACK, min_periods=200).std()
    reversal = -(close / close.shift(MONTH) - 1)
    suspect = (ret.abs() > JUMP).rolling(LOOKBACK, min_periods=1).sum() > 0
    return {"Momentum 12-1": momentum, "Geringe Schwankung": low_vol, "Umkehr": reversal}, suspect


def combine(a, b):
    return (a.rank(axis=1, pct=True) + b.rank(axis=1, pct=True)) / 2


def select(scores, eligible, held, top=TOP, keep=KEEP):
    """Die besten top; wer schon im Depot ist, bleibt, solange er unter den besten keep steht."""
    order = np.argsort(-np.where(eligible & np.isfinite(scores), scores, -np.inf), kind="stable")
    valid = int((eligible & np.isfinite(scores)).sum())
    order = order[:valid]
    stay = [i for i in order[:keep] if held[i]][:top]
    chosen = set(stay)
    for i in order:
        if len(chosen) == top:
            break
        chosen.add(i)
    weight = np.zeros(len(scores))
    weight[list(chosen)] = 1 / top
    return weight


def vol_scale(close):
    """min(1, bisheriger Median / heutige Schwankung ueber 21 Tage). Ohne Vorgeschichte voll investiert."""
    sigma = close.pct_change(fill_method=None).rolling(MONTH, min_periods=15).std()
    target = sigma.expanding(min_periods=60).median().shift(1)
    return (target / sigma).clip(upper=1.0).where(target.notna() & sigma.notna(), 1.0)


def rank_ic(scores, future, eligible):
    """Rangkorrelation je Monat zwischen Faktor und der folgenden Rendite."""
    values = []
    for s, f, e in zip(scores, future, eligible):
        m = np.isfinite(s) & np.isfinite(f) & e
        if m.sum() >= 50:
            values.append(np.corrcoef(pd.Series(s[m]).rank(), pd.Series(f[m]).rank())[0, 1])
    values = np.array(values)
    return {"ic": float(values.mean()), "t": float(values.mean() / values.std() * np.sqrt(len(values))), "monate": len(values)}


# ---------------------------------------------------------------------------
# Depot
# ---------------------------------------------------------------------------

def simulate(open_, close, targets, rate, years, capital=CAPITAL, cost=COST, fee=FEE, tax=TAX):
    """Mehrere Aktien und Cash. targets[t] ist das Zielgewicht aus dem Schluss von Tag t, gehandelt zur Eroeffnung von t+1."""
    # ponytail: Durchschnittskosten statt FIFO und Zinsen verrechnen mit Aktienverlusten, wie Phase 7.
    n, k = close.shape
    has_bar = np.isfinite(close)
    last_bar = n - 1 - np.argmax(has_bar[::-1], axis=0)
    mark = np.where(np.isfinite(close[0]), close[0], 0.0)
    shares, basis = np.zeros(k), np.zeros(k)
    cash, gain, carry, tax_paid, costs, orders, traded = capital, 0.0, 0.0, 0.0, 0.0, 0, 0.0
    nav, held = np.empty(n), np.empty(n)

    def sell(i, value, price, penalty=0.0):
        nonlocal cash, gain, costs, orders, traded
        share = min(value / max(shares[i] * price, 1e-12), 1.0)
        received = value * (1 - penalty)
        spent = value * cost + fee
        gain += received - spent - basis[i] * share
        basis[i] *= 1 - share
        shares[i] *= 1 - share
        cash += received - spent
        costs += spent
        orders += 1
        traded += value

    for t in range(n):
        if t > 0 and t - 1 in targets:
            prices = np.where(np.isfinite(open_[t]), open_[t], mark)
            total = cash + (shares * prices).sum()
            target = targets[t - 1]
            current = shares * prices
            wanted = target * total
            tradable = np.isfinite(open_[t]) & (prices > 0)
            change = wanted - current
            due = tradable & ((np.abs(change) >= MIN_CHANGE * np.maximum(wanted, current)) | ((target == 0) & (shares > 0)))
            due &= np.abs(change) > 0
            for i in np.flatnonzero(due & (change < 0)):
                sell(i, -change[i], prices[i])
            buys = np.flatnonzero(due & (change > 0))
            if len(buys):
                need = change[buys] * (1 + cost) + fee
                scale = min(1.0, max(cash, 0.0) / need.sum())
                for i in buys:
                    value = change[i] * scale
                    spent = value * cost + fee
                    if value > spent:
                        shares[i] += value / prices[i]
                        basis[i] += value + spent
                        cash -= value + spent
                        costs += spent
                        orders += 1
                        traded += value
        known = np.isfinite(close[t])
        mark[known] = close[t][known]
        for i in np.flatnonzero((shares > 0) & (last_bar == t) & (t < n - 1)):  # Aktie verschwindet
            past = close[max(t - MONTH, 0), i]
            drop = np.isfinite(past) and past > 0 and mark[i] / past - 1 < DELIST_DROP
            sell(i, shares[i] * mark[i], mark[i], DELIST_PENALTY if drop else 0.0)
        worth = (shares * mark).sum()
        nav[t], held[t] = cash + worth, worth
        interest = max(cash, 0.0) * rate[t] / DAYS_PER_YEAR
        cash += interest
        gain += interest
        if t + 1 < n and years[t + 1] != years[t]:
            taxable = gain + carry
            gain, carry = 0.0, min(taxable, 0.0)
            due_tax = max(taxable, 0.0) * tax
            tax_paid += due_tax
            short = due_tax - cash
            if due_tax > 0 and short > 0 and worth > 0:  # Aus dem Depot zahlen, gleichmaessig ueber alle Positionen; der Gewinn zaehlt im neuen Jahr
                for i in np.flatnonzero(shares > 0):
                    sell(i, shares[i] * mark[i] * min((short + fee * (shares > 0).sum()) / worth * 1.01, 1.0), mark[i])
            cash -= due_tax
    for i in np.flatnonzero(shares > 0):
        sell(i, shares[i] * mark[i], mark[i])
    final_tax = max(gain + carry, 0.0) * tax
    return Run(nav, cash - final_tax, float((held / np.maximum(nav, 1e-9)).mean()), orders, traded / nav.mean() / (n / DAYS_PER_YEAR), tax_paid + final_tax, costs)


# ---------------------------------------------------------------------------
# Auswertung
# ---------------------------------------------------------------------------

def build_targets(days, close, members):
    """Die Zielgewichte aller Strategien je Monatsende. Alle Regeln aus GAMEPLAN 8.5 und 8.6."""
    factors, suspect = factor_scores(close)
    factors["Kombination"] = combine(factors["Momentum 12-1"], factors["Geringe Schwankung"])
    scale = vol_scale(close)
    symbols = close.columns.tolist()
    spy = symbols.index(BENCHMARK)
    is_member = np.column_stack([members.get(s, np.zeros(len(days), dtype=bool)) for s in symbols])
    ends = month_ends(days)
    ends = ends[days[ends] >= START]
    k = len(symbols)
    targets = {name: {} for name in ("Momentum 12-1", "Geringe Schwankung", "Kombination", "Umkehr", "Alle gleichgewichtet", "Alle mit Volatilitaet", "SPY mit Volatilitaet")}
    held = {name: np.zeros(k, dtype=bool) for name in factors}
    close_now = close.to_numpy(dtype=float)
    for t in ends:
        tradable = np.isfinite(close_now[t])
        eligible = is_member[t] & tradable
        for name, frame in factors.items():
            weight = select(frame.to_numpy()[t], eligible & ~suspect.to_numpy()[t], held[name])
            targets[name][t], held[name] = weight, weight > 0
        equal = eligible / max(eligible.sum(), 1)
        targets["Alle gleichgewichtet"][t] = equal
        targets["Alle mit Volatilitaet"][t] = equal * scale.to_numpy()[t]
        only_spy = np.zeros(k)
        only_spy[spy] = scale.to_numpy()[t, spy]
        targets["SPY mit Volatilitaet"][t] = only_spy
    return targets, factors, is_member, ends


def evaluate(days, open_, close, members, rate, today_members):
    """Alle Strategien auf demselben Fenster, mit Tests und Information."""
    targets, factors, is_member, ends = build_targets(days, close, members)
    first = int(ends[0])
    o, c = open_.to_numpy(dtype=float)[first:], close.to_numpy(dtype=float)[first:]
    r, years = rate[first:], days[first:].tz_convert(ingest.NY).year.to_numpy()
    shift = lambda t: {key - first: value for key, value in t.items()}
    spy = close.columns.tolist().index(BENCHMARK)
    k = close.shape[1]
    hold_spy = np.zeros(k)
    hold_spy[spy] = 1.0
    survivors = np.array([s in today_members for s in close.columns], dtype=float)
    plain = lambda t, capital=CAPITAL, tax=0.0: simulate(o, c, t, r, years, capital=capital, tax=tax)
    def row(t):
        result = stats(plain(t), plain(t, tax=TAX), r, CAPITAL)
        result["klein"] = stats(plain(t, SMALL_CAPITAL), plain(t, SMALL_CAPITAL, TAX), r, SMALL_CAPITAL)["rendite"]
        return result
    reference = {0: hold_spy}
    ret_spy = np.diff(np.log(plain(reference).nav))
    cash = cash_return(r)
    idx = boot_indices(len(ret_spy))
    late = days[first:][1:] >= SPLIT
    tests = []

    def versus(name, ret, ref, against):
        out = compare(ret, ref, cash, idx)
        for metric in ("rendite", "sharpe"):
            gap = lambda m: float((ret - ref)[m].mean() * DAYS_PER_YEAR) if metric == "rendite" else _sharpe(ret, cash, m) - _sharpe(ref, cash, m)
            tests.append({"strategie": name, "gegen": against, "kennzahl": metric, "diff": out[f"{metric}_diff"], "low": out[f"{metric}_low"], "high": out[f"{metric}_high"], "p": out[f"{metric}_p"], "frueh": gap(~late), "spaet": gap(late)})

    rows = [{"strategie": "Halten SPY", **row(reference)}]
    returns = {}
    for name, target in targets.items():
        target = shift(target)
        rows.append({"strategie": name, **row(target)})
        returns[name] = np.diff(np.log(plain(target).nav))
        versus(name, returns[name], ret_spy, BENCHMARK)
    versus("Alle mit Volatilitaet", returns["Alle mit Volatilitaet"], returns["Alle gleichgewichtet"], "ungesteuert")
    versus("SPY mit Volatilitaet", returns["SPY mit Volatilitaet"], ret_spy, "ungesteuert")
    survivor_targets = {key - first: (close.to_numpy()[key] > 0) * survivors / max(((close.to_numpy()[key] > 0) * survivors).sum(), 1) for key in ends}
    info = stats(plain(survivor_targets), plain(survivor_targets, tax=TAX), r, CAPITAL)
    tests = pd.DataFrame(tests)
    # Die SPY-Steuerung gegen ungesteuert ist derselbe Vergleich wie gegen SPY; gezaehlt wird trotzdem, wie vorab festgelegt
    tests["q"] = fdr_q(tests.p.to_numpy())
    tests["belegt"] = ((tests.q < 0.05) & (tests.frueh > 0) & (tests.spaet > 0)).astype(int)
    # IC auf den Monatsenden
    future = close.shift(-MONTH) / close - 1
    ics = [{"faktor": name, **rank_ic(frame.to_numpy()[ends], future.to_numpy()[ends], is_member[ends])} for name, frame in factors.items()]
    return pd.DataFrame(rows), tests, pd.DataFrame(ics), info, (days[first], days[-1]), first


def _sharpe(ret, cash, mask):
    excess = (ret - cash)[mask]
    return float(excess.mean() / max(excess.std(), 1e-9) * np.sqrt(DAYS_PER_YEAR))


def check_sources(close, con):
    """Stimmen Alpaca und Yahoo ueberein? Grobe Fehler bei Dividenden oder Splits fielen hier auf."""
    rows = []
    for symbol in (BENCHMARK, "META"):
        yahoo = load(con, symbol, "1D").close
        yahoo.index = yahoo.index.normalize()
        ours = close[symbol].dropna()
        both = ours.index.intersection(yahoo.index)
        years = len(both) / DAYS_PER_YEAR
        a, b = (ours[both[-1]] / ours[both[0]]) ** (1 / years) - 1, (yahoo[both[-1]] / yahoo[both[0]]) ** (1 / years) - 1
        rows.append({"symbol": symbol, "alpaca": float(a), "yahoo": float(b), "tage": len(both)})
    return pd.DataFrame(rows)


def today_ranks(close, members, days):
    """Rang je Faktor zum letzten Handelsschluss, unter den heutigen Mitgliedern. Rang 1 ist der beste."""
    factors, suspect = factor_scores(close)
    factors["Kombination"] = combine(factors["Momentum 12-1"], factors["Geringe Schwankung"])
    t = len(days) - 1
    member = pd.Series({s: members.get(s, np.zeros(len(days), dtype=bool))[t] for s in close.columns})
    rows = []
    for name, frame in factors.items():
        score = frame.iloc[t][member & ~suspect.iloc[t]].dropna()
        ranks = score.rank(ascending=False).astype(int)
        rows += [{"aktie": symbol, "faktor": name, "rang": int(rank), "von": len(ranks), "stand": str(days[t].date())} for symbol, rank in ranks.items()]
    return pd.DataFrame(rows)


def _p(x, signed=True):
    return "–" if pd.isna(x) else f"{100 * x:{'+' if signed else ''}.1f} %"


def write_report(results, tests, ics, info, window, sources, jumps, coverage):
    start, end = (d.date() for d in window)
    names = {"rendite": "Rendite p. a.", "sharpe": "Sharpe"}
    value = lambda v, metric: _p(v) if metric == "rendite" else f"{v:+.2f}"
    lines = ["# S&P 500: Phase-8-Report", "", f"Stand {datetime.now():%Y-%m-%d %H:%M}. Statistische Auswertung der Kursgeschichte, keine Anlageberatung. Es wurden keine Orders gesendet.", "",
             f"Zeitraum {start} bis {end}. Auswahl am letzten Handelstag des Monats aus den damaligen Mitgliedern, Ausführung zur nächsten Eröffnung, nur Long. Beste {TOP} gleichgewichtet, gehalten bis außerhalb der besten {KEEP}. Start {CAPITAL:,.0f} $, Kosten {COST * 1e4:.0f} Basispunkte je Seite plus {FEE:.0f} $ je Order. Alle Regeln standen vor dem ersten Lauf fest (GAMEPLAN, Phase 8).", "",
             f"**Daten:** {coverage}. {jumps}", "", "| Abgleich | Alpaca p. a. | Yahoo p. a. | Tage |", "|---|---:|---:|---:|"]
    lines += [f"| {r['symbol']} | {_p(r['alpaca'])} | {_p(r['yahoo'])} | {r['tage']:,} |" for r in sources.to_dict("records")]
    lines += ["", "## Ergebnis", "", f"| Strategie | Rendite p. a. | Nach Steuer p. a. | Endwert nach Steuer | Sharpe | Schwankung | Max. Einbruch | Investiert | Orders | Kosten $ | Mit {SMALL_CAPITAL:,.0f} $ Start | Rendite mit Yahoo | Sharpe mit Yahoo |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    lines += [f"| {r['strategie']} | {_p(r['rendite'])} | {_p(r['nach_steuer'])} | {r['endwert']:,.0f} $ | {r['sharpe']:.2f} | {_p(r['schwankung'], False)} | {_p(r['drawdown'])} | {_p(r['investiert'], False)} | {r['orders']:,} | {r['kosten']:,.0f} | {_p(r['klein'])} | {_p(r['yahoo'])} | {r['yahoo_sharpe']:.2f} |" for r in results.to_dict("records")]
    lines += ["", "„–“ beim kleinen Depot heißt: Die Gebühren je Order haben das Depot aufgezehrt.", "", f"Zur Information, nicht getestet: Nur die heutigen Mitglieder gleichgewichtet hätten {_p(info['rendite'])} p. a. gebracht. Die Differenz zu „Alle gleichgewichtet“ zeigt die Überlebensverzerrung.", "",
              "## Belegt besser?", "", f"Vor Steuern, nach Kosten. Block-Bootstrap wie Phase 7, in Klammern das 95 %-Intervall. q ist korrigiert über alle {len(tests)} Tests. Belegt heißt q < 0,05 und positiv in 2017–2021 und in 2022–2026.", "",
              "| Strategie | Gegen | Kennzahl | Differenz | 2017–2021 | 2022–2026 | q | Belegt |", "|---|---|---|---:|---:|---:|---:|---|"]
    lines += [f"| {r['strategie']} | {r['gegen']} | {names[r['kennzahl']]} | {value(r['diff'], r['kennzahl'])} ({value(r['low'], r['kennzahl'])} bis {value(r['high'], r['kennzahl'])}) | {value(r['frueh'], r['kennzahl'])} | {value(r['spaet'], r['kennzahl'])} | {r['q']:.3f} | {'ja' if r['belegt'] else 'nein'} |" for r in tests.to_dict("records")]
    lines += ["", "## Rang-IC", "", "Rangkorrelation zwischen Faktor und der Rendite der folgenden 21 Handelstage, je Monatsende unter den damaligen Mitgliedern.", "", "| Faktor | Ø IC | t | Monate |", "|---|---:|---:|---:|"]
    lines += [f"| {r['faktor']} | {r['ic']:+.3f} | {r['t']:+.1f} | {r['monate']} |" for r in ics.to_dict("records")]
    won = tests[tests.belegt == 1]
    lines += ["", "## Was das heißt", "", f"Belegt: {', '.join(sorted({f'''{r['strategie']} ({names[r['kennzahl']]})''' for r in won.to_dict('records')})) if len(won) else 'keine Strategie'}.", "",
              "**Grenzen:** Nur Kurse, keine Bilanzdaten. Ein Zeitraum von knapp zehn Jahren mit starkem Markt. Die Mitgliedschaft stammt aus einer rückwärts rekonstruierten Wikipedia-Liste. Der Abschlag für verschwundene Aktien ist eine Annahme. Beträge in Dollar ohne Wechselkurs.", ""]
    path = REPORTS / "SP500_phase8.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def run(con=None, log=None, refresh=True):
    log = log or (lambda text: print(text, flush=True))
    con = con or connect()
    current, changes = fetch_members()
    symbols = sorted({*current, *changes[changes.date >= pd.Timestamp("2015-06-01", tz="UTC")]["add"].dropna(), *changes[changes.date >= pd.Timestamp("2015-06-01", tz="UTC")]["rem"].dropna(), BENCHMARK})
    frame = pd.read_pickle(PRICES) if PRICES.exists() and not refresh else ingest_prices(symbols, log)
    days, open_, close = to_matrix(frame)
    members = membership(current, changes, days)
    coverage = f"{close.shape[1]} von {len(symbols)} Symbolen mit Kursen, {(np.column_stack([members.get(s, np.zeros(len(days), dtype=bool)) for s in close.columns]).sum(1)).mean():.0f} Mitglieder im Schnitt"
    moves = close.pct_change(fill_method=None).abs()
    jump_count = int((moves > JUMP).sum().sum())
    member_jumps = sum(int(((moves[s] > JUMP).to_numpy() & members[s]).sum()) for s in close.columns if s in members)
    jumps = f"Tagessprünge über {100 * JUMP:.0f} %: {jump_count}, davon als Mitglied {member_jumps}."
    sources = check_sources(close, con)
    log(sources.to_string())
    log(jumps)
    if load(con, RATE_SYMBOL, "1D").empty:
        ingest.ingest_daily(RATE_SYMBOL, con)
    rate_frame = load(con, RATE_SYMBOL, "1D").close
    rate_days = rate_frame.index.normalize()
    rate = rate_frame.to_numpy(dtype=float)[np.clip(np.searchsorted(rate_days, days, side="right") - 1, 0, len(rate_frame) - 1)] / 100
    results, tests, ics, info, window, _ = evaluate(days, open_, close, members, rate, set(current))
    yahoo_open, yahoo_close, swapped = yahoo_check(days, open_, close, log)
    other = evaluate(days, yahoo_open, yahoo_close, members, rate, set(current))
    results["yahoo"] = other[0].rendite
    results["yahoo_sharpe"] = other[0].sharpe
    jumps += f" Darunter sind unbereinigte Abspaltungen, gegen Yahoo bestätigt bei RTX 2020 und APTV 2017; echt sind etwa SVB und First Republic 2023. Die Spalten mit Yahoo rechnen dieselben Regeln mit Yahoo-Kursen für {swapped} Aktien, weil Yahoo Abspaltungen bereinigt. Yahoo-Belegt: {int(other[1].belegt.sum())} von {len(other[1])} Tests."
    for table, data in (("rank_result", results), ("rank_test", tests), ("rank_ic", ics), ("rank_today", today_ranks(close, members, days))):
        replace_rows(con, table, "SP500", data)
    path = write_report(results, tests, ics, info, window, sources, jumps, coverage)
    log(f"Report: {path}")
    log(results[["strategie", "rendite", "nach_steuer", "sharpe", "drawdown", "orders", "klein", "yahoo", "yahoo_sharpe"]].to_string())
    log(jumps)
    log(tests[["strategie", "gegen", "kennzahl", "diff", "frueh", "spaet", "q", "belegt"]].to_string())
    log(ics.to_string())
    return results
