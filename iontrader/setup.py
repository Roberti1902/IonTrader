"""Phase 5: Setup- und Thesen-Report. Welche Indikatoren und Thesen helfen bei genau diesem Ticker wirklich?"""
import time
from concurrent.futures import ThreadPoolExecutor

import ioncore
import numpy as np
import pandas as pd

from .features import load_features
from .ingest import TIMEFRAMES
from .store import connect, load, replace_rows
from .study import FDR, HORIZONS, fdr_q, forward_returns

IC_SHIFTS = 5000
MIN_BARS = 500
SOLID_HORIZONS = ("1T", "7T", "1M")  # Nur hier gibt es genug unabhaengige Zeitraeume fuer eine belastbare Aussage


def _standardize(x):
    x = x - x.mean()
    spread = x.std()
    return x / spread if spread > 0 else None


def feature_ic(symbol, con=None, n_shift=IC_SHIFTS, log=None):
    """Rangkorrelation jedes Indikators mit der Rendite (Richtung) und ihrem Betrag (Schwankung), je Timeframe und Horizont."""
    log = log or (lambda text: print(text, flush=True))
    con = con or connect()
    rows, seed = [], 1
    tic, cpu = time.perf_counter(), time.process_time()
    threads = ioncore.threads()
    with ThreadPoolExecutor(threads) as pool:
        for tf in TIMEFRAMES:
            bars = load(con, symbol, tf)
            if len(bars) < MIN_BARS:
                continue
            f = load_features(symbol, tf)
            fwd, _ = forward_returns(con, symbol, tf, bars.index)
            names = list(f.columns)
            ranks = dict(zip(names, pool.map(lambda c: f[c].rank().to_numpy(dtype=float), names)))
            tests = 0
            for hz in HORIZONS:
                y = pd.Series(fwd[hz])
                for target, values in (("Richtung", y), ("Schwankung", y.abs())):
                    y_rank = values.rank().to_numpy(dtype=float)
                    for name in names:
                        valid = np.isfinite(ranks[name]) & np.isfinite(y_rank)
                        if valid.sum() < MIN_BARS:
                            continue
                        a, b = _standardize(ranks[name][valid]), _standardize(y_rank[valid])
                        if a is None or b is None:
                            continue
                        seed += 1
                        ic, p = ioncore.ic_test(a, b, n_shift, seed)
                        rows.append({"timeframe": tf, "indikator": name, "horizont": hz, "ziel": target, "n": int(valid.sum()), "ic": ic, "p": p})
                        tests += 1
            log(f"  {tf}: {len(bars):,} Bars, {tests:,} Tests, {time.perf_counter() - tic:.0f} s")
    table = pd.DataFrame(rows)
    table["q"] = fdr_q(table.p)
    replace_rows(con, "feature_ic", symbol, table)
    wall, used = time.perf_counter() - tic, time.process_time() - cpu
    log(f"Indikator-Tests: {len(table):,} mit je {n_shift:,} Verschiebungen, {wall:.0f} s, CPU-Auslastung {used / max(wall, 1e-9) / threads:.0%}")
    return table, wall, used / max(wall, 1e-9) / threads


def _rows(con, table, symbol):
    if not con.execute("SELECT 1 FROM sqlite_master WHERE name=?", (table,)).fetchone():
        return pd.DataFrame()
    return pd.read_sql_query(f"SELECT * FROM {table} WHERE symbol=?", con, params=(symbol,))


def theses(symbol, con=None):
    """Jede These aus deinen Notizen mit dem Messwert dieses Tickers. Liefert Zeilen (These, Messung, Urteil)."""
    con = con or connect()
    out = []
    control, study, fractal, regime, mean_rev, models, var = (
        _rows(con, t, symbol) for t in ("pattern_control", "study", "fractal", "regime", "mean_reversion", "model_scores", "var_backtest"))
    if len(control):
        hits = int((control.q < FDR).sum())
        out.append(("20 Chartmuster sagen die Richtung voraus", f"{hits} von {len(control)} Kombinationen schlagen zufällige Einstiege", "gestützt" if hits else "nicht gestützt"))
    for family, title in (("FIB", "Fibonacci-Niveaus wirken"), ("MR", "Mean-Reversion-Signale wirken"), ("MOM", "Momentum-Signale wirken")):
        part = study[study.familie == family] if len(study) else study
        if len(part):
            good = part[(part.q < FDR) & part.passt]
            out.append((title, f"{len(good)} von {len(part)} Tests in erwarteter Richtung nach FDR; ohne Korrektur p<5 %: {int((part.p < 0.05).sum())} (Zufall: rund {0.05 * len(part):.0f})",
                        "gestützt" if len(good) else "nicht gestützt"))
    if len(fractal):
        outside = lambda col: int((~fractal[col].between(0.809, 1.862)).sum())
        out.append(("Märkte haben Gedächtnis: Richtung", f"H {fractal.H.min():.2f} bis {fractal.H.max():.2f}; Lo-Test auf {outside('lo')} von {len(fractal)} Timeframes signifikant",
                    "gestützt" if outside("lo") > len(fractal) / 2 else "nicht gestützt"))
        out.append(("Märkte haben Gedächtnis: Schwankung", f"H {fractal.H_abs.min():.2f} bis {fractal.H_abs.max():.2f}; Lo-Test auf {outside('lo_abs')} von {len(fractal)} Timeframes signifikant",
                    "gestützt" if outside("lo_abs") > len(fractal) / 2 else "nicht gestützt"))
    if len(regime):
        good = ((regime.familie == "MR") & (regime.t_diff > 2)) | ((regime.familie == "MOM") & (regime.t_diff < -2))
        out.append(("Hurst schaltet zwischen Mean Reversion und Momentum", f"{int(good.sum())} von {len(regime)} Vergleichen stützen das", "gestützt" if good.mean() > 0.2 else "nicht gestützt"))
    if len(mean_rev):
        out.append(("Mean Reversion ist häufig", f"Kurs in {100 * mean_rev.stationaer.min():.0f} bis {100 * mean_rev.stationaer.max():.0f} % der Fenster stationär (Zufall: rund 5 %)",
                    "gestützt" if mean_rev.stationaer.median() > 0.10 else "nicht gestützt"))
    if len(models):
        known = models[models.n > 0]
        solid = known[known.brier_low > 1e-6]
        out.append(("LSTM, GRU, Transformer und TFT sagen die Richtung voraus", f"{len(solid)} von {len(known)} Modell-Horizont-Kombinationen liegen mit dem Intervall über der Basisrate", "gestützt" if len(solid) else "nicht gestützt"))
    if len(var):
        tested = var[(var.kennzahl != "Spanne 80") & (var.testbar == 1)]
        fhs = tested[tested.verfahren == "FHS"]
        out.append(("Monte Carlo erfasst das Risiko", f"FHS besteht {int(fhs.bestanden.sum())} von {len(fhs)} testbaren VaR-Backtests", "gestützt" if len(fhs) and fhs.bestanden.all() else "teilweise"))
    return out


def setup_lines(symbol, con=None, top=12):
    """Berichtsteil: Welche Indikatoren tragen, getrennt nach Richtung und Schwankung."""
    con = con or connect()
    table = _rows(con, "feature_ic", symbol)
    if table.empty:
        return []
    lines = ["## Setup: Welche Indikatoren helfen bei diesem Ticker?", "",
             f"{len(table):,} Tests: jeder Indikator gegen die spätere Rendite (Richtung) und ihren Betrag (Schwankung), je Timeframe und Horizont, "
             f"mit je {IC_SHIFTS:,} Verschiebungen. IC ist die Rangkorrelation, q die Fehlerquote nach Korrektur für viele Tests.", ""]
    for target in ("Richtung", "Schwankung"):
        part = table[table.ziel == target]
        solid = part[part.horizont.isin(SOLID_HORIZONS)]
        hits = solid[solid.q < FDR]
        thin = part[~part.horizont.isin(SOLID_HORIZONS)]
        lines += [f"### {target}: {len(hits):,} von {len(solid):,} Tests signifikant bei 1 Tag, 7 Tagen und 1 Monat", "",
                  f"Bei 6 Monaten und 1 Jahr zusätzlich {int((thin.q < FDR).sum())} von {len(thin):,}; das stützt sich aber nur auf wenige unabhängige Zeiträume und zählt hier nicht.", ""]
        if len(hits):
            lines += ["| Indikator | Timeframe | Horizont | IC | q |", "|---|---|---|---:|---:|"]
            for r in hits.assign(stark=hits.ic.abs()).sort_values("stark", ascending=False).head(top).to_dict("records"):
                lines.append(f"| {r['indikator']} | {r['timeframe']} | {r['horizont']} | {r['ic']:+.3f} | {r['q']:.4f} |")
            lines.append("")
            per = hits.assign(stark=hits.ic.abs()).groupby("indikator").stark.agg(["size", "mean"]).sort_values("size", ascending=False).head(top)
            lines += ["Am häufigsten signifikant:", "", "| Indikator | Treffer | Ø |IC| |", "|---|---:|---:|"]
            lines += [f"| {name} | {int(r['size'])} | {r['mean']:.3f} |" for name, r in per.iterrows()]
            lines.append("")
        else:
            lines += ["Kein Indikator übersteht die Korrektur.", ""]
    lines += ["Die Ränge zeigen einen Zusammenhang über die gesamte Historie, keine Handelsregel.", ""]
    return lines
