"""Phase 10: Musterdepot. Monatserkennung, Einfrieren, Ausfuehrungstag und Fingerabdruck."""
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from iontrader.paper import STRATEGIES, evaluate, execution_position, fingerprint, freeze, latest_month_end, load_decisions, month_of, targets_from


def utc(*days):
    return pd.DatetimeIndex(pd.to_datetime(list(days), utc=True))


def rows(month, strategy="Kombination", symbols=("A", "B"), created="2026-11-01T12:00:00+00:00"):
    return pd.DataFrame([{"monat": month, "strategie": strategy, "aktie": s, "gewicht": 0.02, "signaltag": "2026-10-30", "erstellt": created} for s in symbols])


def test_month_end_counts_last_bar_only_when_its_month_is_over():
    days = utc("2026-09-29", "2026-09-30", "2026-10-01", "2026-10-30")
    assert latest_month_end(days, datetime(2026, 11, 1)) == 3
    assert latest_month_end(days, datetime(2026, 10, 30)) == 1, "Der Oktober laeuft noch"


def test_fingerprint_ignores_order_and_sees_any_change():
    a = fingerprint("2026-10", "Kombination", ["A", "B"])
    assert a == fingerprint("2026-10", "Kombination", ["B", "A"])
    assert a != fingerprint("2026-10", "Kombination", ["A", "C"])
    assert a != fingerprint("2026-11", "Kombination", ["A", "B"])


def test_frozen_month_is_never_changed_and_logged_once():
    con = sqlite3.connect(":memory:")
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "log.txt"
        assert freeze(con, rows("2026-10"), path) == [("2026-10", "Kombination")]
        assert freeze(con, rows("2026-10", symbols=("X", "Y")), path) == []
        assert sorted(load_decisions(con).aktie) == ["A", "B"]
        lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1 and fingerprint("2026-10", "Kombination", ["A", "B"]) in lines[0]


def test_execution_is_the_trading_day_after_creation():
    days = utc("2026-10-30", "2026-11-02", "2026-11-03")
    assert execution_position(days, "2026-11-01T12:00:00+00:00") == 1, "Sonntag: Montag"
    assert execution_position(days, "2026-11-02T22:30:00+00:00") == 2, "Montagabend: Dienstag"


def test_targets_skip_months_not_yet_executable_and_set_weights():
    days = utc("2026-10-29", "2026-10-30", "2026-11-02")
    decisions = pd.concat([rows("2026-09", created="2026-10-29T12:00:00+00:00"), rows("2026-10", created="2026-11-02T22:00:00+00:00")])
    out = targets_from(decisions, "Kombination", days, ["A", "B", "SPY"])
    assert list(out) == [0], out  # Nur September: gehandelt am 30.10., Schluessel ist der Tag davor
    assert out[0].tolist() == [0.02, 0.02, 0.0], out


def test_evaluation_waits_and_then_compares_on_the_same_window():
    days = utc("2026-10-30", "2026-11-02", "2026-11-03")
    columns = ["A", "SPY"]
    open_ = pd.DataFrame(100.0, index=days, columns=columns)
    close = open_.copy()
    close.iloc[-1] = [120.0, 110.0]
    rate = np.zeros(3)
    assert evaluate(load_decisions(sqlite3.connect(":memory:")), days, open_, close, rate).empty
    decisions = pd.concat([pd.DataFrame([{"monat": "2026-10", "strategie": name, "aktie": "A", "gewicht": 1.0, "signaltag": "2026-10-30", "erstellt": "2026-11-01T12:00:00+00:00"}]) for name in STRATEGIES])
    out = evaluate(decisions, days, open_, close, rate).set_index("strategie")
    assert out.loc["Kombination", "rendite"] > out.loc["Halten SPY", "rendite"] > 0, out
    assert out.seit.nunique() == 1 and out.loc["Kombination", "seit"] == "2026-11-02"


def test_month_label():
    assert month_of(pd.Timestamp("2026-03-31")) == "2026-03"


if __name__ == "__main__":
    tests = [f for name, f in list(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print("ok ", test.__name__, flush=True)
    print(f"{len(tests)} Tests bestanden", flush=True)
