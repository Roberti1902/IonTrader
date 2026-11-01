"""Phase 7: Strategie-Backtest. Haette ein Signal nach Kosten und Steuern mehr gebracht als einfaches Halten?"""
import json
from dataclasses import dataclass
from datetime import datetime

import numpy as np
import pandas as pd

from . import ingest, matrix, risk, train
from .matrix import CONFIG, HORIZON_NAMES, sigmoid
from .store import connect, load, replace_rows
from .study import fdr_q, naive_seconds
from .train import OOS, REPORTS

CAPITAL = 10_000.0
COST = 0.0005  # Je Seite: Spread und Slippage
STRESS_COST = 0.002
ORDER_FEE = 1.0
MIN_CHANGE = 0.05  # Kleinere Gewichtsaenderungen loesen keine Order aus
TAX = 0.26375  # Kapitalertragsteuer plus Soli
DAYS_PER_YEAR = 252
BLOCK, N_BOOT = 21, 5000
RATE_SYMBOL = "^IRX"
SIDES = {"1T": 1, "7T": 5, "1M": 21}
STRATEGIES = 10  # Vorab festgelegt, siehe GAMEPLAN 7.5


@dataclass
class Run:
    nav: np.ndarray  # Depotwert je Handelsschluss
    final_after_tax: float  # Nach Verkauf von allem und Steuer
    exposure: float
    orders: int
    turnover: float  # Gehandeltes Volumen je Jahr, in Vielfachen des Depots
    tax_paid: float
    costs: float


def simulate(open_, close, weight, rate=None, years=None, cost=COST, fee=ORDER_FEE, tax=TAX, capital=CAPITAL):
    """Ein Depot aus einer Aktie und Cash. weight[t] ist das Zielgewicht zur Eroeffnung von Tag t.

    Es muss aus Daten bis zum Schluss von Tag t-1 stammen; das stellt to_execution sicher.
    """
    # ponytail: Durchschnittskosten statt FIFO, und Zinsen verrechnen mit Aktienverlusten. Reicht fuer den Vergleich, nicht fuer die Steuererklaerung.
    n = len(close)
    rate = np.zeros(n) if rate is None else rate
    years = np.zeros(n, dtype=int) if years is None else years
    shares, basis, cash = 0.0, 0.0, capital
    gain, carry, tax_paid, costs, orders, traded = 0.0, 0.0, 0.0, 0.0, 0, 0.0
    nav, held = np.empty(n), np.empty(n)

    def sell(value, price):
        nonlocal shares, basis, cash, gain, costs, orders, traded
        spent = value * cost + fee
        share = value / (shares * price)
        gain += value - spent - basis * share
        basis *= 1 - share
        shares *= 1 - share
        cash += value - spent
        costs += spent
        orders += 1
        traded += value

    for t in range(n):
        price = open_[t]
        total = cash + shares * price
        change = weight[t] * total - shares * price
        if abs(change) >= MIN_CHANGE * total or (weight[t] == 0 and shares > 0):
            if change > 0:
                spent = change * cost + fee
                value = min(change, cash - spent)
                if value > 0:
                    shares += value / price
                    basis += value + spent
                    cash -= value + spent
                    costs += spent
                    orders += 1
                    traded += value
            elif shares > 0:
                sell(min(-change, shares * price), price)
        nav[t], held[t] = cash + shares * close[t], shares * close[t]
        interest = max(cash, 0.0) * rate[t] / DAYS_PER_YEAR
        cash += interest
        gain += interest
        if t + 1 < n and years[t + 1] != years[t]:
            taxable = gain + carry
            gain, carry = 0.0, min(taxable, 0.0)
            due = max(taxable, 0.0) * tax
            tax_paid += due
            if due > cash:  # Die Steuer muss aus dem Depot bezahlt werden; der Verkauf zaehlt im neuen Jahr
                sell(min(due - cash + 2 * fee, shares * close[t]), close[t])
            cash -= due
    if shares > 0:
        sell(shares * close[-1], close[-1])
    due = max(gain + carry, 0.0) * tax
    tax_paid += due
    return Run(nav, cash - due, float((held / np.maximum(nav, 1e-9)).mean()), orders, traded / nav.mean() / (n / DAYS_PER_YEAR), tax_paid, costs)


def to_execution(decision):
    """Entscheidung zum Handelsschluss von t wird Gewicht zur Eroeffnung von t+1. Der erste Tag des Fensters nutzt die Entscheidung davor."""
    return np.r_[0.0, decision[:-1]]


def staggered(signal, days):
    """Gestaffelt: Jeder Tag legt einen eigenen Anteil an, der h Tage bleibt. So haengt nichts vom Starttag ab."""
    return pd.Series(signal, dtype=float).rolling(days, min_periods=1).mean().to_numpy()


def cash_return(rate):
    """Log-Rendite von Cash von Schluss zu Schluss. Der Zins von Tag t landet im Depotwert von Tag t+1."""
    return np.log1p(rate[:-1] / DAYS_PER_YEAR)


def stats(gross, net, rate):
    """Alles vor Steuern aus gross; nur Endwert und Steuer aus net, dem Lauf mit Steuerzahlungen."""
    ret = np.diff(np.log(gross.nav))
    excess = ret - cash_return(rate)
    peak = np.maximum.accumulate(gross.nav)
    years = len(gross.nav) / DAYS_PER_YEAR
    return {"rendite": float((gross.final_after_tax / CAPITAL) ** (1 / years) - 1), "nach_steuer": float((net.final_after_tax / CAPITAL) ** (1 / years) - 1), "schwankung": float(ret.std() * np.sqrt(DAYS_PER_YEAR)),
            "sharpe": float(excess.mean() / max(excess.std(), 1e-9) * np.sqrt(DAYS_PER_YEAR)), "drawdown": float((gross.nav / peak - 1).min()), "investiert": gross.exposure, "orders": gross.orders,
            "umschlag": float(gross.turnover), "kosten": float(gross.costs), "steuer": float(net.tax_paid), "endwert": float(net.final_after_tax)}


def boot_indices(n, seed=0, draws=N_BOOT, block=BLOCK):
    """Kreisfoermiger Block-Bootstrap: Schwankungs-Cluster und Gedaechtnis bleiben in den Bloecken erhalten."""
    rng = np.random.default_rng(seed)
    blocks = int(np.ceil(n / block))
    starts = rng.integers(0, n, size=(draws, blocks))
    return ((starts[:, :, None] + np.arange(block)) % n).reshape(draws, -1)[:, :n]


def compare(ret, ref, cash, idx):
    """Rendite- und Sharpe-Differenz gegen die Referenz, je mit Intervall und einseitigem p-Wert."""
    def sharpe(values):
        excess = values - cash[idx]
        return excess.mean(1) / np.maximum(excess.std(1), 1e-9) * np.sqrt(DAYS_PER_YEAR)

    gap = (ret - ref)
    boot_return = gap[idx].mean(1) * DAYS_PER_YEAR
    boot_sharpe = sharpe(ret[idx]) - sharpe(ref[idx])
    plain = lambda v: (v - cash).mean() / max((v - cash).std(), 1e-9) * np.sqrt(DAYS_PER_YEAR)
    out = {}
    for name, point, boot in (("rendite", gap.mean() * DAYS_PER_YEAR, boot_return), ("sharpe", plain(ret) - plain(ref), boot_sharpe)):
        low, high = np.quantile(boot, [0.025, 0.975])
        out |= {f"{name}_diff": float(point), f"{name}_low": float(low), f"{name}_high": float(high), f"{name}_p": float(((boot <= 0).sum() + 1) / (len(boot) + 1))}
    return out


# ---------------------------------------------------------------------------
# Signale
# ---------------------------------------------------------------------------

def price_decisions(close):
    """Kursregeln: nur Schlusskurse bis zum jeweiligen Tag."""
    series = pd.Series(close)
    trend = (series > series.rolling(200).mean()).to_numpy(dtype=float)
    momentum = (series.shift(21) > series.shift(252)).to_numpy(dtype=float)
    return trend, momentum


def vol_decision(q10, q90):
    """Gewicht aus der Schwankungsprognose. Der Vergleichswert ist nur der Median der bisherigen Prognosen."""
    sigma = (q90 - q10) / 2.563
    target = pd.Series(sigma).expanding(min_periods=60).median().shift(1).to_numpy()
    return np.where(np.isfinite(target), np.minimum(target / sigma, 1.0), 1.0)


def on_calendar(days, source_days, values, fill=0.0):
    """Werte je Tag aus einer Quelle auf den Handelskalender. Fehlt ein Tag, gilt fill."""
    out = np.full(len(days), fill, dtype=float)
    position = np.searchsorted(source_days, days)
    position_ok = position < len(source_days)
    found = np.zeros(len(days), dtype=bool)
    found[position_ok] = source_days[position[position_ok]] == days[position_ok]
    out[found] = values[position[found]]
    return out


def load_market(con, symbol, start):
    """Tagesdaten von Aktie, SPY und Zins auf dem Kalender der Aktie, ab dem ersten Tag nach start."""
    if load(con, RATE_SYMBOL, "1D").empty:
        ingest.ingest_daily(RATE_SYMBOL, con)
    frame = load(con, symbol, "1D")
    days = naive_seconds(frame.index) // 86400
    spy, rate = load(con, "SPY", "1D"), load(con, RATE_SYMBOL, "1D")
    rate_days = naive_seconds(rate.index) // 86400
    position = np.clip(np.searchsorted(rate_days, days, side="right") - 1, 0, len(rate) - 1)  # Der letzte bekannte Zins
    spy_days = naive_seconds(spy.index) // 86400
    return {"days": days, "open": frame.open.to_numpy(dtype=float), "close": frame.close.to_numpy(dtype=float), "rate": rate.close.to_numpy(dtype=float)[position] / 100,
            "spy_open": on_calendar(days, spy_days, spy.open.to_numpy(dtype=float), np.nan), "spy_close": on_calendar(days, spy_days, spy.close.to_numpy(dtype=float), np.nan),
            "years": frame.index.tz_convert(ingest.NY).year.to_numpy(), "first": int(np.searchsorted(days, start, side="right"))}


def decisions(con, symbol, market, config):
    """Alle zehn Strategien als Entscheidung je Handelstag, auf dem vollen Kalender."""
    target = matrix.load_ticker(con, symbol)
    final_folds, _ = train.holdout_folds(target)
    with np.load(OOS / f"{symbol}_mc.npz") as data:
        mc_past = {key: data[key] for key in data.files}
    with np.load(OOS / f"{symbol}_mc_final.npz") as data:
        mc_final = {key: data[key] for key in data.files}
    everything, stack, active, mc_only, _ = matrix.stack_history(con, symbol, config, final_folds, mc_past, mc_final)
    days, close = market["days"], market["close"]
    out, tolerance = {}, 1e-6  # Liegt ein Modell genau auf der Basisrate, ist das kein Signal
    for p, label in ((stack, "Stack"), (mc_only, "Monte Carlo")):
        for horizon, step in SIDES.items():
            h = HORIZON_NAMES.index(horizon)
            signal = ((p[:, h] - everything.base_up[:, h]) > tolerance).astype(float)
            out[f"{label} {horizon}"] = staggered(on_calendar(days, everything.date, signal), step)
    pattern = matrix.pattern_signal(con, symbol, days)
    out["Muster 7T"] = staggered((pattern > 0).astype(float), SIDES["7T"])
    trend, momentum = price_decisions(close)
    out["200-Tage-Linie"] = trend
    out["Momentum 12-1"] = staggered(momentum, SIDES["1M"])
    mc = matrix.merged_mc(symbol)
    fhs = list(mc["engines"]).index("FHS")
    i10, i90 = risk.LEVELS.index(0.1), risk.LEVELS.index(0.9)
    out["Volatilitaet"] = on_calendar(days, mc["dates"], vol_decision(mc["q"][:, fhs, 0, i10].astype(float), mc["q"][:, fhs, 0, i90].astype(float)), 1.0)
    if len(out) != STRATEGIES:
        raise ValueError("Die Strategien sind vorab festgelegt")
    start = int(everything.date[active].min())
    return out, start


def evaluate(market, weights, holdout):
    """Alle Strategien auf dem Fenster ab market['first']. Die Referenzen und Teilzeitraeume sind fuer alle gleich."""
    f = market["first"]
    open_, close, rate, years = market["open"][f:], market["close"][f:], market["rate"][f:], market["years"][f:]
    run = lambda w, o=open_, c=close, cost=COST, tax=0.0: simulate(o, c, w, rate, years, cost=cost, tax=tax)
    row = lambda w, o=open_, c=close: {**stats(run(w, o, c), run(w, o, c, tax=TAX), rate), "stress": stats(run(w, o, c, cost=STRESS_COST), run(w, o, c, cost=STRESS_COST, tax=TAX), rate)["rendite"]}
    always = np.ones(len(close))
    ret_hold = np.diff(np.log(run(always).nav))
    cash = cash_return(rate)
    idx = boot_indices(len(ret_hold))
    is_holdout = market["days"][f:][1:] >= holdout
    rows = [{"strategie": "Halten Aktie", **row(always)}, {"strategie": "Halten SPY", **row(always, market["spy_open"][f:], market["spy_close"][f:])},
            {"strategie": "Cash", **row(np.zeros(len(close)))}]
    for name, decision in weights.items():
        weight = to_execution(decision[f - 1:])[1:]
        ret = np.diff(np.log(run(weight).nav))
        rows.append({"strategie": name, **row(weight), **compare(ret, ret_hold, cash, idx),
                     "diff_wf": float((ret - ret_hold)[~is_holdout].mean() * DAYS_PER_YEAR), "diff_holdout": float((ret - ret_hold)[is_holdout].mean() * DAYS_PER_YEAR),
                     "sharpe_wf": sharpe_gap(ret, ret_hold, cash, ~is_holdout), "sharpe_holdout": sharpe_gap(ret, ret_hold, cash, is_holdout)})
    return pd.DataFrame(rows), (market["days"][f], market["days"][-1])


def sharpe_gap(ret, ref, cash, mask):
    value = lambda v: (v[mask] - cash[mask]).mean() / max((v[mask] - cash[mask]).std(), 1e-9) * np.sqrt(DAYS_PER_YEAR)
    return float(value(ret) - value(ref))


def judge(frames):
    """FDR ueber alle Tests aller Ticker. Belegt nur, was auch in beiden Teilzeitraeumen positiv ist."""
    tests = [(symbol, i, name) for symbol, frame in frames.items() for i in frame.index[frame.rendite_p.notna()] for name in ("rendite", "sharpe")]
    q = fdr_q([frames[symbol].loc[i, f"{name}_p"] for symbol, i, name in tests])
    for frame in frames.values():
        for name in ("rendite", "sharpe"):
            frame[f"{name}_q"], frame[f"{name}_belegt"] = np.nan, 0
    parts = {"rendite": ("diff_wf", "diff_holdout"), "sharpe": ("sharpe_wf", "sharpe_holdout")}
    for (symbol, i, name), value in zip(tests, q):
        frame = frames[symbol]
        frame.loc[i, f"{name}_q"] = value
        frame.loc[i, f"{name}_belegt"] = int(value < 0.05 and all(frame.loc[i, part] > 0 for part in parts[name]))
    return frames, len(tests)


# ---------------------------------------------------------------------------
# Bericht
# ---------------------------------------------------------------------------

def _p(x, signed=False):
    return "–" if pd.isna(x) else f"{100 * x:{'+' if signed else ''}.1f} %"


def write_report(symbol, frame, window, n_tests):
    start, end = (pd.Timestamp(int(d), unit="D").date() for d in window)
    lines = [f"# {symbol}: Phase-7-Report", "", f"Stand {datetime.now():%Y-%m-%d %H:%M}. Statistische Auswertung der Kursgeschichte, keine Anlageberatung. Es wurden keine Orders gesendet.", "",
             f"Zeitraum {start} bis {end}. Signal zum Handelsschluss, Ausführung zur nächsten Eröffnung, nur Long. Start {CAPITAL:,.0f} $, Kosten {COST * 1e4:.0f} Basispunkte je Seite plus {ORDER_FEE:.0f} $ je Order, Cash verzinst mit {RATE_SYMBOL}. Steuer {100 * TAX:.3f} % auf realisierte Gewinne je Jahr mit Verlustvortrag, Depot am Ende verkauft. Alle Regeln standen vor dem ersten Lauf fest (GAMEPLAN, Phase 7).", "",
             "## Ergebnis", "", "| Strategie | Rendite p. a. | Nach Steuer p. a. | Endwert nach Steuer | Sharpe | Schwankung | Max. Einbruch | Investiert | Orders | Kosten $ | Steuer $ | Mit 20 Bp. |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for r in frame.to_dict("records"):
        lines.append(f"| {r['strategie']} | {_p(r['rendite'], True)} | {_p(r['nach_steuer'], True)} | {r['endwert']:,.0f} $ | {r['sharpe']:.2f} | {_p(r['schwankung'])} | {_p(r['drawdown'])} | {_p(r['investiert'])} | {r['orders']} | {r['kosten']:,.0f} | {r['steuer']:,.0f} | {_p(r.get('stress'), True)} |")
    lines += ["", "## Besser als Halten der Aktie?", "", f"Vor Steuern, nach Kosten. Block-Bootstrap über {BLOCK} Tage, {N_BOOT:,} Läufe, in Klammern das 95 %-Intervall. q ist korrigiert über alle {n_tests} Tests beider Ticker. Belegt heißt q < 0,05 und positiv in Walk-Forward und Abschlussprüfung.", "",
              "| Strategie | Rendite-Differenz p. a. | Walk-Forward | Abschluss | q | Belegt | Sharpe-Differenz | Walk-Forward | Abschluss | q | Belegt |", "|---|---:|---:|---:|---:|---|---:|---:|---:|---:|---|"]
    for r in frame[frame.rendite_p.notna()].to_dict("records"):
        lines.append(f"| {r['strategie']} | {_p(r['rendite_diff'], True)} ({_p(r['rendite_low'], True)} bis {_p(r['rendite_high'], True)}) | {_p(r['diff_wf'], True)} | {_p(r['diff_holdout'], True)} | {r['rendite_q']:.3f} | {'ja' if r['rendite_belegt'] else 'nein'} | {r['sharpe_diff']:+.2f} ({r['sharpe_low']:+.2f} bis {r['sharpe_high']:+.2f}) | {r['sharpe_wf']:+.2f} | {r['sharpe_holdout']:+.2f} | {r['sharpe_q']:.3f} | {'ja' if r['sharpe_belegt'] else 'nein'} |")
    won = frame[(frame.rendite_belegt == 1) | (frame.sharpe_belegt == 1)]
    lines += ["", "## Was das heißt", "", f"Belegt besser als Halten: {', '.join(won.strategie) if len(won) else 'keine Strategie'}.", "",
              f"**Grenzen:** {symbol} wurde ausgewählt, als der Kursverlauf schon bekannt war, Halten ist hier also eine hohe Latte und Halten von SPY die fairere Referenz. Beträge in Dollar ohne Wechselkurs. Dividenden stecken als bereinigte Kurse in der Rendite und werden erst beim Verkauf besteuert. Kosten sind eine Annahme, nicht gemessen.", ""]
    path = REPORTS / f"{symbol}_phase7.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def run(symbols, con=None, log=None):
    """Immer alle Ticker zusammen: Die Korrektur fuer viele Tests gilt ueber alle."""
    log = log or (lambda text: print(text, flush=True))
    con = con or connect()
    frames, windows = {}, {}
    for symbol in symbols:
        config = json.loads((CONFIG / f"matrix_{symbol}.json").read_text(encoding="utf-8"))
        market = load_market(con, symbol, 0)
        weights, start = decisions(con, symbol, market, config)
        market["first"] = int(np.searchsorted(market["days"], start, side="right"))
        frames[symbol], windows[symbol] = evaluate(market, weights, config["holdout"])
        log(f"{symbol}: {len(weights)} Strategien gerechnet")
    frames, n_tests = judge(frames)
    for symbol, frame in frames.items():
        replace_rows(con, "backtest", symbol, frame)
        log(f"{symbol}: {write_report(symbol, frame, windows[symbol], n_tests)}")
    return frames
