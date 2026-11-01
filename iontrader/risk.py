"""Phase 4: Risiko-Saeule. Monte Carlo auf der GPU, Stresstests und VaR-Backtest."""
import math
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime

import ioncore
import numpy as np
import pandas as pd
import torch
import yfinance as yf

from . import ROOT, features, ingest
from .dataset import HOLDOUT_DAYS, HORIZON_DAYS
from .graph import MARKET, PROXY, build, daily_returns, factor_table, graph_tickers, neighbors, reachable
from .store import connect, load, replace_rows
from .study import HORIZONS, naive_seconds
from .train import OOS, block_ci

REPORTS = ROOT / "reports"
HORIZON_NAMES = list(HORIZONS)
HORIZON_STEPS = list(HORIZONS.values())
LEVELS = (0.01, 0.05, 0.1, 0.5, 0.9, 0.95, 0.99)
BACKTEST_PATHS = 50_000
BLOCK_LENGTH = 21  # rund ein Handelsmonat, damit Abhaengigkeiten innerhalb des Blocks erhalten bleiben
EARNINGS_EVERY = 63  # Handelstage zwischen zwei Quartalszahlen, wenn der Termin noch nicht bekannt ist
ANNOUNCE_DAYS = 14  # Erst so viele Kalendertage vorher gilt der Termin als bekannt; davor zaehlt der Quartalsrhythmus
BACKTEST_START = "2016-01-01"
VAR_LEVELS = {0.05: "VaR 95", 0.01: "VaR 99"}


# ---------------------------------------------------------------------------
# Daten: Ticker, Markt, Sektor und Earnings auf einem gemeinsamen Handelskalender
# ---------------------------------------------------------------------------

@dataclass
class Panel:
    symbol: str
    dates: np.ndarray  # Tage als Zahl
    r: np.ndarray  # Log-Renditen des Tickers
    market: np.ndarray
    sector: dict  # Sektor-ID -> Log-Renditen; vor dem Start eines ETF steht dort der Stellvertreter
    earn: np.ndarray  # True an Tagen, an denen der Kurs auf Quartalszahlen reagiert
    earnings_days: np.ndarray  # Reaktionstage als Zahl, auch zukuenftige
    factors: pd.DataFrame  # Graph: je Stichtag b_m, sector, b_s, b_sm


def fetch_earnings(con, symbol):
    """Earnings-Termine von Yahoo, zwischengespeichert. Ohne Verbindung gilt der letzte bekannte Stand."""
    try:
        frame = yf.Ticker(symbol).get_earnings_dates(limit=100)
        if frame is not None and len(frame):
            local = frame.index.tz_convert("America/New_York").tz_localize(None)
            replace_rows(con, "earnings", symbol, pd.DataFrame({"seconds": local.as_unit("s").asi8}))
    except Exception:  # Fehlende Termine verringern die Genauigkeit, stoppen aber nicht den Lauf
        pass
    exists = con.execute("SELECT 1 FROM sqlite_master WHERE name='earnings'").fetchone()
    if not exists:
        return np.array([], dtype=np.int64)
    return pd.read_sql_query("SELECT seconds FROM earnings WHERE symbol=? ORDER BY seconds", con, params=(symbol,)).seconds.to_numpy()


def reaction_days(seconds, dates):
    """Tag, an dem der Kurs reagiert: Vor der Eroeffnung noch am selben Tag, sonst am naechsten Handelstag."""
    out = []
    for s in seconds:
        day, hour = int(s // 86400), (s % 86400) / 3600
        if hour >= 9:
            i = np.searchsorted(dates, day, side="right")
            out.append(int(dates[i]) if i < len(dates) else int(np.busday_offset(np.datetime64(day, "D"), 1, roll="forward").astype(int)))
        else:
            i = np.searchsorted(dates, day)
            out.append(int(dates[i]) if i < len(dates) else day)
    return np.unique(np.array(out, dtype=np.int64)) if out else np.array([], dtype=np.int64)


def load_panel(con, symbol):
    factors = factor_table(con, symbol)
    if factors.empty:
        raise SystemExit(f"{symbol}: keine Betas im Graphen, bitte zuerst den Graphen bauen")
    sectors = sorted(set(factors.sector))
    returns = daily_returns(con, [symbol, MARKET, PROXY, *sectors])
    returns = returns[returns[[symbol, MARKET, PROXY]].notna().all(axis=1)]
    dates = returns.index.to_numpy(dtype=np.int64)
    proxy = returns[PROXY].to_numpy(dtype=float)
    sector = {s: np.where(np.isfinite(returns[s].to_numpy(dtype=float)), returns[s].to_numpy(dtype=float), proxy) for s in sectors}
    days = reaction_days(fetch_earnings(con, symbol), dates)
    return Panel(symbol, dates, returns[symbol].to_numpy(dtype=float), returns[MARKET].to_numpy(dtype=float), sector,
                 np.isin(dates, days), days, factors)


# ---------------------------------------------------------------------------
# Zustand: GARCH je Faktor, gefilterte Schocks und Sprung-Pool, nur aus Daten bis zum Stichtag
# ---------------------------------------------------------------------------

@dataclass
class State:
    mu: float
    load: np.ndarray  # (3,) Gewicht von Markt, Sektor, Eigenanteil
    omega: np.ndarray
    alpha: np.ndarray
    gamma: np.ndarray
    beta: np.ndarray
    next_var: np.ndarray
    peak_var: np.ndarray
    z: np.ndarray  # (Tage, 3) gemeinsam nach Datum gezogen, das erhaelt die Korrelation der Faktoren
    jumps: np.ndarray  # Eigenanteil an Earnings-Tagen
    raw: np.ndarray  # alle Renditen des Tickers fuer den Block-Bootstrap
    earnings_steps: list


def earnings_steps(panel, t):
    """Schritte im Pfad mit Earnings: naechster Termin, wenn angekuendigt, sonst ueber den Quartalsrhythmus geschaetzt."""
    day = panel.dates[t]
    upcoming = panel.earnings_days[panel.earnings_days > day]
    if len(upcoming) and upcoming[0] - day <= ANNOUNCE_DAYS:
        first = int(np.busday_count(np.datetime64(int(day), "D"), np.datetime64(int(upcoming[0]), "D"))) - 1
    else:
        past = np.flatnonzero(panel.earn[:t + 1])
        if not len(past):
            return []
        first = (int(past[-1]) + EARNINGS_EVERY - t - 1) % EARNINGS_EVERY
    return list(range(max(first, 0), HORIZON_STEPS[-1], EARNINGS_EVERY))


def prepare(panel, t, jumps=True):
    """Alles, was die Simulation zum Handelsschluss von Tag t braucht. Nichts davon liegt nach t."""
    row = panel.factors[panel.factors["asof"] <= panel.dates[t]].iloc[-1]
    b_m, b_s, b_sm = float(row.b_m), float(row.b_s), float(row.b_sm)
    r, m, s_raw = panel.r[:t + 1], panel.market[:t + 1], panel.sector[row.sector][:t + 1]
    s = s_raw - b_sm * m
    e = r - b_m * m - b_s * s
    earn = panel.earn[:t + 1] if jumps else np.zeros(t + 1, dtype=bool)
    fit_m, fit_s, fit_e = ioncore.gjr_fit(m), ioncore.gjr_fit(s), ioncore.gjr_fit(e[~earn])
    fits = (fit_m, fit_s, fit_e)
    field = lambda name: np.array([f[name] for f in fits], dtype=np.float32)
    z = np.c_[fit_m["z"][~earn], fit_s["z"][~earn], fit_e["z"]].astype(np.float32)
    return State(float(r[~earn].mean()), np.array([b_m, b_s, 1.0], dtype=np.float32), field("omega"), field("alpha"),
                 field("gamma"), field("beta"), field("next_var"), field("peak_var"), z,
                 (e[earn] if jumps else np.array([])).astype(np.float32), r.astype(np.float32),
                 earnings_steps(panel, t) if jumps else [])


# ---------------------------------------------------------------------------
# Monte Carlo auf der GPU
# ---------------------------------------------------------------------------

@torch.inference_mode()
def simulate_fhs(state, n_paths, n_steps=HORIZON_STEPS[-1], seed=1, device="cuda", start_var=None):
    """Filtered Historical Simulation: GJR-Schwankung plus echte, gemeinsam gezogene Schocks. Liefert Log-Renditen."""
    gen = torch.Generator(device).manual_seed(seed)
    tensor = lambda a: torch.as_tensor(np.asarray(a), dtype=torch.float32, device=device)
    z, load_, omega, alpha, gamma, beta = (tensor(a) for a in (state.z, state.load, state.omega, state.alpha, state.gamma, state.beta))
    sig2 = tensor(state.next_var if start_var is None else start_var).expand(n_paths, 3).clone()
    jumps = tensor(state.jumps)
    earnings = set(state.earnings_steps) if len(jumps) else set()
    out = torch.empty(n_paths, n_steps, device=device)
    for step in range(n_steps):
        draws = z[torch.randint(0, len(z), (n_paths,), generator=gen, device=device)]
        shock = draws * sig2.sqrt()
        out[:, step] = state.mu + (shock * load_).sum(1)
        if step in earnings:  # Am Earnings-Tag ersetzt der Sprung den normalen Eigenanteil
            out[:, step] += jumps[torch.randint(0, len(jumps), (n_paths,), generator=gen, device=device)] - shock[:, 2]
        sig2 = omega + (alpha + gamma * (shock < 0)) * shock ** 2 + beta * sig2
    return out


@torch.inference_mode()
def simulate_block(state, n_paths, n_steps=HORIZON_STEPS[-1], seed=1, device="cuda", length=BLOCK_LENGTH):
    """Block-Bootstrap: zieht zusammenhaengende Stuecke der echten Kursreihe und erhaelt so ihr Gedaechtnis."""
    gen = torch.Generator(device).manual_seed(seed)
    raw = torch.as_tensor(state.raw, dtype=torch.float32, device=device)
    length = min(length, len(raw))
    offsets = torch.arange(length, device=device)
    parts = []
    for _ in range(math.ceil(n_steps / length)):
        starts = torch.randint(0, len(raw) - length + 1, (n_paths,), generator=gen, device=device)
        parts.append(raw[starts[:, None] + offsets])
    return torch.cat(parts, dim=1)[:, :n_steps]


def _sorted_quantiles(sorted_x, levels):
    n = sorted_x.shape[0]
    return sorted_x[[min(n - 1, int(p * n)) for p in levels]]


@torch.inference_mode()
def distribution(paths, steps=HORIZON_STEPS):
    """Verteilung je Horizont in einfachen Renditen: Quantile, Expected Shortfall, P(steigt), Drawdown, Median der Gewinne und der Verluste."""
    n = paths.shape[0]
    # Schritt fuer Schritt statt ueber ganze Pfad-Matrizen: Das Dashboard rechnet neben einem Training auf derselben GPU
    cum, peak, drawdown = (torch.zeros(n, device=paths.device, dtype=paths.dtype) for _ in range(3))
    wanted = set(steps)
    q, es, p_up, dd, mid_up, mid_down = [], [], [], [], [], []
    for step in range(1, max(steps) + 1):
        cum += paths[:, step - 1]
        peak = torch.maximum(peak, cum)
        drawdown = torch.minimum(drawdown, cum - peak)
        if step not in wanted:
            continue
        simple = torch.expm1(cum).sort().values
        q.append(_sorted_quantiles(simple, LEVELS))
        es.append(torch.stack([simple[:max(1, int(p * n))].mean() for p in VAR_LEVELS]))
        falling = int((simple <= 0).sum())
        p_up.append((simple > 0).float().mean())
        mid_up.append(simple[min((falling + n) // 2, n - 1)])  # Median statt Mittel: Der Mittelwert hinge an wenigen extremen Pfaden
        mid_down.append(simple[falling // 2])
        dd.append(torch.expm1(_sorted_quantiles(drawdown.sort().values, (0.05, 0.5))))
    to_np = lambda items: torch.stack(items).cpu().numpy()
    return {"q": to_np(q), "es": to_np(es), "p_up": to_np(p_up), "dd": to_np(dd), "mid_up": to_np(mid_up), "mid_down": to_np(mid_down)}


@torch.inference_mode()
def p_tp_before_sl(paths, tp, sl, horizon):
    """Wahrscheinlichkeit, dass +tp vor -sl erreicht wird. Geprueft wird zum Tagesschluss."""
    # ponytail: nur Schlusskurse; Intraday-Treffer werden unterschaetzt, Brownian-Bridge-Korrektur falls das in 6.x stoert
    cum = paths[:, :horizon].cumsum(1)
    hit_tp, hit_sl = cum >= math.log1p(tp), cum <= math.log1p(-sl)
    never = horizon + 1
    first = lambda hits: torch.where(hits.any(1), hits.float().argmax(1), torch.full((len(hits),), never, device=hits.device))
    first_tp, first_sl = first(hit_tp), first(hit_sl)
    return (float((first_tp < first_sl).float().mean()), float((first_sl < first_tp).float().mean()),
            float(((first_tp == never) & (first_sl == never)).float().mean()))


# ---------------------------------------------------------------------------
# VaR-Backtest
# ---------------------------------------------------------------------------

def _xlogy(x, y):
    return x * math.log(y) if x > 0 else 0.0


def kupiec(hits, p):
    """Stimmt die Anzahl der VaR-Ueberschreitungen mit der erwarteten Quote ueberein? Liefert (LR, p-Wert)."""
    n, x = len(hits), int(np.sum(hits))
    rate = x / n
    lr = -2 * (_xlogy(x, p) + _xlogy(n - x, 1 - p) - _xlogy(x, rate) - _xlogy(n - x, 1 - rate))
    lr = max(lr, 0.0)
    return lr, math.erfc(math.sqrt(lr / 2))


def christoffersen(hits, p):
    """Kommen Ueberschreitungen gehaeuft nacheinander? Liefert (LR Unabhaengigkeit, LR gesamt, p-Wert gesamt)."""
    h = np.asarray(hits, dtype=int)
    n00 = int(((h[:-1] == 0) & (h[1:] == 0)).sum())
    n01 = int(((h[:-1] == 0) & (h[1:] == 1)).sum())
    n10 = int(((h[:-1] == 1) & (h[1:] == 0)).sum())
    n11 = int(((h[:-1] == 1) & (h[1:] == 1)).sum())
    pi01 = n01 / (n00 + n01) if n00 + n01 else 0.0
    pi11 = n11 / (n10 + n11) if n10 + n11 else 0.0
    pi = (n01 + n11) / max(1, n00 + n01 + n10 + n11)
    lr_ind = -2 * (_xlogy(n00 + n10, 1 - pi) + _xlogy(n01 + n11, pi)
                   - _xlogy(n00, 1 - pi01) - _xlogy(n01, pi01) - _xlogy(n10, 1 - pi11) - _xlogy(n11, pi11))
    lr_ind = max(lr_ind, 0.0)
    lr_uc, _ = kupiec(hits, p)
    return lr_ind, lr_uc + lr_ind, math.exp(-(lr_uc + lr_ind) / 2)


def var_tests(q_low, realized, level, step):
    """Test nur auf Stichtagen ohne Ueberlappung, sonst waeren die Treffer nicht unabhaengig."""
    known = np.flatnonzero(np.isfinite(realized))
    picks = known[::step]
    hits = realized[picks] < q_low[picks]
    n = len(picks)
    if n == 0:
        return {"n": 0}
    _, p_uc = kupiec(hits, level)
    _, _, p_cc = christoffersen(hits, level)
    return {"n": n, "erwartet": level * n, "treffer": int(hits.sum()), "quote": float(hits.mean()), "p_kupiec": p_uc, "p_christoffersen": p_cc,
            "testbar": level * n >= 5, "bestanden": p_uc >= 0.05 and p_cc >= 0.05}


def backtest(panel, start_day, end_day, n_paths=BACKTEST_PATHS, log=print, threads=None):
    """Fuer jeden Handelstag eine Prognose nur aus der Vergangenheit: GARCH neu schaetzen, dann simulieren."""
    origins = np.flatnonzero((panel.dates >= start_day) & (panel.dates < end_day))
    tic = time.perf_counter()
    cpu = time.process_time()
    threads = threads or ioncore.threads()
    with ThreadPoolExecutor(threads) as pool:
        states = list(pool.map(lambda t: prepare(panel, int(t)), origins))
    fit_wall, fit_cpu = time.perf_counter() - tic, time.process_time() - cpu
    log(f"GARCH neu geschaetzt fuer {len(origins):,} Handelstage x 3 Faktoren: {fit_wall:.1f} s, "
        f"CPU-Auslastung {fit_cpu / max(fit_wall, 1e-9) / threads:.0%}")
    h, engines = len(HORIZON_STEPS), ("FHS", "Block")
    q = np.zeros((len(origins), len(engines), h, len(LEVELS)), dtype=np.float32)
    es = np.zeros((len(origins), len(engines), h, len(VAR_LEVELS)), dtype=np.float32)
    p_up = np.zeros((len(origins), len(engines), h), dtype=np.float32)
    tic = time.perf_counter()
    for o, state in enumerate(states):
        for e, simulate in enumerate((simulate_fhs, simulate_block)):
            result = distribution(simulate(state, n_paths, seed=o + 1))
            q[o, e], es[o, e], p_up[o, e] = result["q"], result["es"], result["p_up"]
        if (o + 1) % 250 == 0:
            log(f"  {o + 1:,}/{len(origins):,} Handelstage, {(time.perf_counter() - tic) / (o + 1):.2f} s je Tag", )
    log(f"Simulation: {time.perf_counter() - tic:.0f} s fuer {len(origins):,} Tage x {n_paths:,} Pfade x {HORIZON_STEPS[-1]} Schritte x 2 Verfahren")
    realized = np.full((len(origins), h), np.nan, dtype=np.float32)
    logp = np.cumsum(panel.r)
    for j, step in enumerate(HORIZON_STEPS):
        target = origins + step
        inside = target < len(logp)
        inside[inside] = panel.dates[target[inside]] < end_day  # Nichts reicht in die unangetastete Zeit
        realized[inside, j] = np.expm1(logp[target[inside]] - logp[origins[inside]])
    return {"origins": origins, "dates": panel.dates[origins], "q": q, "es": es, "p_up": p_up, "realized": realized, "engines": np.array(engines)}


def evaluate_backtest(result):
    rows = []
    for e, engine in enumerate(result["engines"]):
        for j, name in enumerate(HORIZON_NAMES):
            for level, label in VAR_LEVELS.items():
                res = var_tests(result["q"][:, e, j, LEVELS.index(level)], result["realized"][:, j], level, HORIZON_STEPS[j])
                rows.append({"verfahren": str(engine), "horizont": name, "kennzahl": label, **res})
            # Die 80 %-Spanne, die auch das Dashboard zeigt, gilt fuer beide Seiten
            known = np.flatnonzero(np.isfinite(result["realized"][:, j]))[::HORIZON_STEPS[j]]
            realized = result["realized"][known, j]
            inside = (realized >= result["q"][known, e, j, LEVELS.index(0.1)]) & (realized <= result["q"][known, e, j, LEVELS.index(0.9)])
            rows.append({"verfahren": str(engine), "horizont": name, "kennzahl": "Spanne 80", "n": len(known),
                         "quote": float(inside.mean()) if len(known) else np.nan})
    return pd.DataFrame(rows)


def compare_with_models(symbol, result, suffix=""):
    """Monte Carlo gegen HAR und Basisrate aus Phase 3, auf denselben Tagen und denselben Zielwerten."""
    path = OOS / f"{symbol}_lstm_solo{suffix}.npz"
    if not path.exists():
        return []
    with np.load(path) as data:
        oos = {key: data[key] for key in data.files}
    day_position = {int(d): i for i, d in enumerate(result["dates"])}
    # Letzter Anker je Tag, also der Stand zum Handelsschluss wie bei Monte Carlo
    _, reverse_first = np.unique(oos["date"][::-1], return_index=True)
    last = len(oos["date"]) - 1 - reverse_first
    last = last[np.isin(oos["date"][last], result["dates"])]
    origin = np.array([day_position[int(d)] for d in oos["date"][last]])
    taus = np.array((0.1, 0.5, 0.9))
    fhs, block = list(result["engines"]).index("FHS"), list(result["engines"]).index("Block")
    level_idx = [LEVELS.index(t) for t in taus]
    rows = []
    for h, name in enumerate(HORIZON_NAMES):
        m = oos["mask"][last, h]
        if not m.any():
            continue
        y = oos["y"][last[m], h].astype(float)
        pin = lambda quant: np.maximum(taus * (y[:, None] - quant), (taus - 1) * (y[:, None] - quant)).mean(1)
        mc = np.log1p(result["q"][origin[m], fhs, h][:, level_idx].astype(float))
        har = oos["base_q"][last[m], h] * oos["scale"][last[m], h][:, None]
        fixed = oos["fixed_q"][last[m], h]
        pin_mc, pin_har, pin_fixed = pin(mc), pin(har), pin(fixed)
        pin_block = pin(np.log1p(result["q"][origin[m], block, h][:, level_idx].astype(float)))
        blocks = oos["date"][last[m]] // HORIZON_DAYS[name]  # Tage sind Kalendertage, die Bloecke also auch
        up = (y > 0).astype(float)
        p = result["p_up"][origin[m], fhs, h].astype(float)
        base = oos["base_up"][last[m], h]
        low_f, high_f = block_ci(pin_mc, pin_fixed, blocks)
        low_h, high_h = block_ci(pin_mc, pin_har, blocks)
        low_b, high_b = block_ci((p - up) ** 2, (base - up) ** 2, blocks)
        rows.append({"horizont": name, "n": int(m.sum()), "n_unabh": len(np.unique(blocks)),
                     "gegen_fest": 1 - pin_mc.sum() / pin_fixed.sum(), "fest_low": low_f, "fest_high": high_f,
                     "har_gegen_fest": 1 - pin_har.sum() / pin_fixed.sum(), "block_gegen_fest": 1 - pin_block.sum() / pin_fixed.sum(),
                     "gegen_har": 1 - pin_mc.sum() / pin_har.sum(), "har_low": low_h, "har_high": high_h,
                     "brier": 1 - ((p - up) ** 2).sum() / ((base - up) ** 2).sum(), "brier_low": low_b, "brier_high": high_b})
    return rows


# ---------------------------------------------------------------------------
# Stresstests
# ---------------------------------------------------------------------------

def worst_episodes(logp, n=5):
    """Die n schwersten Einbrueche ohne Ueberlappung als (Hoch-Index, Tief-Index, Log-Verlust)."""
    segments, episodes = [(0, len(logp))], []
    for _ in range(n):
        best = None
        for a, b in segments:
            if b - a < 2:
                continue
            part = logp[a:b]
            drawdown = part - np.maximum.accumulate(part)
            trough = int(drawdown.argmin())
            if best is None or drawdown[trough] < best[2]:
                best = (a + int(part[:trough + 1].argmax()), a + trough, float(drawdown[trough]), (a, b))
        if best is None or best[2] >= 0:
            break
        peak, trough, loss, (a, b) = best
        episodes.append((peak, trough, loss))
        segments.remove((a, b))
        segments += [(a, peak), (trough + 1, b)]
    return episodes


def market_replay(days, market, sector, b_m, b_s, b_sm, price, n=5):
    """Markt-Einbrueche ueber die heutigen Betas. Sektor-Wirkung nur, wenn es den Sektor-ETF damals schon gab."""
    day = lambda d: pd.Timestamp(int(d), unit="D").date()
    logp = np.cumsum(market)
    orth = np.cumsum(np.nan_to_num(sector - b_sm * market))
    rows = []
    for peak, trough, loss in worst_episodes(logp, n):
        with_sector = bool(np.isfinite(sector[peak + 1:trough + 1]).all())
        impact = b_m * loss + (b_s * (orth[trough] - orth[peak]) if with_sector else 0.0)
        rows.append({"art": "Markt-Einbruch über Betas", "von": day(days[peak]), "bis": day(days[trough]), "handelstage": trough - peak,
                     "markt": math.expm1(loss), "basis": "Markt + Sektor" if with_sector else "nur Markt",
                     "verlust": math.expm1(impact), "kurs": price * math.exp(impact)})
    return rows


def stress_tests(con, panel, t, price):
    """Eigene schlimmste Phasen im Replay und Markt-Einbrueche ueber die heutigen Betas aus dem Graphen."""
    day = lambda d: pd.Timestamp(int(d), unit="D").date()
    logp = np.cumsum(panel.r[:t + 1])
    rows = []
    for peak, trough, loss in worst_episodes(logp):
        rows.append({"art": "Eigene Historie", "von": day(panel.dates[peak]), "bis": day(panel.dates[trough]), "handelstage": trough - peak,
                     "basis": "echter Verlauf", "verlust": math.expm1(loss), "kurs": price * math.exp(loss)})
    row = panel.factors[panel.factors["asof"] <= panel.dates[t]].iloc[-1]
    returns = daily_returns(con, [MARKET, row.sector])
    market = returns[MARKET].dropna()
    sector = returns[row.sector].reindex(market.index).to_numpy(dtype=float)
    return rows + market_replay(market.index.to_numpy(), market.to_numpy(dtype=float), sector, row.b_m, row.b_s, row.b_sm, price)


# ---------------------------------------------------------------------------
# Gesamtlauf
# ---------------------------------------------------------------------------

def run(symbol, paths=1_000_000, big_paths=10_000_000, log=None):
    log = log or (lambda text: print(text, flush=True))
    symbol = symbol.upper()
    con = connect()
    torch.set_float32_matmul_precision("high")
    assert torch.cuda.is_available(), "CUDA nicht verfuegbar"

    tic = time.perf_counter()
    ingest.ingest_daily(symbol, con)  # Neuester Schlusskurs; die Features muessen danach wieder zu den Bars passen
    features.run(symbol, con)
    stichtage, members = build(con, graph_tickers(con, symbol))
    edge_count = con.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
    node_count = con.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
    log(f"Graph: {node_count} Knoten, {edge_count:,} Kanten, {stichtage} Stichtage, {time.perf_counter() - tic:.0f} s. {symbol} -> {members[symbol]}")

    panel = load_panel(con, symbol)
    log(f"Panel: {len(panel.dates):,} Handelstage, {int(panel.earn.sum())} Earnings-Reaktionen in der Historie, "
        f"Sektor {sorted(panel.sector)}")

    # Die letzten 2 Jahre bleiben unangetastet: Der Backtest endet davor
    last_anchor_day = int(naive_seconds(load(con, symbol, "5m").index[-1:])[0] // 86400)
    holdout = last_anchor_day - HOLDOUT_DAYS
    start_day = int(pd.Timestamp(BACKTEST_START).value // 86_400_000_000_000)
    result = backtest(panel, start_day, holdout, log=log)
    OOS.mkdir(parents=True, exist_ok=True)
    np.savez(OOS / f"{symbol}_mc.npz", **result)
    tests = evaluate_backtest(result)
    replace_rows(con, "var_backtest", symbol, tests)
    comparison = compare_with_models(symbol, result)

    # Aktuelles Risikobild mit vielen Pfaden und Laufzeitmessung
    t = len(panel.dates) - 1
    state = prepare(panel, t)
    price = float(load(con, symbol, "1D").close.iloc[-1])
    torch.cuda.reset_peak_memory_stats()
    torch.cuda.synchronize()
    tic = time.perf_counter()
    full = simulate_fhs(state, paths, seed=2026)
    torch.cuda.synchronize()
    seconds_full = time.perf_counter() - tic
    current = distribution(full)
    memory = torch.cuda.max_memory_allocated() / 2**30
    no_jumps = distribution(simulate_fhs(prepare(panel, t, jumps=False), paths, seed=2026))
    high_vol = distribution(simulate_fhs(state, paths, seed=2026, start_var=state.peak_var))
    block = distribution(simulate_block(state, paths, seed=2026))
    tp_sl = [{"tp": tp, "sl": sl, "horizont": name, **dict(zip(("p_tp", "p_sl", "p_keins"), p_tp_before_sl(full, tp, sl, HORIZONS[name])))}
             for tp, sl in ((0.05, 0.05), (0.10, 0.05), (0.20, 0.10)) for name in ("1M", "6M")]
    del full
    torch.cuda.empty_cache()
    tic = time.perf_counter()
    done = 0
    while done < big_paths:  # Zehn Millionen Pfade in Portionen, damit der Grafikspeicher reicht
        batch = simulate_fhs(state, min(paths, big_paths - done), seed=3000 + done // paths)
        torch.cuda.synchronize()
        done += len(batch)
        del batch
    seconds_big = time.perf_counter() - tic
    log(f"Monte Carlo: {paths:,} Pfade x {HORIZON_STEPS[-1]} Schritte in {seconds_full:.2f} s; {big_paths:,} Pfade in {seconds_big:.1f} s; {memory:.1f} GB")

    stress = stress_tests(con, panel, t, price)
    replace_rows(con, "risk_snapshot", symbol, pd.DataFrame(
        [{"horizont": n, "kurs": price, "var95": -current["q"][j, LEVELS.index(0.05)], "var99": -current["q"][j, LEVELS.index(0.01)],
          "cvar95": -current["es"][j, 0], "cvar99": -current["es"][j, 1], "q10": current["q"][j, LEVELS.index(0.1)],
          "q50": current["q"][j, LEVELS.index(0.5)], "q90": current["q"][j, LEVELS.index(0.9)], "p_up": current["p_up"][j],
          "dd95": -current["dd"][j, 0], "stand": int(panel.dates[t])} for j, n in enumerate(HORIZON_NAMES)]))
    path = write_report(con, symbol, panel, t, price, state, current, no_jumps, high_vol, block, tp_sl, stress, tests, comparison,
                        result, paths, big_paths, seconds_full, seconds_big, memory, members)
    bestanden = tests[(tests.kennzahl != "Spanne 80") & (tests.testbar == True)]  # noqa: E712
    log(f"Backtest: {bestanden.groupby('verfahren').bestanden.sum().to_dict()} von je {len(bestanden) // 2} testbaren Kombinationen bestanden. Report: {path}")
    return tests


def _pct(x, digits=1):
    return f"{100 * x:+.{digits}f} %"


def _skill(value, low, high):
    if pd.isna(value):
        return "–"
    if pd.isna(low):
        return f"{100 * value:+.2f} % (zu wenig Fälle)"
    mark = "**" if low > 1e-6 else ""
    return f"{mark}{100 * value:+.2f} %{mark} ({100 * low:+.1f} bis {100 * high:+.1f})"


def write_report(con, symbol, panel, t, price, state, current, no_jumps, high_vol, block, tp_sl, stress, tests, comparison, result,
                 paths, big_paths, seconds_full, seconds_big, memory, members):
    REPORTS.mkdir(exist_ok=True)
    day = lambda d: pd.Timestamp(int(d), unit="D").date()
    i95, i99, i10, i50, i90 = (LEVELS.index(p) for p in (0.05, 0.01, 0.1, 0.5, 0.9))
    lines = [f"# {symbol}: Phase-4-Report", "", f"Stand {datetime.now():%Y-%m-%d %H:%M}. Letzter Handelsschluss: {day(panel.dates[t])}, Kurs {price:.2f} $.",
             "", "Statistische Auswertung der Kursgeschichte, keine Anlageberatung.", ""]

    upcoming = panel.earnings_days[panel.earnings_days > panel.dates[t]]
    next_earn = day(upcoming[0]) if len(upcoming) else "unbekannt"
    lines += ["## 1. Aktuelles Risikobild", "",
              f"Filtered Historical Simulation mit {paths:,} Pfaden. Nächste geschätzte Earnings-Reaktion: {next_earn}.", "",
              "| Horizont | VaR 95 | VaR 99 | CVaR 95 | CVaR 99 | Spanne 10–90 % | Median | P(steigt) | Drawdown 95 % |",
              "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for j, name in enumerate(HORIZON_NAMES):
        q, es = current["q"][j], current["es"][j]
        lines.append(f"| {name} | {_pct(q[i95])} | {_pct(q[i99])} | {_pct(es[0])} | {_pct(es[1])} | {_pct(q[i10])} bis {_pct(q[i90])} | "
                     f"{_pct(q[i50])} | {current['p_up'][j]:.1%} | {_pct(current['dd'][j, 0])} |")
    lines += ["", "VaR 95 heißt: In 95 % der Pfade ist die Rendite über diesem Wert. CVaR ist der Durchschnitt der schlechtesten 5 % bzw. 1 %. "
              "Drawdown ist der größte zwischenzeitliche Rückgang bis zum Horizont.", ""]

    lines += ["## 2. Was die einzelnen Bausteine ausmachen", "",
              "VaR 99 je Variante. Rekordniveau setzt Markt, Sektor und Eigenanteil gleichzeitig auf ihre jeweils höchste bisherige "
              "Schwankung; das ist ein bewusst extremes Szenario, keine Erwartung.", "",
              "| Horizont | Basis | Ohne Earnings-Sprünge | Schwankung auf Rekordniveau | Block-Bootstrap |", "|---|---:|---:|---:|---:|"]
    for j, name in enumerate(HORIZON_NAMES):
        lines.append(f"| {name} | {_pct(current['q'][j, i99])} | {_pct(no_jumps['q'][j, i99])} | {_pct(high_vol['q'][j, i99])} | {_pct(block['q'][j, i99])} |")
    lines.append("")

    lines += ["## 3. Stresstests", "", f"Ausgangskurs {price:.2f} $. Über Betas: Markt-Einbruch umgerechnet mit den heutigen Betas aus dem Graphen, ohne Eigenanteil der Aktie. "
              "Vor dem Start des Sektor-ETF zählt nur das Marktbeta; der tatsächliche Verlust einer Aktie kann deutlich höher liegen.", "",
              "| Art | Von | Bis | Handelstage | Markt | Basis | Wirkung | Kurs |", "|---|---|---|---:|---:|---|---:|---:|"]
    for r in stress:
        market = _pct(r["markt"]) if "markt" in r else "–"
        lines.append(f"| {r['art']} | {r['von']} | {r['bis']} | {r['handelstage']:,} | {market} | {r['basis']} | {_pct(r['verlust'])} | {r['kurs']:.0f} $ |")
    lines.append("")

    lines += ["## 4. Take Profit vor Stop Loss", "", "Geprüft jeweils zum Tagesschluss, Treffer innerhalb des Tages sind nicht erfasst.", "",
              "| TP | SL | Horizont | TP zuerst | SL zuerst | Keines |", "|---:|---:|---|---:|---:|---:|"]
    for r in tp_sl:
        lines.append(f"| +{r['tp']:.0%} | -{r['sl']:.0%} | {r['horizont']} | {r['p_tp']:.1%} | {r['p_sl']:.1%} | {r['p_keins']:.1%} |")
    lines.append("")

    # Backtest
    span = f"{day(result['dates'][0])} bis {day(result['dates'][-1])}"
    lines += ["## 5. VaR-Backtest außerhalb der Trainingsdaten", "",
              f"{len(result['dates']):,} Handelstage von {span}. Für jeden Tag wurde das Modell nur mit der Vergangenheit neu geschätzt. "
              "Getestet wird auf Stichtagen ohne Überlappung. Bestanden heißt: Kupiec und Christoffersen liegen beide bei p ≥ 5 %. "
              "Die letzten 2 Jahre bleiben unangetastet.", "",
              "| Verfahren | Horizont | Kennzahl | Fälle | Erwartet | Treffer | Quote | p Kupiec | p Christoffersen | Ergebnis |",
              "|---|---|---|---:|---:|---:|---:|---:|---:|---|"]
    for r in tests[tests.kennzahl != "Spanne 80"].to_dict("records"):
        verdict = "zu wenig Fälle" if not r["testbar"] else ("bestanden" if r["bestanden"] else "**durchgefallen**")
        lines.append(f"| {r['verfahren']} | {r['horizont']} | {r['kennzahl']} | {r['n']:,} | {r['erwartet']:.1f} | {r['treffer']} | {r['quote']:.1%} | "
                     f"{r['p_kupiec']:.3f} | {r['p_christoffersen']:.3f} | {verdict} |")
    spans = tests[tests.kennzahl == "Spanne 80"].pivot(index="verfahren", columns="horizont", values="quote")[HORIZON_NAMES]
    lines += ["", "6 Monate und 1 Jahr sind damit nicht belegt: Dafür gibt es zu wenige unabhängige Zeiträume.",
              "", "Anteil der Fälle innerhalb der 80 %-Spanne (Ziel 80 %):", "", "| Verfahren | " + " | ".join(HORIZON_NAMES) + " |", "|---|" + "---:|" * len(HORIZON_NAMES)]
    for engine, row in spans.iterrows():
        lines.append(f"| {engine} | " + " | ".join(f"{v:.1%}" for v in row) + " |")
    lines.append("")

    if comparison:
        lines += ["## 6. Monte Carlo gegen die Modelle aus Phase 3", "",
                  "Dieselben Testjahre, je Tag zum Handelsschluss. MC ist hier FHS. Skill in Prozent, in Klammern das 95 %-Intervall; fett, wenn es ganz über null liegt. "
                  "Bei 6 Monaten und 1 Jahr stehen nur wenige unabhängige Zeiträume dahinter, die Intervalle sind dort trotz Fettdruck nicht belastbar.", "",
                  "| Horizont | Fälle | Unabhängig | Spanne: MC gegen fest | Block gegen fest | HAR gegen fest | Spanne: MC gegen HAR | Richtung: MC gegen Basisrate |",
                  "|---|---:|---:|---:|---:|---:|---:|---:|"]
        for r in comparison:
            lines.append(f"| {r['horizont']} | {r['n']:,} | {r['n_unabh']} | {_skill(r['gegen_fest'], r['fest_low'], r['fest_high'])} | {100 * r['block_gegen_fest']:+.2f} % | "
                         f"{100 * r['har_gegen_fest']:+.2f} % | {_skill(r['gegen_har'], r['har_low'], r['har_high'])} | {_skill(r['brier'], r['brier_low'], r['brier_high'])} |")
        lines.append("")

    lines += ["## 7. Beziehungsgraph", ""]
    row = panel.factors[panel.factors["asof"] <= panel.dates[t]].iloc[-1]
    lines += [f"Sektor von {symbol}: {members[symbol]}. Betas zum letzten Stichtag ({day(row["asof"])}): Markt {row.b_m:.2f}, Sektor über den Markt hinaus {row.b_s:.2f} (gemessen an {row.sector}). "
              "Hat der Ticker selbst großes Gewicht im Sektor-ETF, misst das Sektor-Beta teils die Aktie selbst.", "",
              f"Über den Sektor erreichbar: {', '.join(reachable(con, symbol)) or 'keine'}.", "",
              "| Stärkste Korrelation | Wert | Stärkster Vorlauf | Wert |", "|---|---:|---|---:|"]
    corr, lead = neighbors(con, symbol, "corr"), neighbors(con, symbol, "lead_lag")
    for (_, a), (_, b) in zip(corr.iterrows(), lead.iterrows()):
        lines.append(f"| {a.dst} | {a.weight:+.2f} | {b.dst} | {b.weight:+.2f} |")
    lines += ["", f"Vorlauf: Korrelation von {symbol} heute mit dem Ziel morgen. Bei 252 Tagen liegt schon ein einzelner Zufallswert in 95 % der Fälle bis ±0,12, "
              "und hier ist das Maximum aus 45 Paaren gelistet. Die Vorlauf-Werte sind deshalb kein Beleg für einen Zusammenhang.", ""]

    lines += ["## 8. Laufzeit", "", f"{paths:,} Pfade x {HORIZON_STEPS[-1]} Schritte: {seconds_full:.2f} s, {memory:.1f} GB Grafikspeicher. {big_paths:,} Pfade in Portionen: {seconds_big:.1f} s."]
    path = REPORTS / f"{symbol}_phase4.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
