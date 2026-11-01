"""Phase 3: Pattern-Matching. Vergleicht den aktuellen Verlauf mit Millionen historischer Sequenzen."""
import time

import ioncore
import numpy as np
import pandas as pd
import torch

from .dataset import HORIZON_DAYS, HORIZON_NAMES
from .store import load
from .study import HORIZONS, forward_returns, naive_seconds
from .train import block_ci

MATCH_TFS = ("1m", "5m", "15m", "1h", "4h", "1D")
WINDOWS = (32, 64, 128)  # Fensterlaengen in Bars; alle werden auf LENGTH Punkte gebracht
LENGTH = 64
TF_MINUTES = {"1m": 1, "5m": 5, "15m": 15, "1h": 60, "4h": 240, "1D": 390}


class MatchIndex:
    """series: tf -> {logp, ts, day, rets (n, Horizonte)}. Alle Fenster liegen normiert auf der GPU."""

    def __init__(self, series, windows=WINDOWS, device="cuda"):
        self.device = device
        self.series = series  # fuer den Folgeverlauf der Analogien im Chart
        vectors, tf_ids, win, bars, ts, day, rets = [], [], [], [], [], [], []
        self.tf_names = list(series)
        for tf_id, (tf, s) in enumerate(series.items()):
            for w in windows:
                if len(s["logp"]) < w:
                    continue
                vectors.append(ioncore.make_windows(s["logp"], w, LENGTH))
                ends = np.arange(w - 1, len(s["logp"]))
                tf_ids.append(np.full(len(ends), tf_id, dtype=np.int8)), win.append(np.full(len(ends), w, dtype=np.int16))
                bars.append(ends), ts.append(s["ts"][ends]), day.append(s["day"][ends]), rets.append(s["rets"][ends])
        self.vectors = torch.from_numpy(np.concatenate(vectors)).to(device)
        self.tf = np.concatenate(tf_ids)
        self.window = np.concatenate(win)
        self.bar = np.concatenate(bars)
        self.ts = np.concatenate(ts)
        self.ts_gpu = torch.from_numpy(self.ts).to(device)
        self.day = np.concatenate(day)
        self.rets = np.concatenate(rets).astype(np.float32)

    def __len__(self):
        return len(self.vectors)

    @classmethod
    def from_db(cls, con, symbol, device="cuda"):
        series = {}
        for tf in MATCH_TFS:
            bars = load(con, symbol, tf)
            if bars.empty:
                continue
            fwd, day = forward_returns(con, symbol, tf, bars.index)
            series[tf] = {"logp": np.log(bars.close.to_numpy(dtype=float)), "ts": bars.index.as_unit("s").asi8,
                          "day": day, "rets": np.stack([fwd[h] for h in HORIZON_NAMES], axis=1)}
        return cls(series, device=device)

    @torch.inference_mode()
    def query(self, logp, now_ts, exclude_seconds=0, candidates=4096, k=200):
        """Die k aehnlichsten Verlaeufe vor now_ts. Der eigene juengste Zeitraum zaehlt nicht als Treffer."""
        q = torch.from_numpy(ioncore.make_windows(np.asarray(logp, dtype=float), len(logp), LENGTH)[0].copy()).to(self.device)
        score = self.vectors @ q
        score[self.ts_gpu > now_ts - exclude_seconds] = -2
        top = torch.topk(score, min(candidates, len(score)))
        keep = top.values > -2
        idx = top.indices[keep].cpu().numpy()
        scores = top.values[keep].cpu().numpy()
        if len(idx) == 0:
            return pd.DataFrame(columns=["timeframe", "window", "bar", "ts", "day", "score", "dtw"])
        # Je Handelstag nur der beste Treffer; topk ist absteigend sortiert, np.unique liefert das erste Vorkommen
        _, first = np.unique(self.day[idx], return_index=True)
        first = np.sort(first)
        idx, scores = idx[first], scores[first]
        distance = ioncore.dtw(q.cpu().numpy(), self.vectors[torch.from_numpy(idx).to(self.device)].cpu().numpy(), LENGTH // 10)
        order = np.argsort(distance)[:k]
        idx = idx[order]
        out = pd.DataFrame({"timeframe": [self.tf_names[i] for i in self.tf[idx]], "window": self.window[idx], "bar": self.bar[idx],
                            "ts": self.ts[idx], "day": self.day[idx], "score": scores[order], "dtw": distance[order]})
        for h, name in enumerate(HORIZON_NAMES):
            out[f"ret_{name}"] = self.rets[idx, h]
        return out


def summarize(analogs, query_day):
    """Verteilung des Folgeverlaufs je Horizont. Es zaehlt nur, was zum Abfragezeitpunkt schon bekannt war."""
    rows = {}
    for name, days in HORIZONS.items():
        r = analogs[f"ret_{name}"].to_numpy(dtype=float)
        known = np.isfinite(r) & (analogs.day.to_numpy() + days < query_day)
        r = r[known]
        rows[name] = {"n": len(r), "p_up": float((r > 0).mean()) if len(r) else np.nan,
                      "q10": float(np.quantile(r, 0.1)) if len(r) else np.nan,
                      "q50": float(np.quantile(r, 0.5)) if len(r) else np.nan,
                      "q90": float(np.quantile(r, 0.9)) if len(r) else np.nan}
    return rows


def evaluate(con, symbol, val_start, holdout_start, n_queries=3000, query_tf="5m", window=64, k=200, seed=11):
    """Schlaegt das Matching die Basisrate? Jede Abfrage kennt nur die Vergangenheit bis zu ihrem Zeitpunkt."""
    index = MatchIndex.from_db(con, symbol)
    bars = load(con, symbol, query_tf)
    logp = np.log(bars.close.to_numpy(dtype=float))
    ts = bars.index.as_unit("s").asi8
    fwd, day = forward_returns(con, symbol, query_tf, bars.index)
    calendar = naive_seconds(load(con, symbol, "1D").index) // 86400
    dates = naive_seconds(bars.index) // 86400
    candidates = np.flatnonzero((dates >= val_start) & (dates < holdout_start))
    rng = np.random.default_rng(seed)
    picks = np.sort(rng.choice(candidates, min(n_queries, len(candidates)), replace=False))
    exclude = window * TF_MINUTES[query_tf] * 60

    # Vergleichsmassstab: Basisrate aus allem, was zum Abfragezeitpunkt bekannt war
    prediction, baseline = {h: [] for h in HORIZONS}, {h: [] for h in HORIZONS}
    actual, when, seconds = {h: [] for h in HORIZONS}, {h: [] for h in HORIZONS}, []
    for a in picks:
        tic = time.perf_counter()
        analogs = index.query(logp[a - window + 1:a + 1], ts[a], exclude, k=k)
        seconds.append(time.perf_counter() - tic)
        summary = summarize(analogs, day[a])
        for name, days in HORIZONS.items():
            r = fwd[name][a]
            label_end = day[a] + days
            if not np.isfinite(r) or label_end >= len(calendar) or calendar[label_end] >= holdout_start:
                continue
            known = fwd[name][:a][np.isfinite(fwd[name][:a]) & (day[:a] + days < day[a])]
            base = float((known > 0).mean()) if len(known) else 0.5
            baseline[name].append(base)
            prediction[name].append(summary[name]["p_up"] if summary[name]["n"] >= 20 else base)
            actual[name].append(float(r > 0))
            when[name].append(dates[a])
    rows = []
    for name, days in HORIZONS.items():
        if not actual[name]:
            rows.append({"horizont": name, "n": 0})
            continue
        up, p, b, d = (np.array(v) for v in (actual[name], prediction[name], baseline[name], when[name]))
        err_model, err_base = (p - up) ** 2, (b - up) ** 2
        blocks = d // HORIZON_DAYS[name]  # d sind Kalendertage
        low, high = block_ci(err_model, err_base, blocks)
        rows.append({"horizont": name, "n": len(up), "n_unabh": len(np.unique(blocks)),
                     "brier_skill": 1 - err_model.sum() / err_base.sum(), "brier_low": low, "brier_high": high,
                     "p_mittel": float(p.mean()), "basis_mittel": float(b.mean())})
    timing = {"sequenzen": len(index), "abfragen": len(picks), "ms_median": 1000 * float(np.median(seconds)),
              "ms_p99": 1000 * float(np.quantile(seconds, 0.99))}
    return pd.DataFrame(rows), timing


def daily_signals(con, symbol, days, query_tf="5m", window=64, k=200):
    """P(steigt) laut Matching zum Handelsschluss jedes Tages. NaN, wenn zu wenige Analogien ihren Ausgang schon kennen."""
    index = MatchIndex.from_db(con, symbol)
    bars = load(con, symbol, query_tf)
    logp = np.log(bars.close.to_numpy(dtype=float))
    ts = bars.index.as_unit("s").asi8
    _, day = forward_returns(con, symbol, query_tf, bars.index)
    dates = naive_seconds(bars.index) // 86400
    exclude = window * TF_MINUTES[query_tf] * 60
    out = np.full((len(days), len(HORIZON_NAMES)), np.nan, dtype=np.float32)
    for i, d in enumerate(days):
        last = np.searchsorted(dates, d, side="right") - 1
        if last < window - 1 or dates[last] != d:
            continue
        summary = summarize(index.query(logp[last - window + 1:last + 1], ts[last], exclude, k=k), day[last])
        for h, name in enumerate(HORIZON_NAMES):
            if summary[name]["n"] >= 20:
                out[i, h] = summary[name]["p_up"]
    del index
    torch.cuda.empty_cache()
    return out


def report(con, symbol, val_start, holdout_start, path):
    scores, timing = evaluate(con, symbol, val_start, holdout_start)
    lines = ["", "## Pattern-Matching", "",
             f"{timing['sequenzen']:,} historische Sequenzen über {len(MATCH_TFS)} Timeframes und {len(WINDOWS)} Fensterlängen. "
             f"{timing['abfragen']:,} Abfragen, jede kennt nur die Vergangenheit bis zu ihrem Zeitpunkt. "
             f"Dauer je Abfrage: Median {timing['ms_median']:.0f} ms, 99 % unter {timing['ms_p99']:.0f} ms.", "",
             "| Horizont | Abfragen | unabhängig | Brier Skill | 95 %-Intervall | Ø P(steigt) Matching | Ø Basisrate |",
             "|---|---:|---:|---:|---:|---:|---:|"]
    for r in scores.to_dict("records"):
        if r["n"] == 0:
            lines.append(f"| {r['horizont']} | 0 | | | | | |")
            continue
        lines.append(f"| {r['horizont']} | {r['n']:,} | {r['n_unabh']} | {100 * r['brier_skill']:+.2f} % | "
                     f"{100 * r['brier_low']:+.1f} bis {100 * r['brier_high']:+.1f} | {r['p_mittel']:.1%} | {r['basis_mittel']:.1%} |")
    with open(path, "a", encoding="utf-8") as out:
        out.write("\n".join(lines) + "\n")
    return scores, timing
