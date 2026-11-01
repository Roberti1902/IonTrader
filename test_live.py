"""Selbsttest Phase 6: python test_live.py"""
import tempfile
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch

from iontrader import exit_now, live as feeds, logbook, match, matrix, pipeline, risk
from iontrader.app import card, chances
from iontrader.engine import Engine, Live, base_rates, live_start_var, merge_live, session_fraction
from iontrader.ingest import NY, resample_calendar, resample_count, resample_intraday
from iontrader.store import connect, load, save

pipeline.LOCK_PORT = 18052  # Ein echter Job darf parallel laufen


def ny(text):
    return pd.Timestamp(text, tz=NY).timestamp()


def walk(index, seed=1, start=100.0):
    rng = np.random.default_rng(seed)
    close = start * np.exp(np.cumsum(rng.normal(0, 0.001, len(index))))
    high, low = close * (1 + rng.uniform(0, 0.001, len(index))), close * (1 - rng.uniform(0, 0.001, len(index)))
    return pd.DataFrame({"open": np.r_[start, close[:-1]], "high": np.maximum(high, np.r_[start, close[:-1]]), "low": np.minimum(low, np.r_[start, close[:-1]]), "close": close, "volume": 100.0}, index=index)


def session(day, seed=1, start=100.0):
    return walk(pd.date_range(f"{day} 09:31", f"{day} 16:00", freq="1min", tz=NY).tz_convert("UTC"), seed, start)


def temp_db(symbol="TSTX"):
    """Zwei Jahre Tagesdaten, die letzten zwei Tage minutengenau. Letzter Tag 2026-10-30."""
    con = connect(Path(tempfile.mkdtemp()) / "t.db")
    days = pd.bdate_range("2024-10-01", "2026-10-30", tz=NY) + pd.Timedelta(hours=16)
    daily = walk(days.tz_convert("UTC"), 2)
    first, second = session("2026-10-29", 3), session("2026-10-30", 4, float(daily.close.iloc[-3]))
    minutes = pd.concat([first, second])
    now = days[-1] + pd.Timedelta(days=1)
    save(con, symbol, "1m", minutes, "test")
    for tf, m in (("5m", 5), ("15m", 15), ("1h", 60), ("4h", 240)):
        frame = resample_intraday(minutes, m, now)
        frame.index = frame.index.tz_convert("UTC")
        save(con, symbol, tf, frame, "test")
    weekly, monthly = resample_calendar(daily, "W-FRI", now), resample_calendar(daily, "M", now)
    for tf, frame in {"1D": daily, "1W": weekly, "12D": resample_count(daily, 12), "1M": monthly, "12W": resample_count(weekly, 12), "12M": resample_count(monthly, 12)}.items():
        save(con, symbol, tf, frame, "test")
    return con, symbol, second


def replayed(with_day=True):
    con, symbol, minutes = temp_db()
    asof = minutes.index[0] - pd.Timedelta(hours=1)
    live = Live(symbol, con, asof=asof, with_index=False)
    if with_day:
        feeds.replay(symbol, minutes, lambda _, ts, price, size: live.on_trade(ts, price, size), seconds_per_bar=0)
    return con, live, minutes


def test_session_fraction_knows_new_york():
    assert session_fraction(ny("2026-10-30 09:30:00")) == 0
    assert abs(session_fraction(ny("2026-10-30 12:45:00")) - 0.5) < 1e-9
    assert session_fraction(ny("2026-10-30 16:00:00")) is None
    assert session_fraction(ny("2026-10-30 09:29:59")) is None
    assert session_fraction(ny("2026-10-31 12:00:00")) is None  # Samstag
    assert session_fraction(ny("2026-11-02 09:30:00")) == 0  # Nach der Zeitumstellung gilt weiter New York


def test_replay_rebuilds_the_bars_of_the_day():
    _, live, minutes = replayed()
    now = minutes.index[-1] + pd.Timedelta(days=1)
    for tf, m in (("5m", 5), ("15m", 15), ("1h", 60), ("4h", 240)):
        want = resample_intraday(minutes, m, now)
        got = live.frame(tf).tail(len(want))
        for col in ("open", "high", "low", "close", "volume"):
            assert np.allclose(got[col].to_numpy(dtype=float), want[col].to_numpy(dtype=float)), (tf, col)
        assert (got.index == want.index.tz_convert("UTC")).all(), tf
    day = live.frame("1D").iloc[-1]
    assert abs(day.high - minutes.high.max()) < 1e-9 and abs(day.low - minutes.low.min()) < 1e-9 and abs(day.close - minutes.close.iloc[-1]) < 1e-9


def test_running_bar_is_partial_and_only_appended():
    _, live, minutes = replayed(with_day=False)
    before = {tf: live.frame(tf) for tf in ("5m", "1D", "1W", "12D", "1M", "12W", "12M")}
    part = minutes.iloc[:7]
    feeds.replay(live.symbol, part, lambda _, ts, price, size: live.on_trade(ts, price, size), seconds_per_bar=0)
    five = live.frame("5m")
    assert len(five) == len(before["5m"]) + 2  # 9:35 fertig, 9:40 laeuft
    assert abs(five.close.iloc[-1] - part.close.iloc[-1]) < 1e-9 and abs(five.high.iloc[-1] - part.high.iloc[5:].max()) < 1e-9
    for tf in ("1D", "1W", "12D", "1M", "12W", "12M"):
        frame = live.frame(tf)
        assert len(frame) == len(before[tf]) + 1, tf  # Alte Bars bleiben unberuehrt, genau ein laufender kommt dazu
        assert frame.iloc[:-1].equals(before[tf]), tf
        assert abs(frame.close.iloc[-1] - part.close.iloc[-1]) < 1e-9, tf
        assert frame.high.iloc[-1] >= part.high.max() - 1e-9, tf


def test_week_bar_contains_all_days_since_the_last_closed_week():
    con, symbol, minutes = temp_db()
    daily = load(con, symbol, "1D")
    weekly = load(con, symbol, "1W")
    cut = minutes.index[0] - pd.Timedelta(hours=1)
    closed_week = weekly[weekly.index <= cut]
    closed_days = daily[daily.index <= cut]
    frame = merge_live("1W", closed_week, closed_days, minutes)
    days_in_week = closed_days[closed_days.index > closed_week.index[-1]]
    assert abs(frame.open.iloc[-1] - days_in_week.open.iloc[0]) < 1e-9
    assert abs(frame.volume.iloc[-1] - (days_in_week.volume.sum() + minutes.volume.sum())) < 1e-6


def test_extended_hours_do_not_enter_the_bars():
    _, live, minutes = replayed(with_day=False)
    live.on_trade(ny("2026-10-30 08:00:00"), 999.0, 10)
    live.on_trade(ny("2026-10-30 17:00:00"), 999.0, 10)
    assert live.price is None and live.live_minutes().empty


def test_same_minute_from_lookback_and_feed_counts_once():
    _, live, minutes = replayed(with_day=False)
    live.seed(minutes.iloc[:3])
    last = minutes.index[2].timestamp()
    live.on_trade(last - 10, 123.0, 5)
    frame = live.live_minutes()
    assert len(frame) == 3 and frame.index.is_unique and frame.close.iloc[-1] == 123.0


def test_night_reload_drops_what_is_now_in_the_database():
    con, symbol, minutes = temp_db()
    live = Live(symbol, con, asof=minutes.index[0] - pd.Timedelta(hours=1), with_index=False)
    feeds.replay(symbol, minutes, lambda _, ts, price, size: live.on_trade(ts, price, size), seconds_per_bar=0)
    live.live_events[("5m", 0, 1)] = 1
    length = len(live.frame("5m"))
    live.asof = None  # Der Nachtlauf hat den Tag gespeichert
    live.load(con)
    assert live.live_minutes().empty and live.price is None and not live.live_events
    assert len(live.frame("5m")) == length  # Nichts doppelt, nichts fehlt


def test_overlays_never_see_the_running_bar():
    con, live, minutes = replayed()
    t = minutes.index[120].timestamp()
    _, early, _ = replayed(with_day=False)
    feeds.replay(early.symbol, minutes.iloc[:121], lambda _, ts, price, size: early.on_trade(ts, price, size), seconds_per_bar=0)
    for tf in ("5m", "15m"):
        a, b = live.overlays(tf, t), early.overlays(tf, t)
        assert [e["ts"] for e in a["patterns"]] == [e["ts"] for e in b["patterns"]], tf
        assert [round(f["price"], 8) for f in a["fib"]] == [round(f["price"], 8) for f in b["fib"]], tf
        assert a["bollinger"]["ts"][-1] == b["bollinger"]["ts"][-1], tf
        assert a["bollinger"]["ts"][-1].timestamp() <= t, tf
        assert np.allclose(a["bollinger"]["upper"][-5:], b["bollinger"]["upper"][-5:]), tf
        assert np.allclose(*zip(*((a["regime"][k], b["regime"][k]) for k in a["regime"])), equal_nan=True), tf


def manual_state():
    z = np.zeros((10, 3), dtype=np.float32)
    return risk.State(0.0, np.array([1.0, 0.5, 1.0], dtype=np.float32), np.full(3, 1e-5, dtype=np.float32), np.full(3, 0.05, dtype=np.float32), np.full(3, 0.1, dtype=np.float32),
                      np.full(3, 0.85, dtype=np.float32), np.array([1e-4, 5e-5, 2e-4], dtype=np.float32), np.full(3, 1e-3, dtype=np.float32), z, np.array([]), np.zeros(10), [])


def test_live_variance_reacts_to_todays_move():
    state = manual_state()
    total = lambda v: float((state.load.astype(float) ** 2 * v).sum())
    calm = live_start_var(state, 0.0, 0.0)
    expected = state.omega + (state.alpha + state.gamma / 2 + state.beta) * state.next_var
    assert np.allclose(calm, expected)  # Noch nichts passiert: ein normaler Schritt nach vorn
    down, up = live_start_var(state, -0.05, 0.5), live_start_var(state, 0.05, 0.5)
    assert total(down) > total(up) > total(live_start_var(state, 0.0, 0.5))  # Grosse Bewegung erhoeht, Rueckgang staerker
    # Tagesende: Der volle Schritt mit dem aufgeteilten Tagesergebnis, nichts Erwartetes mehr
    v = state.next_var.astype(float)
    shock = state.load * v / (state.load ** 2 * v).sum() * -0.02
    assert np.allclose(live_start_var(state, -0.02, 1.0), state.omega + (state.alpha + state.gamma) * shock ** 2 + state.beta * v)


def test_stack_now_is_base_rate_without_weight_and_uses_each_source():
    names = ["gru solo", "monte carlo", "matching", "muster"]
    base = np.full(5, 0.6)
    assert np.allclose(matrix.stack_now(names, np.zeros((5, 4)), base, np.full(5, 0.8), np.full(5, 0.8), 0.5, {"gru solo": np.full(5, 3.0)}), base)
    weights = np.zeros((5, 4))
    weights[:, 1] = 1
    assert np.allclose(matrix.stack_now(names, weights, base, np.full(5, 0.8), np.full(5, np.nan), 0.0, {}), 0.8)
    weights = np.zeros((5, 4))
    weights[:, 2] = 1
    assert np.allclose(matrix.stack_now(names, weights, base, base, np.full(5, np.nan), 0.0, {}), base)  # Ohne Analogien zaehlt Matching als Basisrate
    assert np.allclose(matrix.stack_now(names, weights, base, base, np.full(5, 0.7), 0.0, {}), 0.7)


def test_base_rates():
    close = np.exp(np.arange(600) * 0.01)
    assert (base_rates(close) == 1).all()
    assert base_rates(np.array([1.0, 2.0]))[4] == 0.5  # zu kurz: keine Aussage


def test_logbook_scores_only_what_is_due():
    con, symbol, minutes = temp_db()
    rows = [{"horizont": "1T", "p_bull": 0.9, "basisrate": 0.5, "von": -0.5, "bis": 0.5}, {"horizont": "1J", "p_bull": 0.5, "basisrate": 0.5, "von": -0.5, "bis": 0.5}]
    first = pd.Timestamp("2026-10-29 12:00", tz=NY).timestamp()
    logbook.write(con, symbol, first, 100.0, rows)
    logbook.write(con, symbol, first, 100.0, rows)  # Derselbe Takt zaehlt einmal
    logbook.write(con, symbol, pd.Timestamp("2026-10-30 12:00", tz=NY).timestamp(), 100.0, rows)
    score = logbook.score(con, symbol).set_index("horizont")
    assert score.prognosen["1T"] == 2 and score.faellig["1T"] == 1  # Vom 30.10. fehlt der Folgetag
    assert score.faellig["1J"] == 0 and score.prognosen["1J"] == 2
    m = load(con, symbol, "1m")
    start = m.close[m.index <= pd.Timestamp("2026-10-29 12:00", tz=NY)].iloc[-1]
    end = m.close[m.index <= pd.Timestamp("2026-10-30 12:00", tz=NY)].iloc[-1]
    assert score.tatsaechlich["1T"] == float(end > start)
    want = 1 - (0.9 - float(end > start)) ** 2 / (0.5 - float(end > start)) ** 2
    assert abs(score.brier_skill["1T"] - want) < 1e-9
    assert score.in_spanne["1T"] == 1


def test_pipeline_runs_steps_in_order_and_resumes():
    con = connect(Path(tempfile.mkdtemp()) / "t.db")
    calls = []
    fail = [True]

    def boom(symbol, _):
        calls.append("b")
        if fail[0]:
            raise RuntimeError("kaputt")

    steps = (("A", lambda s, c: calls.append("a")), ("B", boom), ("C", lambda s, c: calls.append("c")))
    assert pipeline.run("TSTX", steps, con) is False
    assert calls == ["a", "b"]  # Nach dem Fehler bleibt der Rest offen
    known = pipeline.status(con, "TSTX")
    assert known.status["A"] == "fertig" and known.status["B"] == "fehler" and "kaputt" in known.message["B"]
    assert pipeline.missing_steps(con, "TSTX") == []  # Ein Fehler startet nicht endlos neu
    fail[0] = False
    calls.clear()
    assert pipeline.run("TSTX", steps, con) is True
    assert calls == ["b", "c"]  # Fertiges wird uebersprungen
    calls.clear()
    assert pipeline.run("TSTX", steps[:1], con, repeat=True) is True and calls == ["a"]  # Nacht- und Wochenlauf wiederholen sich


def test_short_history_skips_the_nets_but_not_the_risk():
    con, symbol, _ = temp_db()
    assert not pipeline.enough_history(con, symbol)
    calls = []
    steps = (("Netze", lambda s, c: calls.append("netze")), ("Risiko", lambda s, c: calls.append("risiko")))
    assert pipeline.run(symbol, steps, con)
    assert calls == ["risiko"] and pipeline.status(con, symbol).status["Netze"] == "uebersprungen"


def test_only_one_job_at_a_time():
    lock = pipeline.job_lock()
    assert lock is not None and pipeline.job_lock() is None and pipeline.job_running()
    try:
        pipeline.run("TSTX", (), connect(Path(tempfile.mkdtemp()) / "t.db"))
        raise AssertionError("zweiter Job haette abbrechen muessen")
    except SystemExit:
        pass
    lock.close()
    assert not pipeline.job_running()


def test_night_job_is_due_once_per_session():
    con, symbol, _ = temp_db()
    for step, _ in pipeline.STEPS:
        pipeline.mark(con, symbol, step, "fertig")
    friday_night = ny("2026-10-30 20:00:00")
    assert pipeline.last_session_day(ny("2026-10-30 15:00:00")).date() == pd.Timestamp("2026-10-29").date()
    assert pipeline.last_session_day(friday_night).date() == pd.Timestamp("2026-10-30").date()
    assert pipeline.last_session_day(ny("2026-11-01 12:00:00")).date() == pd.Timestamp("2026-10-30").date()
    assert pipeline.next_job(con, symbol, friday_night) is None  # Daten vom 30.10. sind da
    monday_night = ny("2026-11-02 20:00:00")
    assert pipeline.next_job(con, symbol, monday_night) == ("nightly", symbol)
    pipeline.mark(con, symbol, pipeline.NIGHTLY, "fertig")
    con.execute("UPDATE pipeline SET ts=? WHERE step=?", (int(monday_night), pipeline.NIGHTLY))
    con.commit()
    assert pipeline.next_job(con, symbol, monday_night + 60) is None  # An Feiertagen bleiben die Daten alt, der Lauf kommt trotzdem nur einmal


def test_new_ticker_gets_the_pipeline():
    con, symbol, _ = temp_db()
    assert pipeline.next_job(con, symbol, ny("2026-10-30 20:00:00")) == ("pipeline", symbol)


def test_tick_survives_a_full_gpu():
    con, live, minutes = replayed()
    live.state = manual_state()
    real, calls = risk.simulate_fhs, []

    def full(*args, **kwargs):
        calls.append(1)
        raise torch.cuda.OutOfMemoryError("voll")

    risk.simulate_fhs = full
    try:
        live.tick(minutes.index[-1].timestamp())
    finally:
        risk.simulate_fhs = real
    assert calls and live.n_paths == 500_000 and live.snapshot is not None and live.snapshot["rows"][0]["p_bull"] == live.base_up[0]


def test_tp_before_sl_follows_the_side_of_the_pattern():
    _, live, _ = replayed(with_day=False)
    rising = torch.full((1000, 30), 0.01, device="cuda")
    live.last_event = {"side": 1, "tp": 110.0, "sl": 90.0}
    assert live._tp_sl(rising, 100.0)["p_tp"] == 1  # Long: Der Anstieg erreicht das Ziel
    live.last_event = {"side": -1, "tp": 90.0, "sl": 110.0}
    result = live._tp_sl(rising, 100.0)
    assert result["p_tp"] == 0 and result["p_sl"] == 1  # Short: Derselbe Anstieg trifft den Stop
    assert live._tp_sl(-rising, 100.0)["p_tp"] == 1
    live.last_event = {"side": 1, "tp": 95.0, "sl": 90.0}
    assert live._tp_sl(rising, 100.0)["p_tp"] is None  # Kurs steht schon ueber dem Ziel
    live.last_event = None
    assert live._tp_sl(rising, 100.0) is None


def test_card_tells_failed_risk_check_from_too_few_periods():
    con, live, _ = replayed(with_day=False)
    con.execute("CREATE TABLE var_backtest (symbol, verfahren, kennzahl, horizont, testbar, bestanden, quote)")
    with con:
        con.executemany("INSERT INTO var_backtest VALUES (?,?,?,?,?,?,?)", [(live.symbol, *row) for row in (("FHS", "VaR 95", "1T", 1, 0, 0.059), ("FHS", "VaR 95", "7T", 1, 1, 0.052),
                                                                                                            ("FHS", "VaR 95", "6M", 0, 1, 0.0), ("Block", "VaR 95", "1M", 1, 0, 0.03))])
    live.load(con)
    live.stack = {"proven": np.zeros(5, dtype=bool), "names": [], "weights": np.zeros((5, 0))}  # Mit Stack heisst ungeprueft: zu wenige Zeitraeume
    live.tick(live.closed["1D"].index[-1].timestamp() + 3600)
    text = {row["horizont"]: repr(card(live, live.snapshot, row)) for row in live.snapshot["rows"]}
    assert "durchgefallen" in text["1T"] and "5,9" in text["1T"], text["1T"]
    assert "bestanden" in text["7T"], text["7T"]
    assert "zu wenige" in text["6M"] and "zu wenige" in text["1M"]  # 6M nicht testbar, 1M nur vom Block-Verfahren getestet


def test_chance_tiles_work_with_and_without_monte_carlo():
    row = {"horizont": "7T", "p_bull": 0.586, "basisrate": 0.589}
    plain = repr(chances({"rows": [row]}))
    assert "In 7 Tagen" in plain and "59 %" in plain and "Typischer Fall" not in plain  # Neuer Ticker: nur die Basisrate
    full = repr(chances({"rows": [row | {"median": 0.007, "mid_up": 0.05, "mid_down": -0.04}]}))
    assert "+0,7 %" in full and "+5,0 %" in full and "-4,0 %" in full


def test_dashboard_shows_the_final_check_numbers_when_nothing_moved():
    """Der 5-Sekunden-Takt rechnet bei ruhendem Kurs exakt dieselbe Matrix wie die Abschlusspruefung."""
    con = connect()
    if not con.execute("SELECT 1 FROM sqlite_master WHERE name='matrix_now'").fetchone():
        return
    saved = pd.read_sql_query("SELECT * FROM matrix_now WHERE symbol='META'", con)
    if saved.empty:
        return
    live = Live("META", con, with_index=False)
    live.index = match.MatchIndex.from_db(con, "META")
    now = live.closed["1D"].index[-1].timestamp() + 3600
    if int(saved.stand.iloc[0]) != int(pd.Timestamp(live.closed["1D"].index[-1].tz_convert(NY).date()).value // 86_400_000_000_000):
        return
    live.tick(now)
    for row, want in zip(live.snapshot["rows"], saved.to_dict("records")):
        name = row["horizont"]
        assert abs(row["p_bull"] - want["p_bull"]) < 1e-3, (name, row["p_bull"], want["p_bull"])
        assert abs(row["von"] - want["spanne_von"]) < 1e-3 and abs(row["bis"] - want["spanne_bis"]) < 1e-3, name
        assert abs(row["var95"] - want["var95"]) < 1e-3 and abs(row["var99"] - want["var99"]) < 1e-3, name
        assert bool(row["beleg"]) == bool(want["beleg_richtung"]) and bool(row["geprueft"]) == bool(want["risiko_geprueft"]), name
    del live
    torch.cuda.empty_cache()


def test_engine_holds_the_clock_with_a_bar_close_in_every_tick():
    """Haertefall: 1 Minute je Sekunde, also bei jedem Takt ein 5-Minuten-Schluss. 1 Mio. Pfade laufen trotzdem jedes Mal."""
    con = connect()
    if load(con, "META", "1m").empty:
        return
    engine = Engine(replay_seconds=1.0)
    engine.start("META")
    deadline = time.monotonic() + 180
    while len(engine.periods) < 6 and time.monotonic() < deadline:
        time.sleep(1)
    engine.stop.set()
    engine.replay_stop.set()
    periods, durations = np.array(engine.periods), np.array(engine.durations)
    assert len(periods) >= 6 and not engine.error, (len(periods), engine.error)
    assert np.abs(periods[1:] - 5).max() < 0.5, periods
    print(f"    Takt: Ø {periods.mean():.2f} s, Rechenzeit Ø {1000 * durations.mean():.0f} ms, laengste {1000 * durations.max():.0f} ms", flush=True)
    assert engine.live.snapshot["paths"] == 1_000_000
    del engine
    torch.cuda.empty_cache()


def test_backtest_panel_handles_missing_and_reference_rows():
    from types import SimpleNamespace
    from iontrader.app import backtest_panel
    from iontrader.snapshot import to_html

    assert "noch nicht gerechnet" in to_html(backtest_panel(SimpleNamespace(backtest=pd.DataFrame())))
    base = {"rendite": 0.1, "nach_steuer": 0.08, "sharpe": 0.5, "drawdown": -0.3, "investiert": 1.0, "orders": 2}
    frame = pd.DataFrame([{"strategie": "Halten Aktie", **base, "rendite_p": np.nan, "rendite_belegt": 0, "sharpe_belegt": 0},
                          {"strategie": "Volatilitaet", **base, "rendite_p": 0.5, "rendite_belegt": 0, "sharpe_belegt": 1}])
    out = to_html(backtest_panel(SimpleNamespace(backtest=frame)))
    assert "Volatilität" in out and "<td>Sharpe</td>" in out and "<td>–</td>" in out, out


def test_ranking_panel_hides_single_stocks_on_the_public_page():
    from types import SimpleNamespace
    from iontrader.app import ranking_panel
    from iontrader.snapshot import to_html

    assert "python main.py rank" in to_html(ranking_panel(SimpleNamespace(rank_result=pd.DataFrame())))
    result = pd.DataFrame([{"strategie": "Momentum 12-1", "rendite": 0.1, "nach_steuer": 0.08, "sharpe": 0.5, "drawdown": -0.3, "klein": np.nan}])
    today = pd.DataFrame([{"aktie": "ZZZZ", "faktor": "Umkehr", "rang": 1, "von": 500, "stand": "2026-10-30"}])
    live = SimpleNamespace(rank_result=result, rank_test=pd.DataFrame({"belegt": [0], "strategie": ["Momentum 12-1"]}), rank_today=today, symbol="ZZZZ")
    private, public = to_html(ranking_panel(live)), to_html(ranking_panel(live, public=True))
    assert "ZZZZ" in private and "Rang 1 von 500" in private and "Keine Strategie" in private, private
    assert "ZZZZ" not in public and "Momentum" in public, public


def test_snapshot_writes_escaped_html_from_dash_parts():
    from dash import html
    from iontrader.snapshot import to_html

    out = to_html([html.Div([html.Span("<b> & 5"), None, 7], className="card", style={"width": "50%"}, title='a"b')])
    assert out == '<div class="card" title="a&quot;b" style="width: 50%"><span>&lt;b&gt; &amp; 5</span>7</div>', out


if __name__ == "__main__":
    tests =[f for name, f in list(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print("ok ", test.__name__, flush=True)
    print(f"{len(tests)} Tests bestanden", flush=True)
    exit_now()
