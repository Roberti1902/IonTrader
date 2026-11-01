"""Selbsttest Phase 4: python test_risk.py"""
import math
import sqlite3
import tempfile
import time
from pathlib import Path

import ioncore
import numpy as np
import pandas as pd
import torch

from iontrader import exit_now
from iontrader.graph import MARKET, PROXY, edges_at, ensure, factor_table, neighbors, reachable, write
from iontrader.risk import (LEVELS, Panel, State, christoffersen, distribution, earnings_steps, kupiec, market_replay, p_tp_before_sl,
                            prepare, reaction_days, simulate_block, simulate_fhs, var_tests, worst_episodes)


def gjr_series(n, alpha, gamma, beta, seed=1, sigma=0.01):
    rng = np.random.default_rng(seed)
    omega = sigma ** 2 * (1 - alpha - gamma / 2 - beta)
    s2, out = sigma ** 2, np.zeros(n)
    for t in range(n):
        out[t] = math.sqrt(s2) * rng.standard_normal()
        s2 = omega + (alpha + (gamma if out[t] < 0 else 0)) * out[t] ** 2 + beta * s2
    return out


def test_gjr_recovers_known_parameters():
    fit = ioncore.gjr_fit(gjr_series(30000, 0.04, 0.10, 0.88))
    print(f"    alpha {fit['alpha']:.3f} (0.04), gamma {fit['gamma']:.3f} (0.10), beta {fit['beta']:.3f} (0.88)")
    assert abs(fit["alpha"] - 0.04) < 0.02 and abs(fit["gamma"] - 0.10) < 0.03 and abs(fit["beta"] - 0.88) < 0.03
    assert abs(fit["z"].std() - 1) < 0.03
    assert fit["alpha"] + fit["gamma"] / 2 + fit["beta"] < 1


def test_gjr_handles_bad_input():
    flat = ioncore.gjr_fit(np.full(200, 0.001))
    assert flat["next_var"] == 0 and (flat["z"] == 0).all()
    for bad in (np.r_[np.zeros(100), np.nan], np.r_[np.zeros(100), np.inf], np.zeros(10)):
        try:
            ioncore.gjr_fit(bad)
        except ValueError:
            continue
        raise AssertionError("ungueltige Eingabe wurde akzeptiert")


def manual_state(sigma=0.01, alpha=0.0, gamma=0.0, beta=0.0, z=None, load=(0.0, 0.0, 1.0), jumps=(), steps=(), raw=None, mu=0.0, seed=2):
    rng = np.random.default_rng(seed)
    z = rng.standard_normal((200_000, 3)).astype(np.float32) if z is None else z
    z = (z - z.mean(0)) / z.std(0)
    a = np.full(3, alpha, dtype=np.float32)
    g = np.full(3, gamma, dtype=np.float32)
    b = np.full(3, beta, dtype=np.float32)
    var = np.full(3, sigma ** 2, dtype=np.float32)
    return State(mu, np.array(load, dtype=np.float32), var * (1 - a - g / 2 - b), a, g, b, var, var * 9, z,
                 np.array(jumps, dtype=np.float32), np.zeros(100, dtype=np.float32) if raw is None else raw.astype(np.float32), list(steps))


def test_var_matches_the_normal_formula():
    result = distribution(simulate_fhs(manual_state(), 1_000_000, n_steps=25), steps=(1, 25))
    var95_1, var99_25 = -result["q"][0, LEVELS.index(0.05)], -result["q"][1, LEVELS.index(0.01)]
    assert abs(var95_1 - 0.01 * 1.645) < 3e-4, var95_1
    assert abs(var99_25 - (1 - math.exp(-0.05 * 2.326))) < 2e-3, var99_25
    es95 = -result["es"][0, 0]
    assert abs(es95 - 0.01 * 2.063) < 4e-4, es95  # Expected Shortfall der Normalverteilung
    assert abs(result["p_up"][0] - 0.5) < 0.002


def test_volatility_clusters_and_decays():
    state = manual_state(alpha=0.05, gamma=0.0, beta=0.9)
    calm = distribution(simulate_fhs(state, 200_000, n_steps=5, start_var=np.full(3, 1e-5)), steps=(1, 5))
    wild = distribution(simulate_fhs(state, 200_000, n_steps=5, start_var=np.full(3, 1e-3)), steps=(1, 5))
    assert -wild["q"][0, LEVELS.index(0.01)] > 5 * -calm["q"][0, LEVELS.index(0.01)]
    # Schwankung kehrt zum Mittel zurueck: Aus hoher Lage faellt die Tages-Schwankung ueber 200 Schritte
    long = simulate_fhs(state, 100_000, n_steps=200, start_var=np.full(3, 1e-3))
    assert long[:, -1].std() < 0.5 * long[:, 0].std()


def test_negative_shocks_raise_volatility_more():
    plain = simulate_fhs(manual_state(alpha=0.05, gamma=0.0, beta=0.9), 200_000, n_steps=2)
    leveraged = simulate_fhs(manual_state(alpha=0.0, gamma=0.1, beta=0.9), 200_000, n_steps=2)
    # Theorie: Varianz nach einem Minus 1,05e-4, nach einem Plus 0,95e-4, also rund 5 % mehr Schwankung
    falling = leveraged[:, 0] < 0
    ratio = (leveraged[falling, 1].std() / leveraged[~falling, 1].std()).item()
    assert abs(ratio - math.sqrt(1.05 / 0.95)) < 0.015, ratio
    falling = plain[:, 0] < 0
    assert abs(plain[falling, 1].std() / plain[~falling, 1].std() - 1) < 0.015


def test_factors_are_drawn_jointly():
    rng = np.random.default_rng(3)
    common = rng.standard_normal(100_000).astype(np.float32)
    together = np.c_[common, rng.standard_normal(100_000), common].astype(np.float32)
    apart = np.c_[common, rng.standard_normal(100_000), rng.permutation(common)].astype(np.float32)
    load = (1.0, 0.0, 1.0)
    var_together = simulate_fhs(manual_state(z=together, load=load), 200_000, n_steps=1).var().item()
    var_apart = simulate_fhs(manual_state(z=apart, load=load), 200_000, n_steps=1).var().item()
    assert abs(var_together / (4 * 0.01 ** 2) - 1) < 0.03  # Gleichlauf: Summe schwankt doppelt
    assert abs(var_apart / (2 * 0.01 ** 2) - 1) < 0.03


def test_earnings_jump_hits_only_its_step():
    state = manual_state(jumps=(-0.2, 0.2), steps=(2,))
    paths = simulate_fhs(state, 200_000, n_steps=5)
    assert paths[:, 2].abs().min() > 0.19  # Der Sprung ersetzt den Eigenanteil
    assert paths[:, 0].std() < 0.011 and paths[:, 3].std() < 0.011


def test_block_bootstrap_keeps_memory():
    rng = np.random.default_rng(4)
    trending = np.repeat(rng.choice([-0.01, 0.01], 500), 21)
    block = simulate_block(manual_state(raw=trending), 100_000, n_steps=21, length=21)
    iid = simulate_block(manual_state(raw=trending), 100_000, n_steps=21, length=1)
    assert block.sum(1).std() > 2 * iid.sum(1).std()
    # Echte Werte aus der Reihe, Reihenfolge innerhalb des Blocks bleibt erhalten
    assert np.allclose(np.abs(block[0].cpu().numpy()), 0.01)


def synthetic_panel(n=900, seed=5):
    rng = np.random.default_rng(seed)
    market = gjr_series(n, 0.05, 0.1, 0.85, seed=seed)
    sector = 1.1 * market + rng.normal(0, 0.003, n)
    r = 1.2 * market + 0.5 * (sector - 1.1 * market) + rng.normal(0, 0.01, n)
    earn = np.zeros(n, dtype=bool)
    earn[60::63] = True
    r[earn] += rng.normal(0, 0.1, earn.sum())
    dates = np.busday_offset(np.datetime64("2015-01-01"), np.arange(n), roll="forward").astype("datetime64[D]").astype(int)
    factors = pd.DataFrame({"asof": [dates[100], dates[400]], "b_m": [1.0, 1.2], "sector": ["S", "S"], "b_s": [0.4, 0.5], "b_sm": [1.0, 1.1]})
    return Panel("X", dates, r, market, {"S": sector}, earn, dates[earn], factors)


def test_prepare_never_sees_the_future():
    panel = synthetic_panel()
    t = 600
    early = prepare(panel, t)
    changed = Panel("X", panel.dates, panel.r.copy(), panel.market.copy(), {"S": panel.sector["S"].copy()}, panel.earn, panel.earnings_days, panel.factors)
    changed.r[t + 1:] = 0.5
    changed.market[t + 1:] = -0.5
    changed.sector["S"][t + 1:] = 0.9
    late = prepare(changed, t)
    assert np.array_equal(early.z, late.z) and np.array_equal(early.next_var, late.next_var) and early.mu == late.mu
    assert np.array_equal(early.jumps, late.jumps)
    # Nur Betas, die zum Stichtag schon bekannt waren
    assert abs(prepare(panel, 200).load[0] - 1.0) < 1e-6 and abs(prepare(panel, 500).load[0] - 1.2) < 1e-6


def test_prepare_keeps_earnings_out_of_normal_volatility():
    panel = synthetic_panel()
    with_jumps, without = prepare(panel, 800), prepare(panel, 800, jumps=False)
    assert len(with_jumps.jumps) == int(panel.earn[:801].sum()) and len(without.jumps) == 0
    # Mit Trennung sind die Eigenanteil-Schocks deutlich weniger extrem
    assert np.abs(with_jumps.z[:, 2]).max() < np.abs(without.z[:, 2]).max()
    assert len(with_jumps.z) == 801 - int(panel.earn[:801].sum())


def test_earnings_schedule():
    panel = synthetic_panel()
    t = int(np.flatnonzero(panel.earn)[3]) - 5  # 5 Handelstage vor dem Termin
    assert earnings_steps(panel, t)[0] == 4  # Schritt 4 ist der fuenfte Tag danach
    # Termin noch nicht angekuendigt: Schaetzung ueber den Quartalsrhythmus ab dem letzten Termin
    panel.earnings_days = panel.earnings_days[panel.earnings_days <= panel.dates[t]]
    steps = earnings_steps(panel, t)
    assert steps[0] == 4 and steps[1] - steps[0] == 63 and steps[-1] < 252
    days = np.array([100, 101, 104, 105])  # Ein Wochenende zwischen 101 und 104
    assert reaction_days(np.array([101 * 86400 + 16 * 3600]), days).tolist() == [104]  # nach Schluss: naechster Handelstag
    assert reaction_days(np.array([101 * 86400 + 7 * 3600]), days).tolist() == [101]  # vor Eroeffnung: selber Tag


def test_kupiec_and_christoffersen():
    rng = np.random.default_rng(6)
    n = 5000
    fair = rng.random(n) < 0.05
    assert kupiec(fair, 0.05)[1] > 0.05 and christoffersen(fair, 0.05)[2] > 0.05
    too_many = rng.random(n) < 0.08
    assert kupiec(too_many, 0.05)[1] < 0.001 and christoffersen(too_many, 0.05)[2] < 0.001
    clustered = np.zeros(n, dtype=bool)
    for start in range(0, n, 200):
        clustered[start:start + 10] = True  # exakt 5 % Quote, aber alle Treffer direkt hintereinander
    assert kupiec(clustered, 0.05)[1] > 0.9
    assert christoffersen(clustered, 0.05)[2] < 1e-6
    assert kupiec(np.zeros(100, dtype=bool), 0.05)[0] > 0  # keine Treffer sind nicht automatisch gut
    # Von Hand: 10 Treffer in 100 Faellen bei 5 % ergibt LR = -2 * (-34.5737 + 32.5083) = 4.1308
    lr, p_value = kupiec(np.r_[np.ones(10), np.zeros(90)], 0.05)
    assert abs(lr - 4.1308) < 0.001 and abs(p_value - 0.0421) < 0.001


def test_var_tests_skip_overlaps_and_future():
    realized = np.full(100, 0.1)
    realized[::10] = -1.0
    realized[60:] = np.nan
    result = var_tests(np.zeros(100), realized, 0.05, 10)
    assert result["n"] == 6 and result["treffer"] == 6 and not result["testbar"]


def test_median_gain_and_loss_split_at_zero_and_ignore_outliers():
    paths = torch.tensor([[0.1], [0.2], [9.0], [-0.1], [-0.2], [-0.3]], device="cuda")
    result = distribution(paths, steps=(1,))
    assert abs(result["mid_up"][0] - math.expm1(0.2)) < 1e-5  # Der Ausreisser verschiebt den Median nicht
    assert abs(result["mid_down"][0] - math.expm1(-0.2)) < 1e-5
    only_losses = distribution(torch.tensor([[-0.1], [-0.2]], device="cuda"), steps=(1,))
    assert only_losses["p_up"][0] == 0  # Keine Gewinne: darf nicht ueber das Ende hinaus greifen


def test_drawdown_and_tp_sl():
    paths = torch.tensor([[-0.1, 0.05, -0.2, 0.3], [0.1, 0.1, -0.05, 0.0]], device="cuda")
    result = distribution(paths, steps=(4,))
    assert abs(result["dd"][0, 0] - math.expm1(-0.25)) < 1e-5  # groesster Rueckgang des ersten Pfads
    # Ohne Drift und mit kleinen Schritten gilt P(+a vor -b) = b / (a + b)
    walk = torch.randn(200_000, 2000, device="cuda") * 0.002
    p_tp, p_sl, p_none = p_tp_before_sl(walk, math.exp(0.04) - 1, 1 - math.exp(-0.04), 2000)  # in Log-Renditen symmetrisch
    assert abs(p_tp - p_sl) < 0.01 and p_none < 0.03, (p_tp, p_sl, p_none)
    p_tp, p_sl, _ = p_tp_before_sl(walk, math.exp(0.08) - 1, 1 - math.exp(-0.04), 2000)
    assert abs(p_tp / (p_tp + p_sl) - 1 / 3) < 0.02, p_tp


def test_worst_episodes():
    logp = np.array([0, 1, 2, 1, 0, 1, 3, 2.5, 2, 4, 3.8, 3.7])
    episodes = worst_episodes(logp, n=3)
    assert episodes[0][:2] == (2, 4) and abs(episodes[0][2] + 2) < 1e-9
    assert episodes[1][:2] == (6, 8) and abs(episodes[1][2] + 1) < 1e-9
    assert episodes[2][:2] == (9, 11)
    assert worst_episodes(np.arange(10.0)) == []


def test_market_replay_uses_sector_only_when_it_existed():
    days = np.arange(16000, 16060)
    # Zwei getrennte Einbrueche: Dazwischen erholt sich der Markt auf ein neues Hoch
    market = np.r_[np.full(10, 0.01), np.full(5, -0.05), np.full(30, 0.01), np.full(5, -0.04), np.full(10, 0.01)]
    sector = market * 1.0 - 0.01  # Sektor faellt jeden Tag staerker als der Markt
    sector[:25] = np.nan  # Der ETF startet erst an Tag 25: Den ersten Einbruch gab es fuer ihn noch nicht
    rows = market_replay(days, market, sector, b_m=1.5, b_s=2.0, b_sm=1.0, price=100.0, n=2)
    first, second = rows[0], rows[1]
    assert first["basis"] == "nur Markt" and abs(first["verlust"] - math.expm1(1.5 * -0.25)) < 1e-9
    assert second["basis"] == "Markt + Sektor"
    assert abs(second["verlust"] - math.expm1(1.5 * -0.20 + 2.0 * 5 * -0.01)) < 1e-9
    assert abs(first["kurs"] - 100 * math.exp(1.5 * -0.25)) < 1e-9


def test_graph_edges_and_queries():
    rng = np.random.default_rng(7)
    n = 400
    market = rng.normal(0, 0.01, n)
    other = rng.normal(0, 0.01, n)
    follower = np.r_[0, market[:-1]] + rng.normal(0, 0.001, n)  # folgt dem Markt mit einem Tag Abstand
    stock = 1.5 * market + 0.8 * other + rng.normal(0, 0.002, n)
    sector = 1.0 * market + other
    days = np.arange(16000, 16000 + n)
    returns = pd.DataFrame({"AAA": stock, MARKET: market, PROXY: market + rng.normal(0, 0.002, n), "SEC": sector, "FOL": follower, "BBB": market + rng.normal(0, 0.01, n)}, index=days)
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        con = sqlite3.connect(Path(tmp) / "g.db")
        ensure(con)
        nodes = [("AAA", "ticker", "A"), ("BBB", "ticker", "B"), (MARKET, "index", "M"), (PROXY, "index", "P"), ("SEC", "sector", "S"), ("FOL", "ticker", "F")]
        write(con, nodes, {"AAA": "SEC", "BBB": "SEC"}, returns, ["AAA", "BBB"], start="2013-12-31")
        table = factor_table(con, "AAA")
        assert len(table) >= 2 and (table.sector == "SEC").all()
        last = table.iloc[-1]
        assert abs(last.b_m - 1.5) < 0.15 and abs(last.b_s - 0.8) < 0.1 and abs(last.b_sm - 1.0) < 0.15, last
        # Vorlauf nur in der richtigen Richtung
        lag = dict(con.execute("SELECT dst, weight FROM edges WHERE src=? AND kind='lead_lag' ORDER BY asof DESC LIMIT 5", (MARKET,)).fetchall())
        back = con.execute("SELECT weight FROM edges WHERE src='FOL' AND dst=? AND kind='lead_lag' ORDER BY asof DESC LIMIT 1", (MARKET,)).fetchone()[0]
        assert lag["FOL"] > 0.9 and abs(back) < 0.2
        # Stichtage kennen nur die Vergangenheit
        changed = returns.copy()
        cut = int(table["asof"].iloc[0])
        changed.loc[changed.index > cut, "AAA"] = 0.5
        before, after = edges_at(returns[returns.index <= cut].tail(252), ["AAA"], {"AAA": "SEC"}, cut), edges_at(changed[changed.index <= cut].tail(252), ["AAA"], {"AAA": "SEC"}, cut)
        assert before == after
        assert neighbors(con, "AAA", "corr", asof=cut, k=2)["asof"].eq(cut).all() and len(neighbors(con, "AAA", "corr", asof=0)) == 0
        assert reachable(con, "AAA") == ["BBB", "SEC"]
        assert reachable(con, "AAA", depth=1) == ["SEC"]
        assert factor_table(con, "ZZZ").empty
        con.close()


def test_million_paths_are_measured_and_fast():
    state = manual_state(alpha=0.05, gamma=0.05, beta=0.85, jumps=(-0.1, 0.1), steps=(10, 73))
    torch.cuda.synchronize()
    tic = time.perf_counter()
    paths = simulate_fhs(state, 1_000_000)
    torch.cuda.synchronize()
    seconds = time.perf_counter() - tic
    result = distribution(paths)
    print(f"    1,000,000 Pfade x 252 Schritte: {seconds:.2f} s, Kennzahlen {time.perf_counter() - tic - seconds:.2f} s")
    assert seconds < 60 and np.isfinite(result["q"]).all()
    # Gleicher Seed, gleiches Ergebnis
    assert torch.equal(simulate_fhs(state, 1000, n_steps=5, seed=9), simulate_fhs(state, 1000, n_steps=5, seed=9))
    del paths
    torch.cuda.empty_cache()


if __name__ == "__main__":
    tests = [f for name, f in list(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print("ok ", test.__name__, flush=True)
    print(f"{len(tests)} Tests bestanden", flush=True)
    exit_now()
