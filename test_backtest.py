"""Phase 7: Simulator ohne Datenbank. Zukunftsblick, Kosten, Steuer, Staffelung und Bootstrap."""
import numpy as np

from iontrader.backtest import CAPITAL, TAX, boot_indices, compare, simulate, staggered, stats, to_execution, vol_decision


def free(open_, close, weight, **kw):
    return simulate(np.array(open_, float), np.array(close, float), np.array(weight, float), cost=0, fee=0, **kw)


def test_decision_trades_only_at_the_next_open():
    weight = to_execution(np.array([1.0, 1.0, 1.0]))
    assert weight.tolist() == [0.0, 1.0, 1.0]
    run = free([100, 100, 200], [100, 200, 200], weight, tax=0)
    assert run.nav.tolist() == [CAPITAL, 2 * CAPITAL, 2 * CAPITAL], run.nav  # Der Sprung an Tag 2 kommt mit, die Entscheidung von Tag 1 wirkt dort


def test_late_decision_cannot_change_the_past():
    decision = np.array([1.0, 0.0, 1.0, 0.0])
    other = decision.copy()
    other[-1] = 1.0
    prices = [100, 90, 120, 80]
    a = free(prices, prices, to_execution(decision), tax=0).nav
    b = free(prices, prices, to_execution(other), tax=0).nav
    assert (a == b).all(), (a, b)


def test_gap_after_the_signal_is_not_earned():
    # Schluss 100, Eroeffnung 150: Wer am Schluss entscheidet, kauft zu 150
    run = free([100, 150], [100, 150], to_execution(np.array([1.0, 1.0])), tax=0)
    assert run.nav[-1] == CAPITAL, run.nav


def test_costs_are_charged_on_both_sides():
    run = simulate(np.full(3, 100.0), np.full(3, 100.0), np.array([1.0, 1.0, 1.0]), cost=0.01, fee=1.0, tax=0)
    assert run.orders == 2, run.orders
    bought = CAPITAL - (CAPITAL * 0.01 + 1)  # Die Kosten kommen vom Geplanten, das Gekaufte wird entsprechend kleiner
    assert abs(run.final_after_tax - (bought * 0.99 - 1)) < 1e-6, run.final_after_tax


def test_tax_on_gain_and_loss_carry():
    years = np.array([1, 1, 2, 2, 3])
    # Jahr 1: Verlust 50 %, Jahr 2: zurueck auf den Start und Verkauf, Jahr 3: nichts. Unterm Strich kein Gewinn, keine Steuer
    open_ = [100, 50, 50, 100, 100]
    weight = [1, 0, 1, 0, 0]
    run = free(open_, open_, weight, years=years)
    assert abs(run.tax_paid) < 1e-6, run.tax_paid
    assert abs(run.final_after_tax - CAPITAL) < 1e-6, run.final_after_tax
    # Gewinn verdoppelt, am Ende verkauft: Steuer auf den Gewinn
    gain = free([100, 200], [100, 200], [1, 1])
    assert abs(gain.final_after_tax - (2 * CAPITAL - TAX * CAPITAL)) < 1e-6, gain.final_after_tax


def test_tax_is_paid_each_year_when_realized():
    years = np.array([1, 1, 2, 2])
    run = free([100, 200, 200, 400], [100, 200, 200, 400], [1, 0, 1, 1], years=years)
    after_first = 2 * CAPITAL - TAX * CAPITAL
    expected = 2 * after_first - TAX * after_first
    assert abs(run.final_after_tax - expected) < 1e-6, (run.final_after_tax, expected)


def test_return_is_before_tax_and_after_tax_is_lower():
    prices = 100 * 1.001 ** np.arange(504)
    years = np.r_[np.zeros(252, dtype=int), np.ones(252, dtype=int)]
    weight = np.tile([1.0, 1.0, 1.0, 1.0, 0.0], 101)[:504]
    gross = free(prices, prices, weight, years=years, tax=0)
    net = free(prices, prices, weight, years=years)
    out = stats(gross, net, np.zeros(504))
    assert net.tax_paid > 0 and gross.tax_paid == 0
    assert out["rendite"] > out["nach_steuer"] > 0, out
    assert abs(out["rendite"] - ((gross.final_after_tax / CAPITAL) ** (252 / 504) - 1)) < 1e-12, out
    assert np.diff(gross.nav).min() > -1e-6, np.diff(gross.nav).min()  # Vor Steuern fliesst nichts ab, Rundung ausgenommen


def test_cash_earns_the_rate():
    run = free(np.full(252, 100.0), np.full(252, 100.0), np.zeros(252), rate=np.full(252, 0.05), tax=0)
    assert abs(run.final_after_tax / CAPITAL - (1 + 0.05 / 252) ** 252) < 1e-9, run.final_after_tax
    rate = 0.03 + 0.02 * np.sin(np.arange(252))  # Auch bei wechselndem Zins hat Cash keinen Ueberschuss
    drift = free(np.full(252, 100.0), np.full(252, 100.0), np.zeros(252), rate=rate, tax=0)
    assert abs(stats(drift, drift, rate)["sharpe"]) < 1e-6


def test_small_changes_cause_no_orders():
    run = simulate(np.full(4, 100.0), np.full(4, 100.0), np.array([1.0, 0.98, 1.0, 0.97]), cost=0.001, fee=1.0, tax=0)
    assert run.orders == 2, run.orders  # Kauf und Schlussverkauf


def test_staggering_builds_up_and_ignores_the_start_day():
    assert staggered(np.array([1, 0, 0, 1.0]), 2).tolist() == [1.0, 0.5, 0.0, 0.5]


def test_vol_weight_uses_only_earlier_forecasts_and_caps_at_one():
    low, high = -np.full(200, 1.0), np.full(200, 1.0)
    calm = vol_decision(low, high)
    assert (calm == 1).all()
    wild = high.copy()
    wild[150:] = 3.0
    weight = vol_decision(low, wild)
    assert weight[149] == 1 and 0.4 < weight[150] < 0.6, weight[150]
    changed = wild.copy()
    changed[199] = 100.0
    assert (vol_decision(low, changed)[:199] == weight[:199]).all()


def test_bootstrap_finds_a_clear_gap_and_no_gap():
    rng = np.random.default_rng(1)
    n = 1500
    ref = rng.normal(0.0005, 0.01, n)
    cash = np.zeros(n)
    idx = boot_indices(n, draws=1000)
    assert idx.shape == (1000, n) and idx.min() >= 0 and idx.max() < n
    same = compare(ref, ref, cash, idx)
    assert same["rendite_diff"] == 0 and same["rendite_p"] > 0.9
    better = compare(ref + 0.002, ref, cash, idx)
    assert better["rendite_p"] < 0.01 and better["rendite_low"] > 0, better


if __name__ == "__main__":
    tests = [f for name, f in list(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print("ok ", test.__name__, flush=True)
    print(f"{len(tests)} Tests bestanden", flush=True)
