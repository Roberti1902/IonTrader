"""Phase 6: Live-Motor mit drei Takten. Alle 5 Sekunden Monte Carlo und Stack, bei Bar-Schluss Scanner und Matching, nachts die Jobs."""
import threading
import time
from collections import deque
from dataclasses import replace
from datetime import datetime
from zoneinfo import ZoneInfo

import ioncore
import numpy as np
import pandas as pd
import talib
import torch

from . import features, ingest, live as feeds, logbook, match, pipeline, risk, setup
from .ingest import AGG, CLOSE, COLS, NY, OPEN, TIMEFRAMES, resample_intraday
from .matrix import HORIZON_NAMES, HORIZON_STEPS, PATTERN_DAYS, PATTERN_TFS, pattern_signal, stack_now, widen
from .store import connect, load
from .study import naive_seconds
from .train import OOS

TICK = 5.0
PATHS = 1_000_000
MIN_PATHS = 50_000
FAN_PATHS = 100_000
SEED = 2026  # Fest: Eine Aenderung der Anzeige kommt vom Kurs, nicht vom Zufall
HISTORY = 5000
FAN_LEVELS = (0.05, 0.1, 0.5, 0.9, 0.95)
MINUTES = {"1m": 1, "5m": 5, "15m": 15, "1h": 60, "4h": 240}
QUERY_WINDOW = 64
ANALOG_BARS = 32
FIB_K = 3.0  # Dieselbe Skala wie in der Ereignisstudie
FIB_LEVELS = (0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0, 1.272, 1.618)
SHOW_PATTERNS = 6
STALE_FEED = 300  # Sekunden ohne Trade mitten im Handel
_NY = ZoneInfo(NY)


def session_fraction(ts):
    """Anteil des Handelstags, der gelaufen ist. None ausserhalb der Handelszeit; Feiertage kennt nur der Feed."""
    t = datetime.fromtimestamp(ts, _NY)
    minute = t.hour * 60 + t.minute + t.second / 60
    if t.weekday() > 4 or not OPEN <= minute < CLOSE:
        return None
    return (minute - OPEN) / (CLOSE - OPEN)


def ny_day(ts):
    return datetime.fromtimestamp(ts, _NY).date()


def live_start_var(state, x, fraction):
    """Schwankung ab jetzt: GJR-Schritt mit dem heutigen Stand. Der noch offene Teil des Tages zaehlt mit seinem Erwartungswert.

    x ist die Log-Rendite seit dem letzten Schlusskurs, fraction der gelaufene Teil des Tages.
    """
    # ponytail: live kommt nur dieser Ticker, die Aufteilung auf Markt, Sektor und Eigenanteil ist der Erwartungswert. Mit Live-Kursen von SPY und Sektor-ETF waere sie genau.
    v, load_ = state.next_var.astype(float), state.load.astype(float)
    shock = load_ * v / (load_ ** 2 * v).sum() * x
    return state.omega + (state.alpha + state.gamma * (shock < 0)) * shock ** 2 + (state.alpha + state.gamma / 2) * (1 - fraction) * v + state.beta * v


def to_daily(minutes):
    ny = minutes.index.tz_convert(NY)
    out = minutes[COLS].groupby(ny.normalize()).agg(AGG)
    out.index = (out.index + pd.Timedelta(minutes=CLOSE)).tz_convert("UTC")
    return out


def merge_live(tf, closed, daily, minutes):
    """Fertige Bars plus das, was live dazukam. Der letzte Bar laeuft noch, solange seine Zeit nicht um ist."""
    if minutes.empty:
        return closed
    if tf == "1m":
        new = minutes[COLS]
    elif tf in MINUTES:
        new = resample_intraday(minutes, MINUTES[tf], minutes.index[-1] + pd.Timedelta(days=1))
        new.index = new.index.tz_convert("UTC")
    else:
        new = to_daily(minutes)
        if tf != "1D":  # Woche, Monat und Zaehl-Bars: alles seit dem letzten fertigen Bar
            rest = pd.concat([daily, new])
            rest = rest[rest.index > closed.index[-1]] if len(closed) else rest
            new = pd.DataFrame([{"open": rest.open.iloc[0], "high": rest.high.max(), "low": rest.low.min(), "close": rest.close.iloc[-1],
                                 "volume": rest.volume.sum()}], index=rest.index[-1:])
    return new if closed.empty else pd.concat([closed, new])


def base_rates(close):
    """Anteil positiver Renditen je Horizont, solange der Stack noch nicht gelernt ist."""
    logp = np.log(close)
    return np.array([(logp[s:] > logp[:-s]).mean() if len(logp) > s else 0.5 for s in HORIZON_STEPS])


class Live:
    """Ein Ticker im Live-Betrieb. Das Dashboard liest nur snapshot und frame, geschrieben wird im Motor-Thread."""

    def __init__(self, symbol, con, asof=None, with_index=True):
        self.symbol, self.asof, self.with_index = symbol, asof, with_index
        self.lock = threading.Lock()
        self.price, self.trade_ts = None, None
        self.minutes = []
        self.current = feeds.Bars5s(self.minutes.append, seconds=60)
        self.seen_bar = None
        self.n_paths = PATHS
        self.index = None
        self.match_up = np.full(len(HORIZON_NAMES), np.nan)
        self.match_n = 0
        self.tp_sl = None
        self.overlay_cache = {}
        self.snapshot = None
        self.load(con)

    # ----- Daten ---------------------------------------------------------------

    def load(self, con):
        s = self.symbol
        bars = {tf: load(con, s, tf) for tf in TIMEFRAMES}
        cut = bars["1D"].index[-1] if self.asof is None else min(bars["1D"].index[-1], self.asof)
        self.closed = {tf: df[df.index <= cut].tail(HISTORY) for tf, df in bars.items()}
        self.ref_close = float(self.closed["1D"].close.iloc[-1])
        with self.lock:  # Nach dem Nachtlauf stehen die heutigen Bars in der Datenbank, live wuerden sie doppelt zaehlen
            limit = cut.timestamp()
            self.minutes[:] = [m for m in self.minutes if m["start"] + 60 > limit]
            if self.current.bar and self.current.bar["start"] + 60 <= limit:
                self.current.bar = None
            if self.trade_ts is not None and self.trade_ts <= limit:
                self.price, self.trade_ts = None, None
        self.calendar = naive_seconds(bars["1D"].index) // 86400
        day = int(naive_seconds(self.closed["1D"].index[-1:])[0] // 86400)
        self.overlay_cache = {}
        self.live_events, self.last_event = {}, None  # Muster von gestern stehen nach dem Nachtlauf in der Datenbank

        # Stack: Gewichte und Regeln stammen aus der Matrix, die Netze aus dem letzten Nachtlauf
        self.stack, self.nets, self.nets_day = None, {}, None
        path = OOS / f"{s}_now.npz"
        if path.exists():
            with np.load(path) as data:
                self.stack = {key: data[key] for key in data.files}
            self.stack["names"] = self.stack["names"].tolist()
            latest = OOS / f"{s}_latest.npz"
            if latest.exists():
                with np.load(latest) as data:
                    self.nets = {key: data[key] for key in data.files if key != "day"}
                    self.nets_day = int(data["day"])
        self.base_up = self.stack["base_up"] if self.stack else base_rates(self.closed["1D"].close.to_numpy(dtype=float))
        self.pattern_past, self.pattern_close = 0.0, 0.0
        if self.stack:  # netto Muster der letzten Tage; laeuft ein Handelstag, ist er selbst der juengste dieser Tage
            signal = float(pattern_signal(con, s, np.array([day]), lookback=PATTERN_DAYS - 1)[0])
            self.pattern_past = 5 * signal / (1 - abs(signal))
            self.pattern_close = float(pattern_signal(con, s, np.array([day]))[0])

        # Risiko: geht schon, sobald der Graph den Ticker kennt
        self.state, self.risk_note = None, ""
        try:
            panel = risk.load_panel(con, s)
            self.state = risk.prepare(panel, int(np.searchsorted(panel.dates, day, side="right")) - 1)
        except (Exception, SystemExit) as error:  # Beim neuen Ticker normal: Der Graph entsteht erst im Hintergrund
            self.risk_note = str(error)

        # Was bisher gemessen wurde, steht neben der Anzeige
        self.track = {}
        if con.execute("SELECT 1 FROM sqlite_master WHERE name='matrix_gesamt'").fetchone():
            rows = pd.read_sql_query("SELECT horizont, p_mittel, quote, n_unabh FROM matrix_gesamt WHERE symbol=? AND quelle='Stack'", con, params=(s,))
            self.track = {r["horizont"]: r for r in rows.to_dict("records")}
        self.theses = setup.theses(s, con)
        var = setup._rows(con, "var_backtest", s)  # Fehlt ein Horizont hier, war er nicht testbar: zu wenige Zeitraeume
        tested = var[(var.verfahren == "FHS") & (var.kennzahl == "VaR 95") & (var.testbar == 1)] if len(var) else var
        self.var_tested = {r["horizont"]: r for r in tested.to_dict("records")}
        self.score = pd.DataFrame()
        if con.execute("SELECT 1 FROM sqlite_master WHERE name='forecast_score'").fetchone():
            self.score = pd.read_sql_query("SELECT * FROM forecast_score WHERE symbol=?", con, params=(s,))

        if self.with_index:
            threading.Thread(target=self._load_index, daemon=True).start()

    def _load_index(self):
        try:
            self.index = match.MatchIndex.from_db(connect(), self.symbol)
            self.seen_bar = None  # Sofort ein erstes Matching beim naechsten Takt
        except Exception as error:  # Das Dashboard laeuft auch ohne Matching
            self.risk_note = f"Matching nicht verfuegbar: {error}"

    def seed(self, frame):
        """Schliesst die Luecke zwischen Datenbank und Live-Feed mit fertigen 1m-Bars von heute."""
        frame = frame[frame.index > self.closed["1D"].index[-1]]
        if frame.empty:
            return
        with self.lock:
            self.minutes.extend({"start": int(t.timestamp()) - 60, "open": r.open, "high": r.high, "low": r.low, "close": r.close, "volume": r.volume}
                                for t, r in zip(frame.index, frame.itertuples()))
            self.price, self.trade_ts = float(frame.close.iloc[-1]), frame.index[-1].timestamp()
        earlier = frame[frame.index.tz_convert(NY).date < ny_day(self.trade_ts)]
        if len(earlier):  # Die Datenbank hinkt mehr als einen Tag hinterher
            self.ref_close = float(earlier.close.iloc[-1])

    def on_trade(self, ts, price, size):
        if session_fraction(ts) is None:  # Vor- und Nachboerse gehoeren nicht zu den Bars
            return
        with self.lock:
            self.price, self.trade_ts = price, ts
            self.current.add(ts, price, size)

    def live_minutes(self):
        with self.lock:
            rows = self.minutes + ([dict(self.current.bar)] if self.current.bar else [])
        if not rows:
            return pd.DataFrame(columns=COLS, index=pd.DatetimeIndex([], tz="UTC"), dtype=float)
        frame = pd.DataFrame(rows)
        frame.index = pd.to_datetime(frame.pop("start") + 60, unit="s", utc=True)
        # Die juengste Minute aus dem Rueckblick und der erste Live-Bar koennen dieselbe sein
        return frame[COLS].groupby(frame.index).agg(AGG) if frame.index.has_duplicates else frame[COLS]

    def frame(self, tf):
        return merge_live(tf, self.closed[tf], self.closed["1D"], self.live_minutes())

    # ----- Takt bei Bar-Schluss --------------------------------------------------

    def on_bar_close(self, now):
        """Fertige 5-Minuten-Bars: Scanner auf den Muster-Timeframes und Matching. Neue Pfade kommen ohnehin in jedem Takt."""
        today = pd.Timestamp(self.closed["1D"].index[-1])
        for tf in PATTERN_TFS:
            frame = self.frame(tf)
            frame = frame[frame.index.as_unit("s").asi8 <= now].tail(HISTORY)
            if len(frame) < 50:
                continue
            h, l, c = (frame[col].to_numpy(dtype=float) for col in ("high", "low", "close"))
            for scan in ioncore.scan(h, l, c, list(features.KS)):
                for i, bar in enumerate(scan["bar"]):
                    ts = frame.index[bar]
                    if ts > today:
                        event = (tf, int(scan["pattern"][i]), ts.value)
                        if event not in self.live_events:
                            self.last_event = {"tf": tf, "name": features.PATTERNS[event[1]], "side": int(scan["side"][i]), "entry": float(scan["entry"][i]),
                                               "sl": float(scan["sl"][i]), "tp": float(scan["tp"][i]), "ts": ts}
                        self.live_events[event] = int(scan["side"][i])
        frame = self.frame("5m")
        frame = frame[frame.index.as_unit("s").asi8 <= now]
        if self.index is not None and len(frame) >= QUERY_WINDOW:
            # Zeitpunkt ist der letzte fertige Bar, nicht die Uhr: Am Wochenende waere sonst der eigene Verlauf von Freitag ein Treffer
            last = frame.index[-1].timestamp()
            logp = np.log(frame.close.to_numpy(dtype=float)[-QUERY_WINDOW:])
            analogs = self.index.query(logp, int(last), QUERY_WINDOW * 5 * 60, k=200)
            summary = match.summarize(analogs, self._query_day(last))
            self.match_up = np.array([summary[h]["p_up"] if summary[h]["n"] >= 20 else np.nan for h in HORIZON_NAMES])
            self.match_n = int(max(summary[h]["n"] for h in HORIZON_NAMES))

    def _query_day(self, ts):
        day = pd.Timestamp(ny_day(ts)).value // 86_400_000_000_000
        return int(np.searchsorted(self.calendar, day))

    @property
    def pattern_now(self):
        if self.trade_ts is None:
            return self.pattern_close
        net = self.pattern_past + sum(self.live_events.values())
        return net / (abs(net) + 5)

    # ----- 5-Sekunden-Takt -------------------------------------------------------

    def tick(self, now):
        """Ein Takt: Monte Carlo ab dem aktuellen Kurs, dann der Stack. Liefert das, was ins Logbuch soll."""
        with self.lock:
            price, trade_ts = self.price, self.trade_ts
        fraction = session_fraction(now)
        traded_today = trade_ts is not None and ny_day(trade_ts) == ny_day(now)
        if price is None:
            price = self.ref_close
        x = float(np.log(price / self.ref_close))

        bar_key = int(now // 300) if fraction is not None or self.seen_bar is None else self.seen_bar
        if bar_key != self.seen_bar:
            self.seen_bar = bar_key
            self.on_bar_close(now)

        dist, fan = None, None
        if self.state is not None:
            state, start_var = self.state, None
            if traded_today:  # Der Sprung eines heutigen Termins steckt schon im Kurs, alle anderen ruecken einen Schritt naeher
                state = replace(state, earnings_steps=[s - 1 for s in state.earnings_steps if s > 0])
                start_var = live_start_var(self.state, x, 1.0 if fraction is None else fraction)
            try:
                paths = risk.simulate_fhs(state, self.n_paths, seed=SEED, start_var=start_var)
                dist = risk.distribution(paths)
                fan = self._fan(paths)
                self.tp_sl = self._tp_sl(paths, price)
                del paths
                torch.cuda.empty_cache()  # Ein paralleles Training soll den Speicher zwischen den Takten nutzen koennen
            except torch.cuda.OutOfMemoryError:  # Ein Training belegt die GPU: lieber weniger Pfade als gar keine
                torch.cuda.empty_cache()
                self.n_paths = max(self.n_paths // 2, MIN_PATHS)
                if self.snapshot:
                    dist, fan = self.snapshot["dist"], self.snapshot["fan"]

        if dist is not None:
            p = stack_now(self.stack["names"], self.stack["weights"], self.base_up, dist["p_up"], self.match_up, self.pattern_now, self.nets) if self.stack else self.base_up
        else:
            p = self.base_up
        rows = []
        for h, name in enumerate(HORIZON_NAMES):
            tested = self.var_tested.get(name)
            row = {"horizont": name, "p_bull": float(p[h]), "p_bear": float(1 - p[h]), "basisrate": float(self.base_up[h]),
                   "beleg": bool(self.stack["proven"][h]) if self.stack else False, "geprueft": bool(tested and tested["bestanden"]),
                   "var_quote": float(tested["quote"]) if tested and not tested["bestanden"] else None}
            if dist is not None:
                q = dist["q"][h]
                factor = float(self.stack["conformal"][h]) if self.stack else 0.0
                low, high = widen(q[risk.LEVELS.index(0.1)], q[risk.LEVELS.index(0.9)], factor)
                row |= {"mc_up": float(dist["p_up"][h]), "median": float(q[risk.LEVELS.index(0.5)]), "von": float(low), "bis": float(high), "var95": float(-q[risk.LEVELS.index(0.05)]),
                        "var99": float(-q[risk.LEVELS.index(0.01)]), "cvar95": float(-dist["es"][h, 0]), "drawdown95": float(-dist["dd"][h, 0]),
                        "mid_up": float(dist["mid_up"][h]), "mid_down": float(dist["mid_down"][h])}
            rows.append(row)
        self.snapshot = {"symbol": self.symbol, "now": now, "price": price, "ref_close": self.ref_close, "change": price / self.ref_close - 1, "fraction": fraction,
                         "traded_today": traded_today, "trade_ts": trade_ts, "rows": rows, "dist": dist, "fan": fan, "paths": self.n_paths if dist is not None else 0, "tp_sl": self.tp_sl}
        return rows if fraction is not None and traded_today else None

    @torch.inference_mode()
    def _fan(self, paths):
        """Quantile je Handelstag aus einer Stichprobe, in Log-Rendite. Der Chart rechnet sie auf den aktuellen Kurs um."""
        cum = paths[:FAN_PATHS].cumsum(1).sort(dim=0).values
        n = cum.shape[0]
        return np.stack([cum[min(n - 1, int(level * n))].cpu().numpy() for level in FAN_LEVELS])

    def _tp_sl(self, paths, price):
        """Das juengste Muster von heute: Was wird laut Monte Carlo zuerst erreicht, TP oder SL? Bis 1 Monat, zum Tagesschluss geprueft."""
        event = self.last_event
        if event is None:
            return None
        sample = paths[:FAN_PATHS]
        if event["side"] > 0:
            tp, sl = event["tp"] / price - 1, 1 - event["sl"] / price
        else:  # Im Spiegelbild ist der Kursrueckgang das Ziel
            sample, tp, sl = -sample, price / event["tp"] - 1, 1 - price / event["sl"]
        if tp <= 0 or sl <= 0:  # Der Kurs steht schon jenseits von TP oder SL
            return {**event, "p_tp": None}
        p_tp, p_sl, p_none = risk.p_tp_before_sl(sample, tp, sl, HORIZON_STEPS[2])
        return {**event, "p_tp": p_tp, "p_sl": p_sl, "p_keins": p_none}

    # ----- Overlays --------------------------------------------------------------

    def overlays(self, tf, now):
        """Bollinger, Fibonacci, Muster und Analogien. Nur aus fertigen Bars, deshalb einmal je Bar-Schluss des Timeframes."""
        frame = self.frame(tf)
        closed = frame[frame.index.as_unit("s").asi8 <= now]
        key = (tf, closed.index[-1].value if len(closed) else None, self.index is not None)
        cached = self.overlay_cache.get(key)
        if cached is not None:
            return cached
        out = {"bollinger": None, "fib": [], "patterns": [], "analogs": [], "regime": {}}
        if len(closed) >= 30:
            out["regime"] = self._regime(closed)
            h, l, c = (closed[col].to_numpy(dtype=float)[-HISTORY:] for col in ("high", "low", "close"))
            times = closed.index[-HISTORY:]
            upper, middle, lower = talib.BBANDS(c, timeperiod=20)
            out["bollinger"] = {"ts": times, "upper": upper, "middle": middle, "lower": lower}
            scans = dict(zip(features.KS, ioncore.scan(h, l, c, list(features.KS))))
            swings = scans[FIB_K]
            if len(swings["swing_price"]) >= 2:
                a, b = float(swings["swing_price"][-2]), float(swings["swing_price"][-1])
                start = times[swings["swing_bar"][-2]]
                out["fib"] = [{"level": level, "price": b - level * (b - a), "ts": start} for level in FIB_LEVELS]
            found = {}
            for k, scan in scans.items():  # Dasselbe Muster auf mehreren Skalen zaehlt einmal, die groesste gewinnt
                for i, bar in enumerate(scan["bar"]):
                    found[(int(scan["pattern"][i]), int(bar))] = {
                        "name": features.PATTERNS[int(scan["pattern"][i])], "k": k, "side": int(scan["side"][i]), "ts": times[bar], "start": times[scan["start"][i]],
                        "entry": float(scan["entry"][i]), "sl": float(scan["sl"][i]), "tp": float(scan["tp"][i]), "bar": int(bar)}
            out["patterns"] = sorted(found.values(), key=lambda e: e["bar"])[-SHOW_PATTERNS:]
            out["analogs"] = self._analogs(tf, closed, now)
        self.overlay_cache = {k: v for k, v in self.overlay_cache.items() if k[0] != tf}
        self.overlay_cache[key] = out
        return out

    def _regime(self, closed):
        """Mean Reversion, Momentum und Fraktal: an jedem fertigen Bar neu getestet, wie in der Ereignisstudie."""
        tail = closed.tail(3 * features.MR_WINDOW)
        out = {name: float(values[-1]) for name, values in features.indicators(tail).items()}
        c = tail.close.to_numpy(dtype=float)
        if len(c) > 2 * features.MR_WINDOW:
            mr = ioncore.rolling_mr(c, features.MR_WINDOW)
            out |= {key: float(mr[key][-1]) for key in ("adf", "half_life", "vr2")}
            out["hurst"] = float(ioncore.rolling_mfdfa(np.diff(np.log(c), prepend=np.log(c[0])), features.MR_WINDOW)["h2"][-1])
        return out

    def _analogs(self, tf, closed, now):
        """Die aehnlichsten fruehen Verlaeufe und was danach kam, auf die Schwankung des aktuellen Fensters skaliert."""
        index = self.index
        if index is None or tf not in match.MATCH_TFS or len(closed) < QUERY_WINDOW:
            return []
        logp = np.log(closed.close.to_numpy(dtype=float)[-QUERY_WINDOW:])
        analogs = index.query(logp, int(closed.index[-1].timestamp()), QUERY_WINDOW * match.TF_MINUTES[tf] * 60, k=50)
        spread = logp.std()
        out = []
        for a in analogs.itertuples():
            series = index.series[a.timeframe]
            bars = int(ANALOG_BARS * a.window / QUERY_WINDOW)
            end = int(a.bar) + bars
            if end >= len(series["logp"]) or series["ts"][end] > now:  # Was danach kam, muss heute schon bekannt sein
                continue
            window = series["logp"][int(a.bar) - int(a.window) + 1:int(a.bar) + 1]
            path = (series["logp"][int(a.bar):end + 1] - series["logp"][int(a.bar)]) * spread / max(window.std(), 1e-9)
            out.append({"steps": np.linspace(0, ANALOG_BARS, len(path)), "path": path, "label": f"{pd.Timestamp(int(a.ts), unit='s', tz='UTC').tz_convert(NY):%d.%m.%Y} · {a.timeframe}"})
            if len(out) == 5:
                break
        return out


class Engine:
    """Der Motor: haelt den 5-Sekunden-Takt, wechselt den Ticker und startet die Hintergrund-Jobs."""

    def __init__(self, replay_seconds=None):
        self.replay_seconds = replay_seconds
        self.live, self.wanted, self.error, self.feed = None, None, "", None
        self.periods = deque(maxlen=720)
        self.durations = deque(maxlen=720)
        self.steps, self.finished_key = pd.DataFrame(), None
        self.stop = threading.Event()
        self.replay_stop = threading.Event()

    def request(self, symbol):
        self.wanted = symbol.strip().upper()

    def start(self, symbol):
        self.request(symbol)
        threading.Thread(target=self._loop, daemon=True).start()

    def now(self, live_):
        if self.replay_seconds is None:
            return time.time()
        return live_.trade_ts or live_.closed["1D"].index[-1].timestamp()

    def _on_trade(self, symbol, ts, price, size):
        live_ = self.live
        if live_ is not None and live_.symbol == symbol:
            live_.on_trade(ts, price, size)

    def _activate(self, con):
        symbol = self.wanted
        self.error = ""
        try:
            ingest.clean_ticker(symbol)
            if load(con, symbol, "1D").empty:
                ingest.ingest_daily(symbol, con)
            asof = None
            minutes = None
            if self.replay_seconds is not None:
                # Wiedergabe: Der letzte Handelstag wird abgespielt und alles ab dann versteckt
                tf = "1m" if not load(con, symbol, "1m").empty else "5m"
                bars = load(con, symbol, tf)
                last_day = bars.index[-1].tz_convert(NY).normalize()
                minutes = bars[bars.index > last_day]
                asof = minutes.index[0] - pd.Timedelta(hours=1)
            self.replay_stop.set()
            self.live = Live(symbol, con, asof=asof)
            self.steps = pipeline.status(con, symbol)
            self.finished_key = None
            self.periods.clear(), self.durations.clear()
            if minutes is not None:
                self.replay_stop = threading.Event()
                threading.Thread(target=feeds.replay, args=(symbol, minutes, self._on_trade, self.replay_seconds, self.replay_stop), daemon=True).start()
            else:
                self._seed_today(self.live)
                if self.feed is None:
                    self.feed = feeds.open_feed(self._on_trade)
                self.feed.watch(symbol)
        except (Exception, SystemExit) as error:  # Ein falscher Ticker darf den laufenden nicht stoppen
            self.error = f"{symbol}: {error}"
            self.wanted = self.live.symbol if self.live else None

    def _seed_today(self, live_):
        """Was heute schon gehandelt wurde, bevor das Dashboard startete."""
        try:
            live_.seed(ingest.yahoo_intraday(live_.symbol, "1m", "5d", 1))
        except Exception as error:  # Ohne Rueckblick beginnt der Chart mit dem ersten Live-Trade
            self.error = f"Heutige Bars nicht geladen: {error}"

    def _check_feed(self, live_, now):
        """Schweigt der Alpaca-Feed mitten im Handel, uebernimmt Yahoo. Etwa wenn der freie Plan keine zweite Verbindung erlaubt."""
        if isinstance(self.feed, feeds.AlpacaFeed) and session_fraction(now) is not None and now - (live_.trade_ts or 0) > STALE_FEED:
            self.feed = feeds.YahooFeed(self._on_trade)
            self.feed.watch(live_.symbol)

    def _jobs(self, con, now):
        """Hintergrund-Jobs: neuer Ticker, Nacht- und Wochenlauf. Immer nur einer, in einem eigenen Prozess."""
        symbol = self.live.symbol
        self.steps = pipeline.status(con, symbol)
        finished = int(self.steps.ts[self.steps.status == "fertig"].sum())
        if self.finished_key is not None and finished != self.finished_key:  # Neue Kurse oder Modelle liegen bereit
            self.live.load(con)
        self.finished_key = finished
        if self.replay_seconds is not None:
            return
        self._check_feed(self.live, now)
        if pipeline.job_running():
            return
        job = pipeline.next_job(con, symbol, now)
        if job:
            pipeline.spawn(*job)

    def _loop(self):
        con = connect()
        next_tick = time.monotonic()
        previous = None
        next_jobs = 0.0
        while not self.stop.is_set():
            if self.wanted != (self.live.symbol if self.live else None):
                self._activate(con)
                previous, next_tick = None, time.monotonic()
            live_ = self.live
            started = time.monotonic()
            if previous is not None:
                self.periods.append(started - previous)
            previous = started
            if live_ is not None:
                try:
                    now = self.now(live_)
                    rows = live_.tick(now)
                    if rows and self.replay_seconds is None:
                        logbook.write(con, live_.symbol, now, live_.snapshot["price"], rows)
                except Exception as error:  # Ein einzelner Takt darf den Motor nicht stoppen
                    self.error = f"Takt: {error}"
                self.durations.append(time.monotonic() - started)
                if started >= next_jobs:
                    next_jobs = started + 60
                    try:
                        self._jobs(con, self.now(live_))
                    except Exception as error:
                        self.error = f"Jobs: {error}"
            next_tick = max(next_tick + TICK, time.monotonic())
            self.stop.wait(next_tick - time.monotonic())
