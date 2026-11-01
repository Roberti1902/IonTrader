"""Historische Kurse laden und in alle Timeframes aggregieren."""
import os
import re

import numpy as np
import pandas as pd
import yfinance as yf

from .store import COLS, connect, load, save

NY = "America/New_York"
OPEN, CLOSE = 570, 960  # Handelszeit New York in Minuten seit Mitternacht
AGG = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
TIMEFRAMES = ["1m", "5m", "15m", "1h", "4h", "1D", "1W", "12D", "1M", "12W", "12M"]


def bar_end(start, minutes):
    """Bar-Ende aus Bar-Start; der letzte Bar des Tages endet spaetestens um 16:00."""
    ny = start.tz_convert(NY)
    close = ny.normalize() + pd.Timedelta(minutes=CLOSE)
    end = ny + pd.Timedelta(minutes=minutes)
    return end.where(end <= close, close)


def to_bar_ends(df, minutes):
    """Nur regulaere Handelszeit behalten und den Index vom Bar-Start aufs Bar-Ende umstellen."""
    ny = df.index.tz_convert(NY)
    mins = ny.hour * 60 + ny.minute
    df = df[(mins >= OPEN) & (mins < CLOSE)]
    df.index = bar_end(df.index, minutes)
    return df


def resample_intraday(df, minutes, now):
    """Intraday-Bars zusammenfassen. Raster startet taeglich um 9:30, laufende Bars fallen weg."""
    ny = df.index.tz_convert(NY)
    bar_mins = ny.hour * 60 + ny.minute
    end_mins = OPEN + ((bar_mins - OPEN - 1) // minutes + 1) * minutes
    end = ny.normalize() + pd.to_timedelta(np.minimum(end_mins, CLOSE), unit="min")
    out = df[COLS].groupby(end).agg(AGG)
    return out[out.index <= now]


def resample_calendar(df, freq, now):
    """Tagesbars zu Wochen ("W-FRI") oder Monaten ("M"). Offene Perioden fallen weg."""
    period = df.index.tz_convert(NY).tz_localize(None).to_period(freq)
    out = df[COLS].assign(ts=df.index).groupby(period).agg({**AGG, "ts": "last"})
    closed = out.index.end_time.tz_localize(NY) <= now
    return out[closed].set_index("ts")


def resample_count(df, n):
    """Je n Bars zu einem. Start am ersten Bar, damit alte Bars stabil bleiben; Rest faellt weg."""
    group = np.arange(len(df)) // n
    out = df[COLS].assign(ts=df.index).groupby(group).agg({**AGG, "ts": "last"})
    return out[np.bincount(group) == n].set_index("ts")


def _yahoo(symbol, interval, period):
    df = yf.Ticker(symbol).history(period=period, interval=interval, auto_adjust=True, actions=False)
    return df.rename(columns=str.lower)[COLS].dropna()


def yahoo_daily(symbol):
    df = _yahoo(symbol, "1d", "max")
    if df.empty:
        raise SystemExit(f"Keine Daten fuer {symbol}")
    # Tagesbar ist erst zum Boersenschluss bekannt
    df.index = df.index.tz_localize(None).normalize().tz_localize(NY) + pd.Timedelta(minutes=CLOSE)
    return df


def yahoo_intraday(symbol, interval, period, minutes):
    return to_bar_ends(_yahoo(symbol, interval, period), minutes)


def alpaca_bars(symbol, now, minutes=1):
    """Intraday-Bars seit 2016: Vollmarkt (SIP), bereinigt, nur regulaere Handelszeit."""
    from alpaca.data.enums import Adjustment
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

    client = StockHistoricalDataClient(os.environ["ALPACA_API_KEY"], os.environ["ALPACA_SECRET_KEY"])
    # Der freie Plan sperrt die letzten 15 Minuten der SIP-Historie
    bars = client.get_stock_bars(StockBarsRequest(
        symbol_or_symbols=symbol.replace("-", "."), timeframe=TimeFrame(minutes, TimeFrameUnit.Minute),
        adjustment=Adjustment.ALL, start=pd.Timestamp("2016-01-01", tz="UTC"), end=now - pd.Timedelta(minutes=16))).df
    return to_bar_ends(bars.droplevel("symbol")[COLS], minutes)


def clean_ticker(symbol):
    symbol = symbol.upper()
    if not re.fullmatch(r"\^?[A-Z0-9.\-]{1,10}", symbol):
        raise SystemExit(f"Ungueltiger Ticker: {symbol}")
    return symbol


def ingest_daily(symbol, con=None):
    """Tagesdaten und alles, was daraus entsteht. Fuer ETFs und Makro-Reihen im Graphen genuegt das."""
    symbol = clean_ticker(symbol)
    con = con or connect()
    now = pd.Timestamp.now(tz="UTC")
    daily = yahoo_daily(symbol)
    daily = daily[daily.index <= now]
    weekly, monthly = resample_calendar(daily, "W-FRI", now), resample_calendar(daily, "M", now)
    bars = {"1D": daily, "1W": weekly, "12D": resample_count(daily, 12), "1M": monthly,
            "12W": resample_count(weekly, 12), "12M": resample_count(monthly, 12)}
    for tf, df in bars.items():
        save(con, symbol, tf, df, "yahoo")


def ingest(symbol, con=None, base_minutes=1):
    """Immer Komplett-Refresh, denn Dividenden aendern auch alte bereinigte Kurse.

    base_minutes=5 spart beim Universum die 1m-Historie, die nur der Ziel-Ticker fuers Matching braucht.
    """
    # ponytail: Vollabruf je Ticker, auf inkrementell umstellen wenn das Universum gross wird
    symbol = clean_ticker(symbol)
    con = con or connect()
    now = pd.Timestamp.now(tz="UTC")
    ingest_daily(symbol, con)

    if os.environ.get("ALPACA_API_KEY") and not symbol.startswith("^"):
        source = "alpaca"
        base = alpaca_bars(symbol, now, base_minutes)
        m5, h1 = resample_intraday(base, 5, now), resample_intraday(base, 60, now)
        if base_minutes == 1:
            save(con, symbol, "1m", base, source)
    else:
        source = "yahoo"  # ohne Key: 5m nur rund 60 Tage, 1h rund 2 Jahre
        m5 = yahoo_intraday(symbol, "5m", "60d", 5)
        h1 = yahoo_intraday(symbol, "1h", "730d", 60)
        m5, h1 = m5[m5.index <= now], h1[h1.index <= now]
    for tf, df in {"5m": m5, "15m": resample_intraday(m5, 15, now), "1h": h1,
                   "4h": resample_intraday(h1, 240, now)}.items():
        save(con, symbol, tf, df, source)
    return source


def check(symbol, con=None):
    """Bericht: Umfang je Timeframe, unmoegliche Kerzen, Luecken, Abweichung zwischen den Quellen."""
    symbol = symbol.upper()
    con = con or connect()
    print(f"{symbol}: {'Timeframe':<9} {'Bars':>9}  {'von':<10}  {'bis':<16}  {'kaputt':>6}")
    for tf in TIMEFRAMES:
        df = load(con, symbol, tf)
        if df.empty:
            print(f"{symbol}: {tf:<9} {'-':>9}")
            continue
        tol = df.close * 1e-3
        bad = ((df.high < df[["open", "close"]].max(axis=1) - tol)
               | (df.low > df[["open", "close"]].min(axis=1) + tol)
               | (df[["open", "high", "low", "close"]] <= 0).any(axis=1)
               | (df.volume < 0)).sum()
        ny = df.index.tz_convert(NY)
        print(f"{symbol}: {tf:<9} {len(df):>9,}  {ny[0]:%Y-%m-%d}  {ny[-1]:%Y-%m-%d %H:%M}  {bad:>6}")

    daily, m5 = load(con, symbol, "1D"), load(con, symbol, "5m")
    if m5.empty or daily.empty:
        return
    day = m5.index.tz_convert(NY).normalize()
    by_day = m5.groupby(day).agg({"close": "last", "volume": "sum"})
    counts = m5.groupby(day).size()
    daily.index = daily.index.tz_convert(NY).normalize()
    both = by_day.join(daily, rsuffix="_d", how="inner")
    print(f"Handelstage mit 5m-Daten: {len(counts):,}, davon unter 70 von 78 Bars: {(counts < 70).sum()}")
    if len(both):
        close_gap = ((both.close / both.close_d - 1).abs()).median()
        volume_ratio = (both.volume / both.volume_d).median()
        print(f"5m gegen 1D: mediane Schlusskurs-Abweichung {close_gap:.3%}, Volumen-Verhaeltnis {volume_ratio:.2f}")
