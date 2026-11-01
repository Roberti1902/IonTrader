"""Selbsttest Phase 1: python test_pipeline.py"""
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

from iontrader.ingest import NY, bar_end, resample_calendar, resample_count, resample_intraday, to_bar_ends
from iontrader.live import Bars5s
from iontrader.store import connect, load, save


def session_5m(day="2026-10-28"):
    """Ein Handelstag 5m: Bar-Enden 9:35 bis 16:00, close = laufende Nummer."""
    idx = pd.date_range(f"{day} 09:35", f"{day} 16:00", freq="5min", tz=NY)
    n = np.arange(1.0, len(idx) + 1)
    return pd.DataFrame({"open": n, "high": n + 0.5, "low": n - 0.5, "close": n, "volume": 10.0}, index=idx)


def daily(start="2026-09-01", end="2026-10-30"):
    idx = pd.bdate_range(start, end, tz=NY) + pd.Timedelta(hours=16)
    n = np.arange(1.0, len(idx) + 1)
    return pd.DataFrame({"open": n, "high": n + 0.5, "low": n - 0.5, "close": n, "volume": 10.0}, index=idx)


def test_bar_end_is_clipped_to_close():
    start = pd.DatetimeIndex(["2026-10-28 09:30", "2026-10-28 15:30"], tz=NY)
    end = bar_end(start, 60)
    assert [t.strftime("%H:%M") for t in end] == ["10:30", "16:00"]


def test_extended_hours_are_dropped_without_duplicates():
    idx = pd.date_range("2026-10-28 03:15", "2026-10-28 16:55", freq="5min", tz=NY)
    out = to_bar_ends(pd.DataFrame({"close": np.arange(len(idx))}, index=idx), 5)
    assert out.index.is_unique and len(out) == 78
    assert out.index[0].strftime("%H:%M") == "09:35" and out.index[-1].strftime("%H:%M") == "16:00"


def test_hourly_grid_and_values():
    df = session_5m()
    h1 = resample_intraday(df, 60, pd.Timestamp("2026-10-29", tz=NY))
    times = [t.tz_convert(NY).strftime("%H:%M") for t in h1.index]
    assert times == ["10:30", "11:30", "12:30", "13:30", "14:30", "15:30", "16:00"]
    first = h1.iloc[0]
    assert (first.open, first.close, first.high, first.low, first.volume) == (1, 12, 12.5, 0.5, 120)
    assert h1.volume.sum() == df.volume.sum()


def test_running_bar_is_dropped():
    now = pd.Timestamp("2026-10-28 11:00", tz=NY)
    df = session_5m()
    h1 = resample_intraday(df[df.index <= now], 60, now)
    assert [t.tz_convert(NY).strftime("%H:%M") for t in h1.index] == ["10:30"]


def test_no_lookahead_on_truncated_history():
    """Ein fertiger Bar darf sich nicht aendern, wenn spaetere Daten dazukommen."""
    df = session_5m()
    full = resample_intraday(df, 60, pd.Timestamp("2026-10-29", tz=NY))
    now = pd.Timestamp("2026-10-28 13:47", tz=NY)
    part = resample_intraday(df[df.index <= now], 60, now)
    assert len(part) == 4
    pd.testing.assert_frame_equal(part, full.iloc[:4], check_freq=False, check_names=False)


def test_open_week_and_month_are_dropped():
    df = daily()
    now = pd.Timestamp("2026-10-30 15:00", tz=NY)  # Freitag, Woche und Monat laufen noch
    df = df[df.index <= now]
    weekly = resample_calendar(df, "W-FRI", now)
    monthly = resample_calendar(df, "M", now)
    assert weekly.index[-1].tz_convert(NY).strftime("%Y-%m-%d") == "2026-10-23"
    assert monthly.index[-1].tz_convert(NY).strftime("%Y-%m-%d") == "2026-09-30"
    assert (weekly.index[1:] > weekly.index[:-1]).all()


def test_count_keeps_only_full_groups_and_stable_history():
    df = daily()
    twelve = resample_count(df, 12)
    assert len(twelve) == len(df) // 12
    assert twelve.iloc[0].volume == 120 and twelve.iloc[0].close == 12
    pd.testing.assert_frame_equal(resample_count(df.iloc[:30], 12), twelve.iloc[:2], check_freq=False, check_names=False)


def test_store_roundtrip_and_replace():
    with tempfile.TemporaryDirectory() as tmp:
        con = connect(Path(tmp) / "t.db")
        df = session_5m()
        save(con, "X", "5m", df, "test")
        save(con, "X", "5m", df.assign(close=99.0), "test")
        back = load(con, "X", "5m")
        assert len(back) == len(df) and (back.close == 99).all()
        assert back.index[0] == df.index[0]
        con.close()


def test_5s_bars():
    out = []
    bars = Bars5s(out.append)
    for ts, price, size in [(100.1, 10, 1), (102, 12, 2), (104.9, 9, 3), (105, 11, 4)]:
        bars.add(ts, price, size)
    assert out == [{"start": 100, "open": 10, "high": 12, "low": 9, "close": 9, "volume": 6}]
    assert bars.bar["start"] == 105


if __name__ == "__main__":
    tests = [f for name, f in list(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print("ok ", test.__name__)
    print(f"{len(tests)} Tests bestanden")
