"""Phase 8: Rangliste ohne Datenbank und Netz. Mitgliedschaft, Auswahl, Verschwinden, Kosten, Steuer und Zukunftsblick."""
import numpy as np
import pandas as pd

from iontrader.ranking import CAPITAL, COST, DELIST_PENALTY, FEE, TAX, combine, factor_scores, membership, month_ends, rank_ic, select, simulate, vol_scale


def days(n, start="2020-01-01"):
    return pd.bdate_range(start, periods=n, tz="UTC")


def test_membership_runs_backward_from_today():
    d = pd.DatetimeIndex(pd.to_datetime(["2020-01-01", "2020-06-01", "2021-01-01"], utc=True))
    changes = pd.DataFrame({"date": pd.to_datetime(["2020-03-01", "2020-09-01"], utc=True), "add": ["B", "C"], "rem": ["A", np.nan]})
    out = membership(["B", "C"], changes, d)
    assert out["A"].tolist() == [True, False, False], out["A"]
    assert out["B"].tolist() == [False, True, True], out["B"]
    assert out["C"].tolist() == [False, False, True], out["C"]


def test_month_ends_are_last_trading_days():
    d = pd.DatetimeIndex(pd.to_datetime(["2020-01-30", "2020-01-31", "2020-02-03", "2020-02-28", "2020-03-02"], utc=True))
    assert month_ends(d).tolist() == [1, 3]


def test_select_keeps_holdings_inside_the_buffer_only():
    scores = np.array([9.0, 8, 7, 6, 5, 4, np.nan])
    eligible = np.ones(7, dtype=bool)
    fresh = select(scores, eligible, np.zeros(7, dtype=bool), top=2, keep=4)
    assert (fresh > 0).tolist() == [True, True, False, False, False, False, False]
    held = np.array([False, False, False, True, True, False, False])  # Rang 4 bleibt, Rang 5 faellt raus, Platz fuellt der Beste
    kept = select(scores, eligible, held, top=2, keep=4)
    assert (kept > 0).tolist() == [True, False, False, True, False, False, False], kept
    assert abs(kept.sum() - 1) < 1e-12
    excluded = select(scores, np.array([False, True, True, True, True, True, True]), np.zeros(7, dtype=bool), top=2, keep=4)
    assert excluded[0] == 0 and excluded[6] == 0


def test_factors_use_no_future_and_skip_the_last_month():
    rng = np.random.default_rng(0)
    close = pd.DataFrame(100 * np.exp(rng.normal(0, 0.01, (400, 3)).cumsum(0)), columns=list("ABC"))
    scores, _ = factor_scores(close)
    changed = close.copy()
    changed.iloc[390:] *= 2
    later, _ = factor_scores(changed)
    for name in scores:
        assert scores[name].iloc[:389].equals(later[name].iloc[:389]), name
    assert scores["Momentum 12-1"].iloc[380].equals(later["Momentum 12-1"].iloc[380])
    assert (later["Momentum 12-1"].iloc[399] - scores["Momentum 12-1"].iloc[399]).abs().max() < 1e-12  # Die letzten 21 Tage zaehlen nicht


def test_suspect_jump_flags_a_year():
    close = pd.DataFrame({"A": np.r_[np.full(10, 100.0), np.full(300, 200.0)]})
    _, suspect = factor_scores(close)
    assert suspect.A.iloc[10] and suspect.A.iloc[261] and not suspect.A.iloc[262], suspect.A.iloc[[10, 261, 262]]


def test_combine_averages_ranks():
    a = pd.DataFrame([[1.0, 2.0, 3.0]])
    b = pd.DataFrame([[3.0, 2.0, 1.0]])
    assert (combine(a, b).iloc[0] == combine(a, b).iloc[0, 0]).all()


def test_vol_scale_caps_and_cuts_when_volatile():
    rng = np.random.default_rng(1)
    returns = rng.normal(0, 0.01, 300)
    returns[250:] *= 4
    close = pd.DataFrame({"A": 100 * np.exp(returns.cumsum())})
    scale = vol_scale(close).A
    assert scale.max() <= 1 and scale.iloc[10] == 1
    assert scale.iloc[280] < 0.5, scale.iloc[280]


def test_ic_finds_perfect_order():
    s = np.arange(100.0)[None, :].repeat(3, 0)
    out = rank_ic(s + np.array([[0], [1], [2]]), s * 2, np.ones_like(s, dtype=bool))
    assert abs(out["ic"] - 1) < 1e-9 and out["monate"] == 3


def book(open_, close, targets, **kw):
    n = len(close)
    return simulate(np.array(open_, float), np.array(close, float), targets, np.zeros(n), kw.pop("years", np.zeros(n, dtype=int)), **kw)


def test_trade_happens_at_the_next_open_without_lookahead():
    run = book([[100], [150], [150]], [[100], [150], [300]], {0: np.array([1.0])}, cost=0, fee=0, tax=0)
    assert run.nav.tolist() == [CAPITAL, CAPITAL, 2 * CAPITAL], run.nav


def test_costs_on_both_sides():
    prices = np.full((3, 1), 100.0)
    run = book(prices, prices, {0: np.array([1.0])}, tax=0)
    need = CAPITAL * (1 + COST) + FEE
    bought = CAPITAL * (CAPITAL / need)
    expected = CAPITAL - bought - (bought * COST + FEE) + bought - bought * COST - FEE
    assert abs(run.final_after_tax - expected) < 1e-6, (run.final_after_tax, expected)
    assert run.orders == 2


def test_delisted_stock_is_sold_at_last_close_without_penalty_when_stable():
    close = np.array([[100.0], [100.0], [100.0], [np.nan], [np.nan]])
    run = book(close, close, {0: np.array([1.0])}, cost=0, fee=0, tax=0)
    assert abs(run.nav[-1] - CAPITAL) < 1e-6, run.nav


def test_collapsed_stock_gets_the_penalty():
    close = np.array([[100.0], [100.0], [50.0], [np.nan]])
    open_ = np.array([[100.0], [100.0], [100.0], [np.nan]])
    run = book(open_, close, {0: np.array([1.0])}, cost=0, fee=0, tax=0)
    assert abs(run.nav[-1] - CAPITAL * 0.5 * (1 - DELIST_PENALTY)) < 1e-6, run.nav


def test_missing_open_delays_the_trade_and_small_changes_trade_nothing():
    open_ = np.array([[100.0, 100.0], [100.0, 100.0], [100.0, 100.0]])
    run = book(open_, open_, {0: np.array([0.5, 0.5]), 1: np.array([0.45, 0.55])}, cost=0, fee=0, tax=0)
    assert run.orders == 4, run.orders  # Zwei Kaeufe, zwei Schlussverkaeufe; die 10 % Abweichung loest nichts aus


def test_tax_on_final_gain_and_loss_carry_between_years():
    close = np.array([[100.0], [200.0]])
    gain = book(np.array([[100.0], [100.0]]), close, {0: np.array([1.0])}, cost=0, fee=0)
    assert abs(gain.final_after_tax - (2 * CAPITAL - TAX * CAPITAL)) < 1e-6, gain.final_after_tax
    prices = np.array([[100.0], [100.0], [50.0], [50.0], [50.0], [100.0], [100.0]])
    targets = {0: np.array([1.0]), 2: np.array([0.0]), 3: np.array([1.0]), 5: np.array([0.0])}
    years = np.array([1, 1, 1, 1, 2, 2, 2])
    run = book(prices, prices, targets, cost=0, fee=0, years=years)
    assert abs(run.tax_paid) < 1e-6 and abs(run.final_after_tax - CAPITAL) < 1e-6, (run.tax_paid, run.final_after_tax)


def test_year_end_without_tax_causes_no_order():
    prices = np.full((4, 1), 100.0)
    run = book(prices, prices, {0: np.array([1.0])}, tax=0, years=np.array([1, 1, 2, 2]))
    assert run.orders == 2, run.orders


def test_gross_and_net_differ_only_by_tax():
    prices = np.array([[100.0], [100.0], [200.0], [200.0]])
    years = np.array([1, 1, 2, 2])
    targets = {0: np.array([1.0]), 1: np.array([0.0]), 2: np.array([1.0])}
    gross = book(prices, prices, targets, cost=0, fee=0, tax=0, years=years)
    net = book(prices, prices, targets, cost=0, fee=0, years=years)
    assert net.final_after_tax < gross.final_after_tax


if __name__ == "__main__":
    tests = [f for name, f in list(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print("ok ", test.__name__, flush=True)
    print(f"{len(tests)} Tests bestanden", flush=True)
