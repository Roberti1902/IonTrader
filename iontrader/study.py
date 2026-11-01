"""Phase 2: Was folgte auf jedes Signal? Ereignisstudie, Fraktal- und Mean-Reversion-Report."""
import time
from datetime import datetime

import ioncore
import numpy as np
import pandas as pd
import talib

from . import ROOT
from .features import PATTERNS, load_features
from .ingest import NY, TIMEFRAMES
from .store import connect, load, replace_rows

REPORTS = ROOT / "reports"
HORIZONS = {"1T": 1, "7T": 5, "1M": 21, "6M": 126, "1J": 252}  # in Handelstagen
INTRADAY = {"1m", "5m", "15m", "1h", "4h"}
N_SHIFT = 100_000
N_CONTROL = 10_000
MIN_EVENTS = 10
FDR = 0.05


def naive_seconds(index):
    """New-York-Ortszeit als Sekunden, damit "gleiche Uhrzeit x Handelstage spaeter" ueber DST stimmt."""
    return index.tz_convert(NY).tz_localize(None).as_unit("s").asi8


def forward_returns(con, symbol, tf, index):
    """Log-Rendite von jedem Bar bis zur gleichen Uhrzeit x Handelstage spaeter. NaN, wenn die Zukunft fehlt."""
    ref = load(con, symbol, "1m") if tf in INTRADAY else pd.DataFrame()
    if ref.empty:
        ref = load(con, symbol, tf if tf in INTRADAY else "1D")
    ref_t, ref_c = naive_seconds(ref.index), np.log(ref.close.to_numpy())
    calendar = naive_seconds(load(con, symbol, "1D").index) // 86400
    t = naive_seconds(index)
    day = np.searchsorted(calendar, t // 86400)
    start = np.searchsorted(ref_t, t, side="right") - 1
    out = {}
    for name, days in HORIZONS.items():
        target_day = day + days
        known = (target_day < len(calendar)) & (start >= 0)
        target = calendar[np.minimum(target_day, len(calendar) - 1)] * 86400 + t % 86400
        ret = ref_c[np.searchsorted(ref_t, target, side="right") - 1] - ref_c[start]
        ret[~known] = np.nan
        out[name] = ret
    return out, day


def _edge(mask):
    mask = np.asarray(mask, dtype=bool)
    return np.flatnonzero(mask & ~np.r_[False, mask[:-1]])


def signals(f):
    """Name -> (Bars, erwartete Richtung, Familie). Ein Signal zaehlt nur beim Eintritt in den Zustand."""
    rsi, z, bb = f.rsi14.to_numpy(), f.zscore20.to_numpy(), f.bb_pct.to_numpy()
    hist, cross, mom = f.macd_hist.to_numpy(), f.sma50_200.to_numpy(), f.mom_12_1.to_numpy()
    ret, leg = f["fib_ret_k3"].to_numpy(), f["fib_dir_k3"].to_numpy()
    out = {
        "RSI unter 30": (_edge(rsi < 30), 1, "MR"),
        "RSI ueber 70": (_edge(rsi > 70), -1, "MR"),
        "Bollinger unten": (_edge(bb < 0), 1, "MR"),
        "Bollinger oben": (_edge(bb > 1), -1, "MR"),
        "Z-Score unter -2": (_edge(z < -2), 1, "MR"),
        "Z-Score ueber 2": (_edge(z > 2), -1, "MR"),
        "MACD kreuzt hoch": (_edge(hist > 0), 1, "MOM"),
        "MACD kreuzt runter": (_edge(hist < 0), -1, "MOM"),
        "Golden Cross": (_edge(cross > 0), 1, "MOM"),
        "Death Cross": (_edge(cross < 0), -1, "MOM"),
        "12-1-Momentum positiv": (_edge(mom > 0), 1, "MOM"),
        "12-1-Momentum negativ": (_edge(mom < 0), -1, "MOM"),
    }
    for level, label in ((0.382, "38,2"), (0.618, "61,8")):
        touch = np.abs(ret - level) <= 0.02
        out[f"Fib {label} im Aufwaertsschwung"] = (_edge(touch & (leg > 0)), 1, "FIB")
        out[f"Fib {label} im Abwaertsschwung"] = (_edge(touch & (leg < 0)), -1, "FIB")
    return out


def n_independent(days, horizon):
    """Wie viele Ereignisse liegen mindestens einen Horizont auseinander? Das ist die ehrliche Fallzahl."""
    count, last = 0, -np.inf
    for d in np.unique(days):
        if d >= last + horizon:
            count, last = count + 1, d
    return count


def fdr_q(p):
    """Benjamini-Hochberg: erwarteter Anteil falscher Treffer, wenn man bis zu diesem p-Wert alles glaubt."""
    p = np.asarray(p, dtype=float)
    order = np.argsort(p)
    q = p[order] * len(p) / np.arange(1, len(p) + 1)
    q = np.minimum.accumulate(q[::-1])[::-1]
    out = np.empty(len(p))
    out[order] = np.minimum(q, 1.0)
    return out


def lo_statistic(x):
    """Lo (1991): modifizierte R/S-Statistik, robust gegen Kurzfrist-Abhaengigkeit. 95 %-Bereich: 0,809 bis 1,862."""
    n = len(x)
    d = x - x.mean()
    s = np.cumsum(d)
    rho = np.corrcoef(x[1:], x[:-1])[0, 1]
    q = 0  # Lag-Wahl nach Andrews
    if np.isfinite(rho) and rho != 0:
        q = min(int((1.5 * n) ** (1 / 3) * (2 * abs(rho) / (1 - rho * rho)) ** (2 / 3)), n // 4)
    var = d @ d / n
    for j in range(1, q + 1):
        var += 2 * (1 - j / (q + 1)) * (d[j:] @ d[:-j]) / n
    return (s.max() - s.min()) / np.sqrt(var * n) if var > 0 else np.nan


def regime_test(fwd, day, h, tests, family, horizon):
    """Hurst als Schalter: Wirken MR-Signale bei H < 0,5 und Momentum-Signale bei H > 0,5 besser?"""
    bars, sides = [], []
    for b, side, fam in tests.values():
        if fam == family:
            bars.append(b), sides.append(np.full(len(b), side))
    if not bars:
        return None
    bars, sides = np.concatenate(bars), np.concatenate(sides)
    r = fwd[horizon]
    valid = np.isfinite(r[bars]) & np.isfinite(h[bars])
    bars, sides = bars[valid], sides[valid]
    if len(bars) < 2 * MIN_EVENTS:
        return None
    signed = sides * (r[bars] - np.nanmean(r))
    low = h[bars] < 0.5
    if low.sum() < MIN_EVENTS or (~low).sum() < MIN_EVENTS:
        return None
    block = day[bars] // HORIZONS[horizon]
    # Welch-Test auf Blockmittelwerten, weil sich Ereignisse innerhalb eines Horizonts ueberlappen
    lo_m = pd.Series(signed[low]).groupby(block[low]).mean()
    hi_m = pd.Series(signed[~low]).groupby(block[~low]).mean()
    if len(lo_m) < 3 or len(hi_m) < 3:
        return None
    se = np.sqrt(lo_m.var() / len(lo_m) + hi_m.var() / len(hi_m))
    return {"familie": family, "horizont": horizon, "n_low": int(low.sum()), "n_high": int((~low).sum()),
            "mean_low": signed[low].mean(), "mean_high": signed[~low].mean(),
            "t_diff": (lo_m.mean() - hi_m.mean()) / se if se > 0 else np.nan}


def control_rows(df, of_tf, tf, seed):
    """Jedes Muster gegen zufaellige Einstiege mit gleichen SL/TP-Abstaenden in ATR."""
    h, l, c = (df[col].to_numpy(dtype=float) for col in ("high", "low", "close"))
    atr = talib.ATR(h, l, c, 14)
    rows = []
    for pid, name in enumerate(PATTERNS):
        g = of_tf[of_tf.pattern == pid].drop_duplicates("bar")
        bar = g.bar.to_numpy(dtype=np.int64)
        known = np.isfinite(atr[bar]) & (atr[bar] > 0)
        g, bar = g[known], bar[known]
        if len(g) < MIN_EVENTS:
            continue
        entry = g.entry.to_numpy(dtype=float)
        max_bars = np.maximum(10, 3 * (bar - g.start.to_numpy(dtype=np.int64)))
        r, control, p = ioncore.control_test(
            h, l, c, atr, bar, g.side.to_numpy(dtype=np.int64), (g.sl.to_numpy(dtype=float) - entry) / atr[bar],
            (g.tp.to_numpy(dtype=float) - entry) / atr[bar], max_bars, N_CONTROL, seed + pid)
        rows.append({"timeframe": tf, "pattern": pid, "name": name, "n": len(g), "r": r, "kontrolle": control, "p": p})
    return rows


def run(symbol, con=None, wall=0.0, cpu=0.0):
    symbol = symbol.upper()
    con = con or connect()
    started, cpu_started = time.perf_counter(), time.process_time()
    events = pd.read_sql_query("SELECT * FROM events WHERE symbol=?", con, params=(symbol,))
    rows, controls, regimes, fractal, mean_rev, total_bars, seed = [], [], [], [], [], 0, 1
    for tf in TIMEFRAMES:
        df = load(con, symbol, tf)
        if df.empty:
            continue
        total_bars += len(df)
        f = load_features(symbol, tf)
        fwd, day = forward_returns(con, symbol, tf, df.index)
        tests = signals(f)
        of_tf = events[events.timeframe == tf]
        controls += control_rows(df, of_tf, tf, seed)
        print(f"{tf}: Kontrollgruppen fertig, {time.perf_counter() - started:.0f} s", flush=True)
        for pid, name in enumerate(PATTERNS):
            hits = np.unique(of_tf[of_tf.pattern == pid].bar.to_numpy(dtype=np.int64))
            tests[name] = (hits, -1 if pid < 10 else 1, "Muster")
        for name, (bars, side, family) in tests.items():
            bars = np.asarray(bars, dtype=np.int64)
            if len(bars) < MIN_EVENTS:
                continue
            for hz, days in HORIZONS.items():
                r = fwd[hz]
                seed += 1
                mean_ev, mean_all, p, k = ioncore.shift_test(r, bars, N_SHIFT, seed)
                if k < MIN_EVENTS or not np.isfinite(p):
                    continue
                valid = bars[np.isfinite(r[bars])]
                rows.append({"timeframe": tf, "signal": name, "familie": family, "richtung": side, "horizont": hz,
                             "n": int(k), "n_unabh": n_independent(day[valid], days), "mean": mean_ev,
                             "base": mean_all, "p_up": float((r[valid] > 0).mean()),
                             "base_up": float((r[np.isfinite(r)] > 0).mean()), "p": p})

        # Fraktal und Mean Reversion je Timeframe
        close = df.close.to_numpy(dtype=float)
        if len(close) >= 128:
            ret = np.diff(np.log(close))
            h_cols = [c for c in f.columns if c.startswith("h2_")]
            longest = f[max(h_cols, key=lambda c: int(c.split("_")[1]))].to_numpy() if h_cols else None
            row = {"timeframe": tf, "bars": len(close),
                   "H": ioncore.rolling_mfdfa(ret, len(ret))["h2"][-1],
                   "H_abs": ioncore.rolling_mfdfa(np.abs(ret), len(ret))["h2"][-1],
                   "lo": lo_statistic(ret), "lo_abs": lo_statistic(np.abs(ret))}
            if longest is not None:
                row.update(share_trend=float(np.nanmean(longest[np.isfinite(longest)] > 0.55)),
                           share_revert=float(np.nanmean(longest[np.isfinite(longest)] < 0.45)))
                for family in ("MR", "MOM"):
                    for hz in ("1T", "7T"):
                        res = regime_test(fwd, day, longest, tests, family, hz)
                        if res:
                            regimes.append({"timeframe": tf, **res})
            fractal.append(row)
        if "adf" in f:
            adf = f.adf.to_numpy()
            mean_rev.append({"timeframe": tf, "stationaer": float(np.nanmean(adf[np.isfinite(adf)] < -2.86)),
                             "halbwertszeit": float(np.nanmedian(f.half_life)), "vr2": float(np.nanmedian(f.vr2)),
                             "vr4": float(np.nanmedian(f.vr4)), "vr8": float(np.nanmedian(f.vr8))})

    study = pd.DataFrame(rows)
    study["q"] = fdr_q(study.p)
    study["excess"] = study["mean"] - study.base
    study["passt"] = np.sign(study.excess) == study.richtung
    replace_rows(con, "study", symbol, study)
    control = pd.DataFrame(controls)
    control["excess"] = control.r - control.kontrolle
    control["q"] = fdr_q(control.p)
    replace_rows(con, "pattern_control", symbol, control)
    replace_rows(con, "fractal", symbol, pd.DataFrame(fractal))
    replace_rows(con, "regime", symbol, pd.DataFrame(regimes))
    replace_rows(con, "mean_reversion", symbol, pd.DataFrame(mean_rev))
    study_wall, study_cpu = time.perf_counter() - started, time.process_time() - cpu_started
    path = write_report(symbol, study, control, events, fractal, regimes, mean_rev, total_bars,
                        wall + study_wall, cpu + study_cpu)
    hits = study[study.q < FDR]
    print(f"\nStudie: {study_wall:.0f} s, CPU {study_cpu / study_wall / ioncore.threads():.0%}. {len(study):,} Tests: "
          f"{len(hits)} signifikant nach FDR ({int(hits.passt.sum())} in erwarteter Richtung). "
          f"Muster gegen Kontrolle: {(control.q < FDR).sum()} von {len(control)}. Report: {path}", flush=True)
    return study


def _pct(x):
    return f"{100 * x:+.2f} %"


def mean_rank_corr(matrix):
    """Mittlere Spearman-Korrelation zwischen allen Timeframe-Paaren mit genug gemeinsamen Mustern."""
    corr = matrix.corr(method="spearman", min_periods=6)
    upper = corr.where(np.triu(np.ones(corr.shape, dtype=bool), 1)).stack()
    return upper.mean() if len(upper) else np.nan, len(upper)


def write_report(symbol, study, control, events, fractal, regimes, mean_rev, total_bars, wall, cpu):
    REPORTS.mkdir(exist_ok=True)
    threads = ioncore.threads()
    lines = [f"# {symbol}: Phase-2-Report", "",
             f"Stand {datetime.now():%Y-%m-%d %H:%M}. {total_bars:,} Bars einzeln durchgerechnet. "
             f"Gesamtlauf: {wall:.0f} s auf {threads} Threads, CPU-Auslastung {cpu / max(wall, 1e-9) / threads:.0%}.", ""]

    # 1. Chartmuster
    e = events.drop_duplicates(["timeframe", "pattern", "bar"])
    e = e[e.outcome != -2]
    lines += ["## 1. Die 20 Chartmuster: was wurde zuerst getroffen?", "",
              "Entry, SL und TP wie im Bild. R = Gewinn in Einheiten des Risikos. Break-even = Trefferquote, ab der das "
              f"Muster ohne Kosten nichts verliert. Kontrolle = {N_CONTROL:,} Läufe mit gleicher Richtung und gleichen "
              "SL/TP-Abständen in ATR, aber an zufällig verschobenen Zeitpunkten. Erst die Differenz zeigt, was das Muster "
              "über den Grundtrend der Aktie hinaus leistet.", "",
              "| Muster | n | TP zuerst | SL zuerst | Zeitlimit | Break-even | Ø R | Ø R Kontrolle | Differenz |",
              "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for pid, name in enumerate(PATTERNS):
        g = e[e.pattern == pid]
        c = control[control.pattern == pid]
        if len(g) < MIN_EVENTS or c.empty:
            lines.append(f"| {name} | {len(g)} | zu wenig | | | | | | |")
            continue
        risk = (g.entry - g.sl).abs()
        reward = (g.tp - g.entry).abs()
        base = np.average(c.kontrolle, weights=c.n)
        real = np.average(c.r, weights=c.n)
        lines.append(f"| {name} | {len(g):,} | {(g.outcome == 1).mean():.1%} | {(g.outcome == -1).mean():.1%} | "
                     f"{(g.outcome == 0).mean():.1%} | {(risk / (risk + reward)).mean():.1%} | {real:+.3f} | "
                     f"{base:+.3f} | {real - base:+.3f} |")

    # Fraktal-Probe: gleiches Muster, gleiche Erwartung ueber alle Timeframes?
    order = [tf for tf in TIMEFRAMES if tf in set(control.timeframe)]
    enough = control[control.n >= 20]
    excess = enough.pivot(index="pattern", columns="timeframe", values="excess").reindex(columns=order)
    stars = enough.pivot(index="pattern", columns="timeframe", values="q").reindex(columns=order)
    raw = enough.pivot(index="pattern", columns="timeframe", values="r").reindex(columns=order)
    lines += ["", "### Differenz zur Kontrolle in R je Muster und Timeframe (mindestens 20 Fälle, * = signifikant nach FDR)", "",
              "| Muster | " + " | ".join(order) + " |", "|---|" + "---:|" * len(order)]
    for pid, row in excess.iterrows():
        cells = ["" if pd.isna(v) else f"{v:+.2f}" + ("*" if stars.loc[pid, tf] < FDR else "") for tf, v in row.items()]
        lines.append(f"| {PATTERNS[pid]} | " + " | ".join(cells) + " |")
    raw_corr, raw_pairs = mean_rank_corr(raw)
    excess_corr, excess_pairs = mean_rank_corr(excess)
    lines += ["", f"**Muster gegen Kontrolle:** {(control.q < FDR).sum()} von {len(control)} Kombinationen signifikant nach FDR; "
                  f"ohne Korrektur p<5 %: {(control.p < 0.05).sum()} (Zufall: rund {0.05 * len(control):.0f}).", "",
              f"**Selbstähnlichkeit über Timeframes** (mittlere Rangkorrelation, nahe +1 = dasselbe Verhalten, nahe 0 = keines): "
              f"roh {raw_corr:+.2f} aus {raw_pairs} Paaren, nach Abzug der Kontrolle **{excess_corr:+.2f}** aus {excess_pairs} Paaren."]

    # 2. Ereignisstudie
    hits = study[study.q < FDR].sort_values("q")
    lines += ["", "## 2. Ereignisstudie: alle Muster und Indikatorsignale", "",
              f"{len(study):,} Tests, je {N_SHIFT:,} zufällige Verschiebungen. Nach Korrektur für viele Tests (FDR {FDR:.0%}) "
              f"bleiben **{len(hits)}** übrig, davon **{int(hits.passt.sum())}** in der erwarteten Richtung.", "",
              f"Ohne Korrektur p<5 %: {(study.p < 0.05).sum()} Tests (bei reinem Zufall rund {0.05 * len(study):.0f}). "
              f"Median aller p-Werte: {study.p.median():.2f} (bei reinem Zufall 0,50).", "",
              "n unabh. = Ereignisse, die mindestens einen Horizont auseinanderliegen.", ""]
    if len(hits):
        lines += ["| Signal | TF | Horizont | n | n unabh. | Ø Rendite | Normal | P(steigt) | Normal | q | Erwartung |",
                  "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|"]
        for _, h in hits.head(40).iterrows():
            lines.append(f"| {h.signal} | {h.timeframe} | {h.horizont} | {h.n:,} | {h.n_unabh:,} | {_pct(h['mean'])} | "
                         f"{_pct(h.base)} | {h.p_up:.1%} | {h.base_up:.1%} | {h.q:.4f} | "
                         f"{'bestätigt' if h.passt else 'Gegenteil'} |")
    by_family = study.assign(sig=study.q < FDR).groupby("familie").agg(tests=("sig", "size"), treffer=("sig", "sum"))
    lines += ["", "| Familie | Tests | Signifikant |", "|---|---:|---:|"]
    lines += [f"| {name} | {r.tests:,} | {r.treffer} |" for name, r in by_family.iterrows()]

    # 3. Fraktal
    lines += ["", "## 3. Fraktale Markthypothese", "",
              "H = DFA-Hurst der Renditen (0,5 = kein Gedächtnis). H |Rendite| = Gedächtnis der Schwankung. "
              "Lo = Test gegen Scheineffekte; außerhalb von 0,809 bis 1,862 ist Langzeit-Gedächtnis bei 95 % signifikant.", "",
              "| TF | Bars | H | Lo | Gedächtnis? | H abs. | Lo abs. | Gedächtnis? | Zeit H>0,55 | Zeit H<0,45 |",
              "|---|---:|---:|---:|---|---:|---:|---|---:|---:|"]
    for r in fractal:
        sig = lambda v: "ja" if np.isfinite(v) and not 0.809 <= v <= 1.862 else "nein"
        share = lambda key: f"{r[key]:.0%}" if key in r else "–"
        lines.append(f"| {r['timeframe']} | {r['bars']:,} | {r['H']:.3f} | {r['lo']:.2f} | {sig(r['lo'])} | {r['H_abs']:.3f} | "
                     f"{r['lo_abs']:.2f} | {sig(r['lo_abs'])} | {share('share_trend')} | {share('share_revert')} |")

    # 4. Schalter
    lines += ["", "## 4. Ist Hurst der Schalter zwischen Mean Reversion und Momentum?", "",
              "Rendite in Signalrichtung über dem Normalwert, getrennt nach H zum Signalzeitpunkt. Die These stimmt, wenn "
              "MR bei H<0,5 und Momentum bei H>0,5 besser abschneidet; |t| ab rund 2 ist unterscheidbar.", ""]
    if regimes:
        lines += ["| TF | Familie | Horizont | n H<0,5 | Ø H<0,5 | n H>0,5 | Ø H>0,5 | t Differenz | These |",
                  "|---|---|---|---:|---:|---:|---:|---:|---|"]
        supported = 0
        for r in regimes:
            good = r["t_diff"] > 2 if r["familie"] == "MR" else r["t_diff"] < -2
            supported += bool(good)
            lines.append(f"| {r['timeframe']} | {r['familie']} | {r['horizont']} | {r['n_low']:,} | {_pct(r['mean_low'])} | "
                         f"{r['n_high']:,} | {_pct(r['mean_high'])} | {r['t_diff']:+.1f} | {'gestützt' if good else '-'} |")
        lines += ["", f"**Gestützt in {supported} von {len(regimes)} Vergleichen.**"]

    # 5. Mean Reversion
    lines += ["", "## 5. Mean Reversion und Momentum", "",
              "Rollend über 256 Bars. Stationär = ADF unter -2,86: In diesem Fenster kehrt der Kurs messbar zum Mittelwert zurück "
              "(bei reinem Zufall rund 5 % der Fenster). Variance Ratio unter 1 = Umkehr, über 1 = Trend.", "",
              "| TF | Zeit stationär | Halbwertszeit (Bars) | VR 2 | VR 4 | VR 8 |", "|---|---:|---:|---:|---:|---:|"]
    for r in mean_rev:
        lines.append(f"| {r['timeframe']} | {r['stationaer']:.1%} | {r['halbwertszeit']:.0f} | {r['vr2']:.3f} | {r['vr4']:.3f} | {r['vr8']:.3f} |")

    path = REPORTS / f"{symbol}_phase2.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
