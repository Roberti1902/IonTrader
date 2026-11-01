"""Phase 2: Indikatoren, Swings, Fibonacci, Muster, Fraktal und Mean Reversion fuer jeden Bar."""
import time

import ioncore
import numpy as np
import pandas as pd
import talib

from . import ROOT
from .ingest import TIMEFRAMES
from .store import connect, load, replace_rows

FEATURES = ROOT / "data" / "features"
KS = (1.5, 2.0, 3.0, 5.0, 8.0)  # Swing-Empfindlichkeit in ATR, auf jedem Timeframe dieselben Skalen
DFA_WINDOWS = (256, 1024, 4096)
MR_WINDOW = 256
PATTERNS = [
    "SKS", "Doppeltop", "Dreifachtop", "Absteigendes Dreieck", "Baerenflagge",
    "Baerischer Wimpel", "Baerischer Keil", "Baerisches Rechteck", "Inverse Tasse", "Rounding Top",
    "Inverse SKS", "Doppelboden", "Dreifachboden", "Aufsteigendes Dreieck", "Bullenflagge",
    "Bullischer Wimpel", "Bullischer Keil", "Bullisches Rechteck", "Tasse mit Henkel", "Rounding Bottom",
]


def _ratio(a, b):
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(b != 0, a / b, np.nan)


def indicators(df):
    """TA-Lib, alle Werte skalenfrei, damit Timeframes und Preisniveaus vergleichbar bleiben."""
    o, h, l, c, v = (df[col].to_numpy(dtype=float) for col in ("open", "high", "low", "close", "volume"))
    macd, macd_signal, macd_hist = talib.MACD(c)
    upper, middle, lower = talib.BBANDS(c, timeperiod=20)
    stoch_k, stoch_d = talib.STOCH(h, l, c)
    obv = talib.OBV(c, v)
    sma = {n: talib.SMA(c, n) for n in (20, 50, 200)}
    ema = {n: talib.EMA(c, n) for n in (20, 50, 200)}
    mom = np.full(len(c), np.nan)
    if len(c) > 252:
        mom[252:] = c[231:-21] / c[:-252] - 1  # 12-1-Momentum: letzter "Monat" zaehlt nicht mit
    out = {
        "rsi14": talib.RSI(c, 14),
        "macd": macd / c,
        "macd_signal": macd_signal / c,
        "macd_hist": macd_hist / c,
        "bb_pct": _ratio(c - lower, upper - lower),
        "bb_width": _ratio(upper - lower, middle),
        "adx14": talib.ADX(h, l, c, 14),
        "plus_di": talib.PLUS_DI(h, l, c, 14),
        "minus_di": talib.MINUS_DI(h, l, c, 14),
        "atr_pct": talib.ATR(h, l, c, 14) / c,
        "obv_z": _ratio(obv - talib.SMA(obv, 20), talib.STDDEV(obv, 20)),
        "mfi14": talib.MFI(h, l, c, v, 14),
        "stoch_k": stoch_k,
        "stoch_d": stoch_d,
        "roc10": talib.ROC(c, 10),
        "mom_12_1": mom,
        "zscore20": _ratio(c - sma[20], talib.STDDEV(c, 20)),
        "rel_volume": _ratio(v, talib.SMA(v, 20)),
        "sma50_200": sma[50] / sma[200] - 1,
    }
    out.update({f"sma{n}_d": c / ma - 1 for n, ma in sma.items()})
    out.update({f"ema{n}_d": c / ma - 1 for n, ma in ema.items()})
    return out


def compute(df, ks=KS, windows=DFA_WINDOWS):
    """Liefert (features, events) fuer einen Timeframe. Jede Zeile nutzt nur Daten bis zu ihrem Bar."""
    h, l, c = (df[col].to_numpy(dtype=float) for col in ("high", "low", "close"))
    cols = indicators(df)
    scans = ioncore.scan(h, l, c, list(ks))
    events = []
    for k, scan in zip(ks, scans):
        for name in ("fib_ret", "fib_dir", "fib_near", "fib_382", "fib_618", "leg_atr", "since", "trend"):
            cols[f"{name}_k{k:g}"] = scan[name]
        if len(scan["bar"]):
            events.append(pd.DataFrame({key: scan[key] for key in
                                        ("pattern", "bar", "start", "side", "entry", "sl", "tp")}).assign(k=k))

    returns = np.diff(np.log(c), prepend=np.log(c[0]))
    for w in windows:
        if len(c) >= 2 * w:
            fractal = ioncore.rolling_mfdfa(returns, w)
            cols[f"h2_{w}"], cols[f"dh_{w}"] = fractal["h2"], fractal["dh"]
            cols[f"h2abs_{w}"] = ioncore.rolling_mfdfa(np.abs(returns), w)["h2"]
    if len(c) > 2 * MR_WINDOW:
        cols.update(ioncore.rolling_mr(c, MR_WINDOW))

    features = pd.DataFrame(cols, index=df.index)
    events = pd.concat(events, ignore_index=True) if events else pd.DataFrame(
        columns=["pattern", "bar", "start", "side", "entry", "sl", "tp", "k"])
    if len(events):
        bar = events.bar.to_numpy(dtype=np.int64)
        # Zeitlimit: dreifache Musterdauer, mindestens 10 Bars
        max_bars = np.maximum(10, 3 * (bar - events.start.to_numpy(dtype=np.int64)))
        outcome = ioncore.triple_barrier(h, l, c, bar, events.side.to_numpy(dtype=np.int64),
                                         events.sl.to_numpy(dtype=float), events.tp.to_numpy(dtype=float), max_bars)
        events = events.assign(**outcome)
    return features, events


def feature_path(symbol, tf):
    # Windows trennt Dateinamen nicht nach Gross-/Kleinschreibung: 1M darf nicht auf 1m landen
    return FEATURES / f"{symbol}_{tf.replace('M', 'mo')}.npz"


def save_features(symbol, tf, features):
    FEATURES.mkdir(parents=True, exist_ok=True)
    np.savez(feature_path(symbol, tf), ts=features.index.as_unit("s").asi8,
             names=np.array(list(features.columns), dtype=str), x=features.to_numpy(dtype=np.float32))


def load_features(symbol, tf):
    with np.load(feature_path(symbol, tf)) as data:
        index = pd.to_datetime(data["ts"], unit="s", utc=True)
        return pd.DataFrame(data["x"], index=index, columns=data["names"].tolist())


def run(symbol, con=None):
    """Alle Timeframes durchrechnen, Features cachen, Ereignisse relational speichern."""
    symbol = symbol.upper()
    con = con or connect()
    threads = ioncore.threads()
    print(f"{symbol}: Scan auf {threads} CPU-Threads", flush=True)
    print(f"{'TF':<5} {'Bars':>10} {'Features':>9} {'Muster':>8} {'Sek.':>7} {'CPU':>5}", flush=True)
    all_events, total_wall, total_cpu = [], 0.0, 0.0
    for tf in TIMEFRAMES:
        df = load(con, symbol, tf)
        if df.empty:
            continue
        wall, cpu = time.perf_counter(), time.process_time()
        features, events = compute(df)
        wall, cpu = time.perf_counter() - wall, time.process_time() - cpu
        total_wall, total_cpu = total_wall + wall, total_cpu + cpu
        save_features(symbol, tf, features)
        if len(events):
            ts = df.index[events.bar.to_numpy(dtype=np.int64)].as_unit("s").asi8
            all_events.append(events.assign(timeframe=tf, ts=ts, name=[PATTERNS[p] for p in events.pattern]))
        print(f"{tf:<5} {len(df):>10,} {features.shape[1]:>9} {len(events):>8,} {wall:>7.1f} "
              f"{cpu / max(wall, 1e-9) / threads:>5.0%}", flush=True)
    if all_events:
        replace_rows(con, "events", symbol, pd.concat(all_events, ignore_index=True))
    return total_wall, total_cpu
