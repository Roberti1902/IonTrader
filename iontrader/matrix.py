"""Phase 5: Wahrscheinlichkeits-Matrix. Stacking, Kalibrierung und die Abschlusspruefung."""
import json
import math
import time
from dataclasses import dataclass
from datetime import datetime

import numpy as np
import pandas as pd
import torch

from . import ROOT, match, risk, setup, study, train
from .dataset import HORIZON_DAYS, fold_dates, load_ticker
from .models import KINDS
from .store import connect, load, replace_rows
from .study import FDR, HORIZONS, naive_seconds
from .train import OOS, REPORTS, block_ci

HORIZON_NAMES = list(HORIZONS)
HORIZON_STEPS = list(HORIZONS.values())
# Kalendertage, bis eine Zielgroesse sicher bekannt ist; 252 Handelstage koennen etwas mehr als 365 Tage sein
PURGE_DAYS = (5, 10, 35, 190, 372)
L2 = 10.0  # Vorab festgelegt: Bei wenigen unabhaengigen Faellen bleibt das Ergebnis dadurch nahe der Basisrate
PATTERN_TFS = ("15m", "1h", "4h", "1D")
PATTERN_DAYS = 5
BINS = (0.0, 0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 1.0)
CONFIG = ROOT / "data"
MIN_STACK_ROWS = 20


def sigmoid(x):
    return 1 / (1 + np.exp(-x))


def logit(p):
    p = np.clip(p, 0.001, 0.999)
    return np.log(p / (1 - p))


# ---------------------------------------------------------------------------
# Stacking und Kalibrierung
# ---------------------------------------------------------------------------

def fit_stack(x, up, base, sample_weight, l2=L2, iterations=500):
    """logit(p) = logit(Basisrate) + x @ w mit w >= 0 und Ridge-Strafe.

    Die Beispiele sind nach ihrer Ueberlappung gewichtet: Wenig unabhaengige Faelle heissen wenig Gesamtgewicht,
    die Strafe gewinnt und das Ergebnis bleibt bei der Basisrate. Das zieht lange Horizonte automatisch dorthin.
    """
    n, k = x.shape
    w = np.zeros(k)
    if n == 0 or k == 0:
        return w
    s = np.full(n, float(sample_weight))
    step = 1 / (0.25 * np.linalg.eigvalsh((x * s[:, None]).T @ x).max() + l2)
    z, t = w.copy(), 1.0
    for _ in range(iterations):
        grad = x.T @ (s * (sigmoid(base + x @ z) - up)) + l2 * z
        next_w = np.maximum(z - step * grad, 0)
        next_t = (1 + math.sqrt(1 + 4 * t * t)) / 2
        z = next_w + (t - 1) / next_t * (next_w - w)
        w, t = next_w, next_t
    return w


def isotonic_fit(x, y, weight=None):
    """Pool-Adjacent-Violators: die beste monoton steigende Abbildung. Liefert (Stuetzstellen, Werte)."""
    order = np.argsort(x)
    x, y = np.asarray(x, dtype=float)[order], np.asarray(y, dtype=float)[order]
    weight = np.ones(len(x)) if weight is None else np.asarray(weight, dtype=float)[order]
    values, weights, right = [], [], []
    for xi, yi, wi in zip(x, y, weight):
        values.append(yi), weights.append(wi), right.append(xi)
        while len(values) > 1 and values[-2] >= values[-1]:
            total = weights[-2] + weights[-1]
            values[-2] = (values[-2] * weights[-2] + values[-1] * weights[-1]) / total
            weights[-2] = total
            right[-2] = right[-1]
            values.pop(), weights.pop(), right.pop()
    return np.array(right), np.array(values)


def conformal_factor(low, high, realized, level=0.8):
    """Conformalized Quantile Regression: um wie viele Bandbreiten das Band wachsen muss, damit level stimmt."""
    width = np.maximum(high - low, 1e-9)
    score = np.maximum((low - realized) / width, (realized - high) / width)
    n = len(score)
    return float(np.quantile(score, min(1.0, level * (n + 1) / n))) if n else 0.0


def widen(low, high, factor):
    width = high - low
    return low - factor * width, high + factor * width


def reliability(p, up, days):
    """Stimmt, was angezeigt wird? Je Bereich: angezeigte Wahrscheinlichkeit, tatsaechliche Quote und unabhaengige Faelle."""
    rows = []
    for a, b in zip(BINS[:-1], BINS[1:]):
        m = (p >= a) & (p < b)
        if m.any():
            rows.append({"von": a, "bis": b, "n": int(m.sum()), "unabhaengig": int(len(np.unique(days[m]))), "angezeigt": float(p[m].mean()), "tatsaechlich": float(up[m].mean())})
    return rows


def calibration_error(p, up):
    """Durchschnittlicher Abstand zwischen Anzeige und Wirklichkeit, gewichtet nach Anzahl."""
    total = 0.0
    for a, b in zip(BINS[:-1], BINS[1:]):
        m = (p >= a) & (p < b)
        if m.any():
            total += m.sum() * abs(p[m].mean() - up[m].mean())
    return float(total / max(len(p), 1))


# ---------------------------------------------------------------------------
# Eingaben: je Handelstag ein Wert aus jedem Modell
# ---------------------------------------------------------------------------

@dataclass
class Daily:
    date: np.ndarray
    y: np.ndarray  # (Tage, Horizonte)
    mask: np.ndarray
    base_up: np.ndarray
    names: list
    x: np.ndarray  # (Tage, Horizonte, Quellen) Abweichung von der Basisrate in Logit

    @property
    def up(self):
        return (self.y > 0).astype(float)

    @property
    def base(self):
        return logit(self.base_up)


def _last_per_day(date):
    """Index des letzten Ankers je Tag, also der Stand zum Handelsschluss."""
    _, first = np.unique(date[::-1], return_index=True)
    return np.sort(len(date) - 1 - first)


def pattern_signal(con, symbol, days, lookback=PATTERN_DAYS):
    """Netto bullische minus baerische Muster der letzten Handelstage, begrenzt auf -1 bis +1. Nur bekannte Ereignisse."""
    events = pd.read_sql_query("SELECT timeframe, pattern, bar, side, ts FROM events WHERE symbol=?", con, params=(symbol,))
    events = events[events.timeframe.isin(PATTERN_TFS)].drop_duplicates(["timeframe", "pattern", "bar"])
    calendar = naive_seconds(load(con, symbol, "1D").index) // 86400
    event_days = naive_seconds(pd.to_datetime(events.ts.to_numpy(), unit="s", utc=True)) // 86400
    position = np.searchsorted(calendar, event_days)
    keep = position < len(calendar)
    counts = np.zeros(len(calendar) + 1)
    np.add.at(counts, position[keep] + 1, events.side.to_numpy(dtype=float)[keep])
    running = np.cumsum(counts)
    start = np.maximum(np.arange(len(calendar)) + 1 - lookback, 0)
    net = running[1:] - running[start]
    signal = net / (np.abs(net) + 5)
    where = np.searchsorted(calendar, days)
    out = np.zeros(len(days))
    known = (where < len(calendar)) & (calendar[np.minimum(where, len(calendar) - 1)] == days)
    out[known] = signal[where[known]]
    return out


def load_inputs(con, symbol, suffix, mc, signals):
    """Alle Modelle als Abweichung von der Basisrate. suffix waehlt Walk-Forward oder Abschlusspruefung."""
    sources, ref = {}, None
    for kind in KINDS:
        for tag in ("solo", "universe"):
            path = OOS / f"{symbol}_{kind}_{tag}{suffix}.npz"
            if not path.exists():
                continue
            with np.load(path) as data:
                last = _last_per_day(data["date"])
                if ref is None:
                    ref = {key: data[key][last] for key in ("date", "y", "mask", "base_up")}
                elif not np.array_equal(ref["date"], data["date"][last]):
                    raise ValueError(f"{path.name}: andere Tage als die uebrigen Modelle")
                sources[f"{kind} {tag}"] = data["logit"][last]
    if ref is None:
        raise SystemExit(f"{symbol}: keine Vorhersagen aus Phase 3, bitte zuerst 'train' laufen lassen")
    date, base = ref["date"], logit(ref["base_up"])
    x = {name: value - base for name, value in sources.items()}
    fhs = list(mc["engines"]).index("FHS")
    position = np.searchsorted(mc["dates"], date)
    inside = (position < len(mc["dates"])) & (mc["dates"][np.minimum(position, len(mc["dates"]) - 1)] == date)
    mc_x = np.zeros_like(base)
    mc_x[inside] = logit(mc["p_up"][position[inside], fhs]) - base[inside]
    x["monte carlo"] = mc_x
    x["matching"] = np.where(np.isfinite(signals), logit(signals) - base, 0.0)
    pattern = pattern_signal(con, symbol, date)
    x["muster"] = np.repeat(pattern[:, None], base.shape[1], axis=1)
    names = list(x)
    return Daily(date, ref["y"], ref["mask"], ref["base_up"], names, np.stack([x[n] for n in names], axis=2))


def direction_proven(walk_forward, holdout):
    """Ein Vorsprung gilt nur, wenn er sich wiederholt: In beiden Pruefzeitraeumen liegt das Intervall ganz ueber null."""
    above = lambda row: row.get("n", 0) > 0 and pd.notna(row.get("brier_low")) and row["brier_low"] > 1e-6
    return bool(above(walk_forward) and above(holdout))


def _concat(a, b):
    return Daily(np.r_[a.date, b.date], np.r_[a.y, b.y], np.r_[a.mask, b.mask], np.r_[a.base_up, b.base_up], a.names, np.r_[a.x, b.x])


# ---------------------------------------------------------------------------
# Walk-Forward
# ---------------------------------------------------------------------------

def stack_folds(daily, folds, start_with=None):
    """Fuer jedes Testjahr: Gewichte nur aus Tagen, deren Ergebnis vorher feststand. Liefert p und die Gewichte."""
    p = daily.base_up.astype(float).copy()
    up, base = daily.up, daily.base
    active = np.zeros(len(daily.date), dtype=bool)
    weights = {}
    for start, end in folds:
        test = (daily.date >= start) & (daily.date < end)
        fold_weights = []
        for h, days in enumerate(HORIZON_STEPS):
            train_rows = daily.mask[:, h] & (daily.date + PURGE_DAYS[h] < start)
            w = np.zeros(len(daily.names))
            if train_rows.sum() >= MIN_STACK_ROWS:
                w = fit_stack(daily.x[train_rows, h], up[train_rows, h], base[train_rows, h], 1 / days)
                p[test, h] = sigmoid(base[test, h] + daily.x[test, h] @ w)
            fold_weights.append(w)
        active |= test
        weights[start] = np.array(fold_weights)
    return p, active, weights


def calibrate_folds(p, daily, active, folds):
    """Isotonic je Testjahr, gelernt nur aus frueheren Stack-Vorhersagen. Liefert die kalibrierten Werte."""
    out = p.copy()
    for start, end in folds:
        test = (daily.date >= start) & (daily.date < end)
        for h in range(p.shape[1]):
            rows = active & daily.mask[:, h] & (daily.date + PURGE_DAYS[h] < start)
            if rows.sum() < MIN_STACK_ROWS * 5:
                continue
            xs, ys = isotonic_fit(p[rows, h], daily.up[rows, h])
            out[test, h] = np.interp(p[test, h], xs, ys)
    return out


def direction_rows(p, daily, rows_mask, label):
    """Brier Skill gegen die Basisrate je Horizont, mit Intervall auf unabhaengigen Bloecken."""
    out = []
    up, base_up = daily.up, daily.base_up
    for h, name in enumerate(HORIZON_NAMES):
        m = rows_mask & daily.mask[:, h]
        if not m.any():
            out.append({"quelle": label, "horizont": name, "n": 0})
            continue
        blocks = daily.date[m] // HORIZON_DAYS[name]  # Tage sind Kalendertage, die Bloecke also auch
        err, err_base = (p[m, h] - up[m, h]) ** 2, (base_up[m, h] - up[m, h]) ** 2
        low, high = block_ci(err, err_base, blocks)
        out.append({"quelle": label, "horizont": name, "n": int(m.sum()), "n_unabh": int(len(np.unique(blocks))),
                    "brier_skill": 1 - err.sum() / err_base.sum(), "brier_low": low, "brier_high": high,
                    "treffer": float(((p[m, h] > 0.5) == (up[m, h] > 0.5)).mean()), "basis_treffer": float(((base_up[m, h] > 0.5) == (up[m, h] > 0.5)).mean()),
                    "p_mittel": float(p[m, h].mean()), "p_streuung": float(p[m, h].std()), "quote": float(up[m, h].mean())})
    return out


def band_rows(mc, folds):
    """80 %-Spanne von Monte Carlo vor und nach der Conformal-Korrektur, jeweils nur mit vorher bekannten Ergebnissen."""
    fhs = list(mc["engines"]).index("FHS")
    i10, i90 = risk.LEVELS.index(0.1), risk.LEVELS.index(0.9)
    rows, dates = [], mc["dates"]
    for h, name in enumerate(HORIZON_NAMES):
        low, high, real = mc["q"][:, fhs, h, i10].astype(float), mc["q"][:, fhs, h, i90].astype(float), mc["realized"][:, h].astype(float)
        hit_raw, hit_new, width_raw, width_new = [], [], [], []
        for start, end in folds:
            past = np.isfinite(real) & (dates + PURGE_DAYS[h] < start)
            test = np.flatnonzero(np.isfinite(real) & (dates >= start) & (dates < end))
            if not past.any() or not len(test):
                continue
            factor = conformal_factor(low[past], high[past], real[past])
            new_low, new_high = widen(low[test], high[test], factor)
            hit_raw.append((real[test] >= low[test]) & (real[test] <= high[test]))
            hit_new.append((real[test] >= new_low) & (real[test] <= new_high))
            width_raw.append(high[test] - low[test]), width_new.append(new_high - new_low)
        if hit_raw:
            cat = np.concatenate
            rows.append({"horizont": name, "n": len(cat(hit_raw)), "unabhaengig": len(cat(hit_raw)) // HORIZON_STEPS[h], "roh": float(cat(hit_raw).mean()),
                         "conformal": float(cat(hit_new).mean()), "breite_roh": float(cat(width_raw).mean()), "breite_conformal": float(cat(width_new).mean())})
    return rows


def run_walk_forward(symbol, con=None, log=None, refresh=True):
    """Phase 5 ohne die unangetastete Zeit. Friert am Ende die Einstellungen fuer die Abschlusspruefung ein."""
    log = log or (lambda text: print(text, flush=True))
    symbol = symbol.upper()
    con = con or connect()
    tic = time.perf_counter()
    if refresh:  # Rechenintensiv; ohne neue Kursdaten aendert sich hier nichts
        study.run(symbol, con)
        setup.feature_ic(symbol, con, log=log)
    target = load_ticker(con, symbol)
    folds, holdout = fold_dates(target)
    with np.load(OOS / f"{symbol}_mc.npz") as data:
        mc = {key: data[key] for key in data.files}
    with np.load(OOS / f"{symbol}_{KINDS[0]}_solo.npz") as data:
        days = np.unique(data["date"])
    if days.max() >= holdout:
        raise RuntimeError("Walk-Forward enthaelt Tage aus der unangetasteten Zeit")
    signals = match.daily_signals(con, symbol, days)
    log(f"Matching-Signale: {len(days):,} Handelstage")
    daily = load_inputs(con, symbol, "", mc, signals)
    # Das erste Testjahr hat keine Vorgeschichte zum Lernen und bleibt auf der Basisrate
    p, active, weights = stack_folds(daily, folds[1:])
    calibrated = calibrate_folds(p, daily, active, folds[2:])
    calibrated_rows = np.zeros(len(daily.date), dtype=bool)
    for start, end in folds[2:]:
        calibrated_rows |= (daily.date >= start) & (daily.date < end)
    # Vorab festgelegte Entscheidungsregel: Isotonic nur, wo es im Walk-Forward wirklich besser war
    use_isotonic = []
    for h in range(p.shape[1]):
        m = calibrated_rows & daily.mask[:, h]
        better = m.any() and ((calibrated[m, h] - daily.up[m, h]) ** 2).sum() < ((p[m, h] - daily.up[m, h]) ** 2).sum()
        use_isotonic.append(bool(better))
    final_p = p.copy()
    for h, use in enumerate(use_isotonic):
        if use:
            final_p[:, h] = calibrated[:, h]
    rows = direction_rows(final_p, daily, active, "Stack")
    mc_only = sigmoid(daily.base + daily.x[:, :, daily.names.index("monte carlo")])
    rows += direction_rows(mc_only, daily, active, "Monte Carlo allein")
    rows += direction_rows(calibrated, daily, calibrated_rows, "Stack + Isotonic")
    frame = pd.DataFrame(rows)
    replace_rows(con, "matrix_walk_forward", symbol, frame)
    bands = band_rows(mc, folds)
    # Gleiche Regel fuer Conformal: nur, wo die Abdeckung im Walk-Forward wirklich naeher an 80 % lag
    use_conformal = [abs(r["conformal"] - 0.8) < abs(r["roh"] - 0.8) for r in bands]
    config = {"symbol": symbol, "erstellt": datetime.now().isoformat(timespec="seconds"), "l2": L2, "use_isotonic": use_isotonic,
              "use_conformal": use_conformal, "holdout": holdout, "folds": folds, "quellen": daily.names}
    (CONFIG / f"matrix_{symbol}.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    np.savez(OOS / f"{symbol}_stack.npz", p=final_p, active=active, date=daily.date, mask=daily.mask, y=daily.y, base_up=daily.base_up,
             signals=signals, days=days)
    last_weights = weights[max(weights)]
    summary = pd.DataFrame(last_weights, columns=daily.names, index=HORIZON_NAMES)
    log(f"Gewichte im letzten Testjahr:\n{summary.round(3).to_string()}")
    log(f"Walk-Forward Stack: " + " ".join(f"{r['horizont']}={100 * r.get('brier_skill', np.nan):+.2f}%" for r in rows[:5]))
    log(f"Isotonic genutzt: {dict(zip(HORIZON_NAMES, use_isotonic))}")
    log(f"Spanne: " + " ".join(f"{r['horizont']} {r['roh']:.1%}->{r['conformal']:.1%}" for r in bands))
    path = write_report(con, symbol, frame, summary, bands, config)
    log(f"Walk-Forward fertig nach {(time.perf_counter() - tic) / 60:.1f} min, eingefroren in data/matrix_{symbol}.json. Report: {path}")


# ---------------------------------------------------------------------------
# Abschlusspruefung auf den bisher unangetasteten 2 Jahren
# ---------------------------------------------------------------------------

def stack_history(con, symbol, config, final_folds, mc_past, mc_final):
    """Der Stack ueber beide Pruefzeitraeume, jede Vorhersage nur aus dem, was damals bekannt war. Genutzt von Abschlusspruefung und Backtest."""
    with np.load(OOS / f"{symbol}_stack.npz") as data:
        past_signals = data["signals"]
    with np.load(OOS / f"{symbol}_{KINDS[0]}_solo_final.npz") as data:
        final_days = np.unique(data["date"])
    final_signals = match.daily_signals(con, symbol, final_days)
    past = load_inputs(con, symbol, "", mc_past, past_signals)
    future = load_inputs(con, symbol, "_final", mc_final, final_signals)
    if past.names != future.names:
        raise ValueError("Walk-Forward und Abschlusspruefung haben unterschiedliche Quellen")
    everything = _concat(past, future)
    folds = [tuple(f) for f in final_folds]
    p, active, _ = stack_folds(everything, folds)
    # Kalibrierung und Isotonic-Entscheidung bleiben wie eingefroren
    wf_p, wf_active, _ = stack_folds(past, [tuple(f) for f in config["folds"][1:]])
    combined_p = np.r_[wf_p, p[len(past.date):]]
    combined_active = np.r_[wf_active, active[len(past.date):]]
    calibrated = calibrate_folds(combined_p, everything, combined_active, folds)
    final_p = combined_p.copy()
    for h, use in enumerate(config["use_isotonic"]):
        if use:
            final_p[:, h] = calibrated[:, h]
    mc_only = sigmoid(everything.base + everything.x[:, :, everything.names.index("monte carlo")])
    return everything, final_p, combined_active, mc_only, folds


def run_final(symbol, con=None, log=None, fresh=False):
    """Genau die eingefrorenen Einstellungen auf der unangetasteten Zeit. Das Ergebnis gilt, wie es kommt.

    fresh=True ist der Wochenlauf: Netze und Monte Carlo werden mit den neuen Kursen neu gerechnet, die Regeln bleiben eingefroren.
    """
    log = log or (lambda text: print(text, flush=True))
    symbol = symbol.upper()
    con = con or connect()
    path = CONFIG / f"matrix_{symbol}.json"
    if not path.exists():
        raise SystemExit(f"{symbol}: Erst 'matrix' laufen lassen, die Einstellungen muessen vor der Pruefung eingefroren sein")
    config = json.loads(path.read_text(encoding="utf-8"))
    if fresh:
        for old in OOS.glob(f"{symbol}_*_final.npz"):
            old.unlink()
    tic = time.perf_counter()
    target = load_ticker(con, symbol)
    final_folds, _ = train.holdout_folds(target)
    if not (OOS / f"{symbol}_{KINDS[0]}_solo_final.npz").exists():
        train.tournament(symbol, final=True, log=log)
    panel = risk.load_panel(con, symbol)
    last_day = int(target.date.max())
    final_path = OOS / f"{symbol}_mc_final.npz"
    if final_path.exists():
        with np.load(final_path) as data:
            mc_final = {key: data[key] for key in data.files}
    else:
        mc_final = risk.backtest(panel, config["holdout"], last_day + 1, log=log)
        np.savez(final_path, **mc_final)
    with np.load(OOS / f"{symbol}_mc.npz") as data:
        mc_past = {key: data[key] for key in data.files}
    everything, final_p, combined_active, mc_only, folds = stack_history(con, symbol, config, final_folds, mc_past, mc_final)
    is_holdout = everything.date >= config["holdout"]
    rows = direction_rows(final_p, everything, is_holdout, "Stack")
    rows += direction_rows(mc_only, everything, is_holdout, "Monte Carlo allein")
    frame = pd.DataFrame(rows)
    replace_rows(con, "matrix_holdout", symbol, frame)
    # Beide Pruefzeitraeume zusammen sagen mehr als jeder fuer sich
    together = pd.DataFrame(direction_rows(final_p, everything, combined_active, "Stack")
                            + direction_rows(mc_only, everything, combined_active, "Monte Carlo allein"))
    replace_rows(con, "matrix_gesamt", symbol, together)
    spans = risk.compare_with_models(symbol, mc_final, suffix="_final")
    # Spanne und VaR in der unangetasteten Zeit
    both_mc = merged_mc(symbol)
    bands = band_rows(both_mc, folds)
    var_tests = risk.evaluate_backtest(mc_final)
    replace_rows(con, "var_holdout", symbol, var_tests)
    reliability_rows = {name: reliability(final_p[is_holdout & everything.mask[:, h], h], everything.up[is_holdout & everything.mask[:, h], h],
                                          everything.date[is_holdout & everything.mask[:, h]] // HORIZON_DAYS[name])
                        for h, name in enumerate(HORIZON_NAMES)}
    log("Abschlusspruefung Stack: " + " ".join(f"{r['horizont']}={100 * r.get('brier_skill', np.nan):+.2f}%" for r in rows[:5]))

    # Die aktuelle Matrix: Gewichte aus allem, was heute bekannt ist
    today = last_day + 1
    _, _, weights_now = stack_folds(everything, [(today, today + 1)])
    w_now = weights_now[today]
    summary = pd.DataFrame(w_now, columns=everything.names, index=HORIZON_NAMES)
    current = current_matrix(con, symbol, panel, target, everything.names, w_now, frame, both_mc, config, log)
    replace_rows(con, "matrix_now", symbol, current)
    wf_frame = pd.read_sql_query("SELECT * FROM matrix_walk_forward WHERE symbol=?", con, params=(symbol,))
    report_path = write_report(con, symbol, wf_frame, summary, band_rows(mc_past, [tuple(f) for f in config["folds"]]), config,
                               holdout=(frame, bands, var_tests, reliability_rows, current, spans, together))
    log(f"Abschlusspruefung fertig nach {(time.perf_counter() - tic) / 60:.1f} min. Report: {report_path}")
    return frame


def stack_now(names, weights, base_up, mc_up, match_up, pattern, nets):
    """Ein Lauf des Stacks. Fehlende Quellen zaehlen als Basisrate. In der Matrix und im 5-Sekunden-Takt identisch."""
    base = logit(base_up)
    x = np.zeros((len(HORIZON_NAMES), len(names)))
    x[:, names.index("monte carlo")] = logit(mc_up) - base
    x[:, names.index("matching")] = np.where(np.isfinite(match_up), logit(match_up) - base, 0.0)
    x[:, names.index("muster")] = pattern
    for name, value in nets.items():
        x[:, names.index(name)] = value - base
    return sigmoid(base + (x * weights).sum(1))


def merged_mc(symbol):
    """Monte-Carlo-Backtest aus beiden Pruefzeitraeumen."""
    with np.load(OOS / f"{symbol}_mc.npz") as past, np.load(OOS / f"{symbol}_mc_final.npz") as final:
        return {key: (np.concatenate([past[key], final[key]]) if key != "engines" else past[key]) for key in past.files}


def current_matrix(con, symbol, panel, target, names, weights, holdout_frame, mc, config, log):
    """Die Matrix zum letzten Handelsschluss, mit Herkunft und Beleg je Horizont."""
    t = len(panel.dates) - 1
    state = risk.prepare(panel, t)
    dist = risk.distribution(risk.simulate_fhs(state, 1_000_000, seed=2026))
    torch.cuda.empty_cache()
    day = int(panel.dates[t])
    known = np.isfinite(target.y)
    base_now = np.array([(target.y[known[:, h], h] > 0).mean() for h in range(target.y.shape[1])])
    k = len(names)
    signal = match.daily_signals(con, symbol, np.array([day]))[0]
    pattern = pattern_signal(con, symbol, np.array([day]))[0]
    needed = sorted({names[j] for j in range(k) if names[j] not in ("monte carlo", "matching", "muster") and weights[:, j].max() > 1e-6})
    nets = {}
    if needed:
        cache = OOS / f"{symbol}_latest.npz"
        known_day = None
        if cache.exists():
            with np.load(cache) as data:
                known_day = int(data["day"])
                saved = {name: data[name] for name in data.files if name != "day"}
        if known_day != day or not set(needed) <= set(saved):
            log(f"Aktuelle Netz-Ausgaben fuer {needed}")
            live = train.latest_logits(symbol, [tuple(n.split()) for n in needed], log=log)
            saved = {name: live[tuple(name.split())] for name in needed}
            np.savez(cache, day=day, **saved)
        nets = {name: saved[name] for name in needed}
    p = stack_now(names, weights, base_now, dist["p_up"], signal, pattern, nets)
    fhs = list(mc["engines"]).index("FHS")
    i10, i50, i90, i95, i99 = (risk.LEVELS.index(q) for q in (0.1, 0.5, 0.9, 0.05, 0.01))
    rows = []
    var = pd.read_sql_query("SELECT * FROM var_backtest WHERE symbol=? AND verfahren='FHS'", con, params=(symbol,))
    walk_forward = pd.read_sql_query("SELECT * FROM matrix_walk_forward WHERE symbol=? AND quelle='Stack'", con, params=(symbol,))
    factors = []
    for h, name in enumerate(HORIZON_NAMES):
        real = mc["realized"][:, h].astype(float)
        past = np.isfinite(real)
        use = config["use_conformal"][h] and past.any()
        factor = conformal_factor(mc["q"][past, fhs, h, i10].astype(float), mc["q"][past, fhs, h, i90].astype(float), real[past]) if use else 0.0
        factors.append(factor)
        low, high = widen(dist["q"][h, i10], dist["q"][h, i90], factor)
        score = holdout_frame[(holdout_frame.quelle == "Stack") & (holdout_frame.horizont == name)].iloc[0]
        proven = direction_proven(walk_forward[walk_forward.horizont == name].iloc[0].to_dict(), score.to_dict())
        tested = var[(var.horizont == name) & (var.kennzahl == "VaR 95")]
        checked = bool(len(tested) and tested.testbar.iloc[0] == 1 and tested.bestanden.iloc[0] == 1)
        rows.append({"horizont": name, "stand": day, "p_bull": float(p[h]), "p_bear": float(1 - p[h]), "basisrate": float(base_now[h]), "beleg_richtung": proven,
                     "median": float(dist["q"][h, i50]), "spanne_von": float(low), "spanne_bis": float(high), "var95": float(-dist["q"][h, i95]), "var99": float(-dist["q"][h, i99]),
                     "cvar95": float(-dist["es"][h, 0]), "drawdown95": float(-dist["dd"][h, 0]), "risiko_geprueft": checked})
    # Alles, was der 5-Sekunden-Takt braucht, ohne den Stack neu zu lernen
    np.savez(OOS / f"{symbol}_now.npz", names=np.array(names, dtype=str), weights=weights, base_up=base_now, conformal=np.array(factors),
             proven=np.array([r["beleg_richtung"] for r in rows]), day=day)
    return pd.DataFrame(rows)


def refresh_now(symbol, con=None, log=None):
    """Nachtlauf: neue Kurse und frisch trainierte Netze, aber dieselben Stack-Gewichte und dieselben Regeln."""
    log = log or (lambda text: print(text, flush=True))
    symbol = symbol.upper()
    con = con or connect()
    config = json.loads((CONFIG / f"matrix_{symbol}.json").read_text(encoding="utf-8"))
    with np.load(OOS / f"{symbol}_now.npz") as data:
        names, weights = data["names"].tolist(), data["weights"]
    holdout_frame = pd.read_sql_query("SELECT * FROM matrix_holdout WHERE symbol=?", con, params=(symbol,))
    current = current_matrix(con, symbol, risk.load_panel(con, symbol), load_ticker(con, symbol), names, weights, holdout_frame, merged_mc(symbol), config, log)
    replace_rows(con, "matrix_now", symbol, current)
    return current


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def _skill(row):
    if row.get("n", 0) == 0 or pd.isna(row.get("brier_skill")):
        return "–"
    low, high = row["brier_low"], row["brier_high"]
    if pd.isna(low):
        return f"{100 * row['brier_skill']:+.2f} % (zu wenig Fälle)"
    mark = "**" if low > 1e-6 else ""
    return f"{mark}{100 * row['brier_skill']:+.2f} %{mark} ({100 * low:+.1f} bis {100 * high:+.1f})"


def _direction_table(frame):
    lines = ["| Quelle | " + " | ".join(HORIZON_NAMES) + " |", "|---|" + "---:|" * len(HORIZON_NAMES)]
    for source, g in frame.groupby("quelle", sort=False):
        by = {r["horizont"]: r for r in g.to_dict("records")}
        lines.append(f"| {source} | " + " | ".join(_skill(by[h]) for h in HORIZON_NAMES) + " |")
    stack = {r["horizont"]: r for r in frame[frame.quelle == "Stack"].to_dict("records")}
    cases = " | ".join(str(int(stack[h]["n_unabh"])) if stack[h].get("n", 0) and not pd.isna(stack[h].get("n_unabh")) else "–" for h in HORIZON_NAMES)
    lines += ["", "| Stack im Detail | " + " | ".join(HORIZON_NAMES) + " |", "|---|" + "---:|" * len(HORIZON_NAMES), f"| Unabhängige Fälle | {cases} |"]
    for key, title in (("p_mittel", "Ø angezeigte Bullish-Quote"), ("quote", "Tatsächlich gestiegen")):
        cells = " | ".join("–" if not stack[h].get("n", 0) else f"{100 * stack[h][key]:.1f} %" for h in HORIZON_NAMES)
        lines.append(f"| {title} | {cells} |")
    # Stimmt, was angezeigt wird? Mehr als die Zufallsstreuung bei dieser Fallzahl laesst sich nicht pruefen.
    spread, verdict = [], []
    for h in HORIZON_NAMES:
        r = stack[h]
        if not r.get("n", 0) or pd.isna(r.get("n_unabh")):
            spread.append("–"), verdict.append("–")
            continue
        limit = 2 * math.sqrt(max(r["quote"] * (1 - r["quote"]), 0.01) / max(r["n_unabh"], 1))
        spread.append(f"±{100 * limit:.1f} Pkt.")
        verdict.append("ja" if abs(r["p_mittel"] - r["quote"]) <= limit else "**nein**")
    lines += [f"| Zufallsstreuung bei dieser Fallzahl | {' | '.join(spread)} |", f"| Anzeige innerhalb der Streuung? | {' | '.join(verdict)} |"]
    for key, title in (("treffer", "Treffer Stack"), ("basis_treffer", "Treffer Basisrate")):
        cells = " | ".join("–" if not stack[h].get("n", 0) else f"{100 * stack[h][key]:.1f} %" for h in HORIZON_NAMES)
        lines.append(f"| {title} | {cells} |")
    return lines


def write_report(con, symbol, frame, weights, bands, config, holdout=None):
    REPORTS.mkdir(exist_ok=True)
    day = lambda d: pd.Timestamp(int(d), unit="D").date()
    folds = config["folds"]
    lines = [f"# {symbol}: Phase-5-Report", "", f"Stand {datetime.now():%Y-%m-%d %H:%M}. Statistische Auswertung der Kursgeschichte, keine Anlageberatung.", ""]
    if holdout:
        holdout_frame, holdout_bands, var_tests, reliability_rows, current, spans, together = holdout
        lines += ["## 1. Die Matrix heute", "", f"Stand: Handelsschluss {day(current.stand.iloc[0])}.", "",
                  "| Horizont | Bullish | Bearish | Basisrate | Richtung belegt? | Median | Spanne 80 % | VaR 95 | VaR 99 | Risiko geprüft? |",
                  "|---|---:|---:|---:|---|---:|---:|---:|---:|---|"]
        for r in current.to_dict("records"):
            lines.append(f"| {r['horizont']} | {r['p_bull']:.1%} | {r['p_bear']:.1%} | {r['basisrate']:.1%} | {'ja' if r['beleg_richtung'] else 'nein'} | {100 * r['median']:+.1f} % | "
                         f"{100 * r['spanne_von']:+.1f} bis {100 * r['spanne_bis']:+.1f} % | {100 * r['var95']:.1f} % | {100 * r['var99']:.1f} % | {'ja' if r['risiko_geprueft'] else 'nein'} |")
        lines += ["", "Richtung belegt heißt: Der Stack schlägt die Basisrate in Walk-Forward und Abschlussprüfung mit einem Intervall ganz über null. Diese Regel wurde nach dem ersten Blick auf die Abschlussprüfung verschärft: "
                  "Vorher genügte die Abschlussprüfung allein. Risiko geprüft heißt: FHS besteht den VaR-95-Backtest auf diesem Horizont.", ""]
        lines += ["## 2. Abschlussprüfung auf den unangetasteten 2 Jahren", "",
                  f"Zeitraum ab {day(config['holdout'])}. Die Modelleinstellungen wurden am {config['erstellt'][:10]} vor dieser Prüfung eingefroren und danach nicht verändert. Brier Skill gegen die Basisrate, in Klammern das 95 %-Intervall; fett, wenn es ganz über null liegt.", ""]
        lines += _direction_table(holdout_frame)
        lines += ["", "### Beide Prüfzeiträume zusammen", "", "Walk-Forward und Abschlussprüfung als durchgehender Test. Das ist die aussagekräftigste Zahl dieses Reports.", ""]
        lines += _direction_table(together)
        lines += ["", "### Stimmt, was angezeigt wird?", "", "Nur Abschlussprüfung. Bei wenigen unabhängigen Fällen ist die tatsächliche Quote stark zufallsabhängig.", ""]
        for name, rows in reliability_rows.items():
            if rows:
                lines += [f"**{name}**", "", "| Bereich | Fälle | Unabhängig | Angezeigt | Tatsächlich |", "|---|---:|---:|---:|---:|"]
                lines += [f"| {100 * r['von']:.0f}–{100 * r['bis']:.0f} % | {r['n']:,} | {r['unabhaengig']} | {r['angezeigt']:.1%} | {r['tatsaechlich']:.1%} |" for r in rows]
                lines.append("")
        if spans:
            lines += ["### Spanne gegen HAR und feste Werte in der Abschlussprüfung", "", "Pinball Skill. MC ist FHS; in Klammern das 95 %-Intervall, fett, wenn es ganz über null liegt.", "",
                      "| Horizont | Fälle | Unabhängig | MC gegen fest | HAR gegen fest | MC gegen HAR |", "|---|---:|---:|---:|---:|---:|"]
            for r in spans:
                lines.append(f"| {r['horizont']} | {r['n']:,} | {r['n_unabh']} | {risk._skill(r['gegen_fest'], r['fest_low'], r['fest_high'])} | {100 * r['har_gegen_fest']:+.2f} % | "
                             f"{risk._skill(r['gegen_har'], r['har_low'], r['har_high'])} |")
            lines.append("")
        lines += ["### Spanne und Risiko in der Abschlussprüfung", "", "| Horizont | Fälle | Unabhängig | 80 %-Spanne roh | mit Conformal | Breite roh | Breite Conformal |", "|---|---:|---:|---:|---:|---:|---:|"]
        lines += [f"| {r['horizont']} | {r['n']:,} | {r['unabhaengig']} | {r['roh']:.1%} | {r['conformal']:.1%} | {100 * r['breite_roh']:.1f} % | {100 * r['breite_conformal']:.1f} % |" for r in holdout_bands]
        lines += ["", "| Verfahren | Horizont | Kennzahl | Fälle | Erwartet | Treffer | Quote | p Kupiec | p Christoffersen | Ergebnis |", "|---|---|---|---:|---:|---:|---:|---:|---:|---|"]
        for r in var_tests[(var_tests.kennzahl != "Spanne 80") & (var_tests.verfahren == "FHS")].to_dict("records"):
            verdict = "zu wenig Fälle" if not r["testbar"] else ("bestanden" if r["bestanden"] else "**durchgefallen**")
            lines.append(f"| {r['verfahren']} | {r['horizont']} | {r['kennzahl']} | {r['n']:,} | {r['erwartet']:.1f} | {r['treffer']} | {r['quote']:.1%} | {r['p_kupiec']:.3f} | {r['p_christoffersen']:.3f} | {verdict} |")
        lines.append("")
    lines += [f"## {'3' if holdout else '1'}. Walk-Forward", "",
              f"Testjahre {day(folds[1][0])} bis {day(folds[-1][1])}. Das erste Jahr ab {day(folds[0][0])} dient nur zum Lernen der Gewichte. Für jedes Testjahr gilt: "
              "Gewichte nur aus Tagen, deren Ergebnis vorher feststand. Brier Skill gegen die Basisrate, in Klammern das 95 %-Intervall; fett, wenn es ganz über null liegt.", ""]
    lines += _direction_table(frame)
    use = dict(zip(HORIZON_NAMES, config["use_isotonic"]))
    use_band = dict(zip(HORIZON_NAMES, config["use_conformal"]))
    lines += ["", "Isotonic und Conformal werden nur genutzt, wo sie im Walk-Forward besser waren. Isotonic: " + (", ".join(k for k, v in use.items() if v) or "bei keinem Horizont")
              + ". Conformal: " + (", ".join(k for k, v in use_band.items() if v) or "bei keinem Horizont") + ".", ""]
    lines += ["### Gewichte im Stack", "", f"Abweichung von der Basisrate je Quelle. Strafe L2 = {config['l2']:g}, vorab festgelegt. 0 heißt: Diese Quelle hat beim Lernen nichts beigetragen.", "",
              "| Horizont | " + " | ".join(weights.columns) + " |", "|---|" + "---:|" * len(weights.columns)]
    for name, row in weights.iterrows():
        lines.append(f"| {name} | " + " | ".join(f"{v:.2f}" for v in row) + " |")
    lines += ["", "### 80 %-Spanne im Walk-Forward", "", "| Horizont | Fälle | Unabhängig | Roh | Mit Conformal | Breite roh | Breite Conformal |", "|---|---:|---:|---:|---:|---:|---:|"]
    lines += [f"| {r['horizont']} | {r['n']:,} | {r['unabhaengig']} | {r['roh']:.1%} | {r['conformal']:.1%} | {100 * r['breite_roh']:.1f} % | {100 * r['breite_conformal']:.1f} % |" for r in bands]
    lines += ["", f"## {'4' if holdout else '2'}. Deine Thesen für {symbol}", "", "| These | Messung | Urteil |", "|---|---|---|"]
    lines += [f"| {a} | {b} | {c} |" for a, b, c in setup.theses(symbol, con)]
    lines += [""] + setup.setup_lines(symbol, con)
    path = REPORTS / f"{symbol}_phase5.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
