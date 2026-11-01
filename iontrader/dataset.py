"""Phase 3: Datensatz fuer die Modelle. Ein Fenster je Timeframe, zeitlich sauber ausgerichtet."""
from dataclasses import dataclass

import numpy as np
import pandas as pd
import torch

from .features import load_features
from .store import load
from .study import HORIZONS, forward_returns, naive_seconds

# Fensterlaenge je Timeframe in Bars: rund 1 Tag, 2 Tage, 10 Tage, 1 Monat, 6 Monate, 2 Jahre, 3 Jahre
INPUT = {"5m": 78, "15m": 52, "1h": 70, "4h": 60, "1D": 126, "1W": 104, "1M": 36}
HORIZON_NAMES = list(HORIZONS)
# Live gibt es Intraday-Vollmarktvolumen im freien Plan erst nach 15 Minuten: In Training und Live gleich verzoegern
VOLUME_COLS = ["obv_z", "mfi14", "rel_volume"]
VOLUME_LAG = {"5m": 4, "15m": 2, "1h": 1, "4h": 1}
PATTERN_COUNT = 20
HORIZON_DAYS = {"1T": 1, "7T": 7, "1M": 30, "6M": 182, "1J": 365}  # Kalendertage fuers Purging
HOLDOUT_DAYS = 730  # Die letzten 2 Jahre bleiben bis Phase 5 unangetastet
FOLD_DAYS, N_FOLDS = 365, 5  # Walk-Forward: 5 Testjahre, damit Crashs und Bullenmaerkte drin sind
SELECT_DAYS = 180  # Auswahlfenster fuers Stoppen, liegt vor dem Testjahr
RV_SPANS = (78, 390, 1638)  # rund 1 Tag, 1 Woche, 1 Monat in 5m-Bars


def tf_frame(con, symbol, tf, events):
    """Alle Eingaben eines Timeframes: Features, Kerzenform, Muster und beim 5m-Raster die Tageszeit."""
    bars, f = load(con, symbol, tf), load_features(symbol, tf)
    if len(bars) != len(f):
        raise ValueError(f"{symbol} {tf}: Features passen nicht zu den Bars, bitte neu scannen")
    o, h, l, c = (bars[col].to_numpy(dtype=float) for col in ("open", "high", "low", "close"))
    f = f.assign(ret=np.diff(np.log(c), prepend=np.log(c[0])), range=(h - l) / c, body=(c - o) / c)
    if tf in VOLUME_LAG:
        f[VOLUME_COLS] = f[VOLUME_COLS].shift(VOLUME_LAG[tf])
    hits = events[events.timeframe == tf]
    patterns = np.zeros((len(f), PATTERN_COUNT), dtype=np.float32)
    patterns[hits.bar.to_numpy(dtype=np.int64), hits.pattern.to_numpy(dtype=np.int64)] = 1
    f = pd.concat([f, pd.DataFrame(patterns, index=f.index, columns=[f"pat_{i}" for i in range(PATTERN_COUNT)])], axis=1)
    if tf == "5m":
        seconds = naive_seconds(f.index)
        angle = 2 * np.pi * (seconds % 86400) / 86400
        f = f.assign(time_sin=np.sin(angle), time_cos=np.cos(angle), weekday=((seconds // 86400 + 3) % 7).astype(float))
    return f


@dataclass
class Ticker:
    """Rohdaten eines Tickers. Alle Anker liegen auf dem Ende eines 5m-Bars."""
    symbol: str
    frames: dict  # tf -> (Bars, Features) float32
    columns: dict  # tf -> Spaltennamen
    ts: dict  # tf -> Bar-Ende in UTC-Sekunden
    pos: dict  # tf -> je Anker der letzte Bar, der zu diesem Zeitpunkt schon fertig ist
    date: np.ndarray  # Tag des Ankers
    label_end: np.ndarray  # (Anker, Horizonte) Tag, an dem die Zielgroesse bekannt wird
    y: np.ndarray  # (Anker, Horizonte) Log-Rendite, NaN wenn die Zukunft fehlt
    rv: np.ndarray  # (Anker, 3) Log der realisierten Schwankung ueber rund 1 Tag, 1 Woche, 1 Monat


def realized_vol(ret, spans=RV_SPANS):
    """HAR-Eingaben: realisierte Schwankung ueber die letzten Bars, je Bar nur aus der Vergangenheit."""
    squares = np.cumsum(np.r_[0.0, np.nan_to_num(ret.astype(float)) ** 2])
    out = []
    for span in spans:
        begin = np.maximum(np.arange(len(ret)) + 1 - span, 0)
        count = np.arange(len(ret)) + 1 - begin
        out.append(0.5 * np.log((squares[1:] - squares[begin]) / count * span + 1e-12))
    return np.stack(out, axis=1).astype(np.float32)


def load_ticker(con, symbol, columns=None, stride=1, windows=INPUT):
    events = pd.read_sql_query("SELECT timeframe, pattern, bar FROM events WHERE symbol=?", con, params=(symbol,))
    frames, cols, ts = {}, {}, {}
    for tf in windows:
        f = tf_frame(con, symbol, tf, events)
        if columns is not None:
            f = f.reindex(columns=columns[tf])
        frames[tf], cols[tf], ts[tf] = f.to_numpy(dtype=np.float32), list(f.columns), f.index.as_unit("s").asi8
    index = load(con, symbol, "5m").index
    fwd, day = forward_returns(con, symbol, "5m", index)
    calendar = naive_seconds(load(con, symbol, "1D").index) // 86400
    date = naive_seconds(index) // 86400
    y = np.stack([fwd[h] for h in HORIZON_NAMES], axis=1).astype(np.float32)
    label_end = np.stack([calendar[np.minimum(day + d, len(calendar) - 1)] for d in HORIZONS.values()], axis=1)
    pos = {tf: np.searchsorted(ts[tf], ts["5m"], side="right") - 1 for tf in windows}
    keep = np.flatnonzero(np.all([pos[tf] >= w - 1 for tf, w in windows.items()], axis=0))[::stride]
    rv = realized_vol(frames["5m"][:, cols["5m"].index("ret")])
    return Ticker(symbol, frames, cols, ts, {tf: p[keep] for tf, p in pos.items()}, date[keep], label_end[keep], y[keep], rv[keep])


def fold_dates(target, n_folds=N_FOLDS):
    """([(Beginn, Ende) je Testjahr], Beginn der unangetasteten Zeit) als Tage."""
    holdout = int(target.date.max()) - HOLDOUT_DAYS
    return [(holdout - (i + 1) * FOLD_DAYS, holdout - i * FOLD_DAYS) for i in reversed(range(n_folds))], holdout


def scale(frame, columns, ts, before):
    """Robuste Skalierung nur aus Daten vor dem ersten Testjahr. Muster bleiben 0/1, NaN wird zu 0."""
    train = frame[ts // 86400 < before]
    out = frame.copy()
    if len(train):
        for j, name in enumerate(columns):
            if name.startswith("pat_"):
                continue
            col = train[:, j]
            finite = col[np.isfinite(col)]
            if len(finite) == 0:
                out[:, j] = 0
                continue
            low, mid, high = np.quantile(finite, [0.25, 0.5, 0.75])
            spread = high - low if high > low else (finite.std() or 1.0)
            out[:, j] = np.clip((frame[:, j] - mid) / spread, -5, 5)
    return np.nan_to_num(out, nan=0.0, posinf=0.0, neginf=0.0)


class Bundle:
    """Alles liegt fertig skaliert auf der GPU, Batches entstehen dort per Index ohne CPU-Umweg."""

    def __init__(self, tickers, scale_before, holdout_start, windows=INPUT, horizon_days=None,
                 select_days=SELECT_DAYS, device="cuda"):
        self.windows, self.device, self.tfs = windows, device, list(windows)
        self.holdout_start, self.select_days = holdout_start, select_days
        self.horizon_days = list((horizon_days or HORIZON_DAYS).values())
        self.columns = tickers[0].columns
        self.back = {tf: torch.arange(w - 1, -1, -1, device=device) for tf, w in windows.items()}
        frames, positions, offset = {tf: [] for tf in self.tfs}, {tf: [] for tf in self.tfs}, {tf: 0 for tf in self.tfs}
        for t in tickers:
            for tf in self.tfs:
                frames[tf].append(scale(t.frames[tf], t.columns[tf], t.ts[tf], scale_before))
                positions[tf].append(t.pos[tf] + offset[tf])
                offset[tf] += len(t.frames[tf])
        self.x = {tf: torch.from_numpy(np.concatenate(frames[tf])).to(device) for tf in self.tfs}
        self.pos = {tf: torch.from_numpy(np.concatenate(positions[tf])).long().to(device) for tf in self.tfs}
        self.ticker_np = np.concatenate([np.full(len(t.y), i) for i, t in enumerate(tickers)])
        self.ticker = torch.from_numpy(self.ticker_np).long().to(device)
        self.y_np = np.concatenate([t.y for t in tickers])
        self.y = torch.from_numpy(np.nan_to_num(self.y_np)).float().to(device)
        self.date = np.concatenate([t.date for t in tickers])
        self.label_end = np.concatenate([t.label_end for t in tickers])
        self.rv = np.concatenate([t.rv for t in tickers])
        self.n_tickers = len(tickers)
        self.dims = {tf: self.x[tf].shape[1] for tf in self.tfs}

    def set_fold(self, start, end):
        """Masken und Basiswerte fuer ein Testjahr. Reihenfolge je Horizont: Training, Auswahl, Test, ohne Ueberlappung."""
        known = np.isfinite(self.y_np)
        length = np.array(self.horizon_days)
        select_end = start - length
        select_start = select_end - self.select_days
        date = self.date[:, None]
        first = self.ticker_np[:, None] == 0
        train = known & (self.label_end < select_start)
        select = known & first & (date >= select_start) & (date < select_end) & (self.label_end < start)
        test = known & first & (date >= start) & (date < end) & (self.label_end < self.holdout_start)
        # Basis: alles, was zu Beginn des Testjahrs schon bekannt war. Richtung = Basisrate,
        # Spanne = HAR-Schwankung aus letztem Tag, letzter Woche und letztem Monat mal feste Quantile
        known_then = known & (self.label_end < start)
        design = np.c_[np.ones(len(self.rv), dtype=np.float32), self.rv]
        scale_y = np.ones_like(self.y_np)
        ups, qs, fixed = [], [], []
        for tid in range(self.n_tickers):
            of = self.ticker_np == tid
            row_up, row_q, row_fixed = [], [], []
            for h in range(self.y_np.shape[1]):
                rows = of & known_then[:, h]
                r = self.y_np[rows, h]
                row_up.append(float((r > 0).mean()) if len(r) else 0.5)
                if len(r) < 50 or r.std() == 0:
                    row_q.append(np.array([-1.0, 0.0, 1.0]))
                    row_fixed.append(np.quantile(r, [0.1, 0.5, 0.9]) if len(r) else np.array([-1.0, 0.0, 1.0]))
                    continue
                beta = np.linalg.lstsq(design[rows], np.log(np.abs(r) + 1e-4), rcond=None)[0]
                predicted = np.exp(design[of] @ beta)
                z = r / predicted[rows[of]]
                scale_y[of, h] = predicted * z.std()
                row_q.append(np.quantile(z / z.std(), [0.1, 0.5, 0.9]))
                row_fixed.append(np.quantile(r, [0.1, 0.5, 0.9]))
            ups.append(row_up), qs.append(np.stack(row_q)), fixed.append(np.stack(row_fixed))
        tensor = lambda a: torch.from_numpy(a).to(self.device)
        self.mask_train, self.mask_select, self.mask_test = tensor(train), tensor(select), tensor(test)
        self.base_up = tensor(np.array(ups, dtype=np.float32))
        self.scale_y = tensor(scale_y.astype(np.float32))
        self.base_q = tensor(np.array(qs, dtype=np.float32))
        self.fixed_q = tensor(np.array(fixed, dtype=np.float32))

    def batch(self, idx):
        return {tf: self.x[tf][self.pos[tf][idx][:, None] - self.back[tf]] for tf in self.tfs}

    def train_idx(self, only_first=False):
        mask = self.mask_train.any(1)
        return torch.nonzero(mask & (self.ticker == 0) if only_first else mask).squeeze(1)

    def select_idx(self):
        return torch.nonzero(self.mask_select.any(1)).squeeze(1)

    def test_idx(self):
        return torch.nonzero(self.mask_test.any(1)).squeeze(1)
