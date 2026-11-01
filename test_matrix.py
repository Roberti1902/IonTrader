"""Selbsttest Phase 5: python test_matrix.py"""
import ioncore
import numpy as np

from iontrader import exit_now
from iontrader.matrix import (PURGE_DAYS, Daily, calibrate_folds, calibration_error, conformal_factor, direction_proven, direction_rows, fit_stack,
                              isotonic_fit, logit, reliability, sigmoid, stack_folds, widen)
from iontrader.setup import _standardize
from iontrader.study import HORIZONS


def stack_data(n=4000, strength=1.0, seed=1):
    rng = np.random.default_rng(seed)
    signal, noise = rng.normal(0, 0.5, n), rng.normal(0, 0.5, n)
    base = np.full(n, logit(0.55))
    up = (rng.random(n) < sigmoid(base + strength * signal)).astype(float)
    return np.c_[signal, noise], up, base


def test_stack_finds_the_real_source_and_ignores_noise():
    x, up, base = stack_data()
    w = fit_stack(x, up, base, 1.0, l2=1.0)
    assert 0.7 < w[0] < 1.3, w
    assert w[1] < 0.1, w


def test_stack_never_goes_negative():
    x, up, base = stack_data()
    w = fit_stack(-x, up, base, 1.0, l2=1.0)  # Eine falsch gepolte Quelle wird nicht umgedreht, sondern ignoriert
    assert (w >= 0).all() and w[0] == 0


def test_stack_stays_at_base_rate_without_evidence():
    x, up, base = stack_data(n=4000)
    # Viele Faelle: deutliches Gewicht. Gleiche Daten, aber lange Horizonte mit wenig unabhaengigen Faellen: fast keins.
    short = fit_stack(x, up, base, 1.0)
    long = fit_stack(x, up, base, 1 / 252)
    assert short[0] > 0.5 and long[0] < 0.1 * short[0], (short, long)
    # Ohne Eingabe bleibt exakt die Basisrate
    assert (fit_stack(np.zeros_like(x), up, base, 1.0) == 0).all()


def test_stack_finds_nothing_in_pure_noise():
    x, up, base = stack_data(strength=0.0)
    w = fit_stack(x, up, base, 1.0)
    p = sigmoid(base + x @ w)
    assert np.abs(p - sigmoid(base)).mean() < 0.01, np.abs(p - sigmoid(base)).mean()  # typische Abweichung unter 1 Prozentpunkt


def make_daily(n=2000, signal=True, seed=2):
    """Taeglich ein Fall, 5 Horizonte, 2 Quellen. Die erste Quelle kennt den 1-Tages-Ausgang teilweise."""
    rng = np.random.default_rng(seed)
    date = np.arange(10000, 10000 + n)
    base_up = np.full((n, 5), 0.55)
    x = rng.normal(0, 0.4, (n, 5, 2))
    p = sigmoid(logit(base_up) + (x[:, :, 0] if signal else 0))
    y = np.where(rng.random((n, 5)) < p, 1.0, -1.0)
    return Daily(date, y, np.ones((n, 5), dtype=bool), base_up, ["a", "b"], x)


def test_stack_folds_learn_only_from_the_past():
    daily = make_daily()
    start, end = 11000, 11500
    baseline, _, weights = stack_folds(daily, [(start, end)])
    # Spaetere Ergebnisse aendern ist egal: Die Gewichte duerfen nur auf Tagen beruhen, die vor dem Testjahr feststanden
    changed = make_daily()
    for h, purge in enumerate(PURGE_DAYS):
        late = changed.date + purge >= start
        changed.y[late, h] = -changed.y[late, h]
        changed.x[late, h] = 9.0
    _, _, weights_changed = stack_folds(changed, [(start, end)])
    assert np.array_equal(weights[start], weights_changed[start])
    # Ausserhalb des Testjahrs bleibt es bei der Basisrate
    outside = (daily.date < start) | (daily.date >= end)
    assert np.allclose(baseline[outside], daily.base_up[outside])
    assert (baseline[(daily.date >= start) & (daily.date < end), 0] != 0.55).any()


def test_walk_forward_scores_real_signal_and_noise():
    start, end = 11000, 12000
    real = make_daily(signal=True)
    p, active, _ = stack_folds(real, [(start, end)])
    good = direction_rows(p, real, active, "x")[0]
    assert good["brier_skill"] > 0.02 and good["brier_low"] > 0, good
    noise = make_daily(signal=False)
    p, active, _ = stack_folds(noise, [(start, end)])
    flat = direction_rows(p, noise, active, "x")[0]
    assert flat["brier_low"] <= 0, flat  # Kein Vorsprung im Rauschen
    assert abs(flat["brier_skill"]) < 0.01, flat


def test_isotonic_is_monotone_and_correct():
    xs, ys = isotonic_fit(np.array([1, 2, 3, 4, 5.0]), np.array([1, 3, 2, 4, 5.0]))
    assert ys.tolist() == [1, 2.5, 4, 5] and xs.tolist() == [1, 3, 4, 5]
    # Verzerrte Wahrscheinlichkeiten werden zurueckgebogen
    rng = np.random.default_rng(3)
    truth = rng.random(50000)
    shown = truth ** 2
    up = (rng.random(50000) < truth).astype(float)
    xs, ys = isotonic_fit(shown, up)
    assert (np.diff(ys) > 0).all()
    fixed = np.interp(shown, xs, ys)
    assert calibration_error(fixed, up) < 0.01 < calibration_error(shown, up)


def test_calibration_uses_only_earlier_folds():
    daily = make_daily()
    p = daily.base_up.astype(float) + 0.1 * np.tanh(daily.x[:, :, 0])
    active = daily.date < 11500
    before = calibrate_folds(p, daily, active, [(11500, 11600)])
    changed = make_daily()
    for h, purge in enumerate(PURGE_DAYS):
        late = changed.date + purge >= 11500  # Jeder Horizont hat seine eigene Sperrfrist
        changed.y[late, h] = -changed.y[late, h]
    after = calibrate_folds(p, changed, active, [(11500, 11600)])
    test = (daily.date >= 11500) & (daily.date < 11600)
    assert np.array_equal(before[test], after[test])


def test_conformal_reaches_the_target_coverage():
    rng = np.random.default_rng(4)
    scale = np.exp(rng.normal(0, 0.5, 40000))
    real = scale * rng.standard_normal(40000)
    narrow_low, narrow_high = -0.8 * scale, 0.8 * scale  # zu schmal
    wide_low, wide_high = -2.5 * scale, 2.5 * scale  # zu breit
    for low, high in ((narrow_low, narrow_high), (wide_low, wide_high)):
        factor = conformal_factor(low[:20000], high[:20000], real[:20000])
        new_low, new_high = widen(low[20000:], high[20000:], factor)
        coverage = ((real[20000:] >= new_low) & (real[20000:] <= new_high)).mean()
        assert abs(coverage - 0.8) < 0.01, coverage
    assert conformal_factor(narrow_low, narrow_high, real) > 0 > conformal_factor(wide_low, wide_high, real)


def test_reliability_table():
    rng = np.random.default_rng(5)
    p = rng.uniform(0.4, 0.9, 20000)
    up = (rng.random(20000) < p).astype(float)
    rows = reliability(p, up, np.arange(20000))
    assert sum(r["n"] for r in rows) == 20000
    for r in rows:
        assert abs(r["angezeigt"] - r["tatsaechlich"]) < 0.03, r
    assert calibration_error(p, up) < 0.01
    assert calibration_error(np.full(1000, 0.9), np.zeros(1000)) > 0.89


def test_ic_test_finds_links_and_rejects_shared_inertia():
    rng = np.random.default_rng(6)
    n = 20000
    a = rng.standard_normal(n)
    linked = _standardize(0.1 * a + rng.standard_normal(n))
    a = _standardize(a)
    ic, p = ioncore.ic_test(a, linked, 2000)
    assert abs(ic - 0.0995) < 0.02 and p < 0.002, (ic, p)
    # Zwei unabhaengige, sehr traege Reihen korrelieren oft zufaellig stark. Der Test darf darauf nicht hereinfallen.
    false_alarms = 0
    for seed in range(40):
        g = np.random.default_rng(100 + seed)
        x, y = np.zeros(4000), np.zeros(4000)
        for t in range(1, 4000):
            x[t] = 0.995 * x[t - 1] + g.standard_normal()
            y[t] = 0.995 * y[t - 1] + g.standard_normal()
        _, p = ioncore.ic_test(_standardize(x), _standardize(y), 500, seed)
        false_alarms += p < 0.05
    assert false_alarms <= 6, false_alarms  # 5 % von 40 waeren 2; ein naiver Test laege weit darueber


def test_a_lead_must_repeat_to_count():
    above, below, missing = {"n": 100, "brier_low": 0.002}, {"n": 100, "brier_low": -0.002}, {"n": 0}
    assert direction_proven(above, above)
    assert not direction_proven(below, above)  # Genau der Fall bei META: nur ein Zeitraum positiv
    assert not direction_proven(above, below)
    assert not direction_proven(above, missing)
    assert not direction_proven(above, {"n": 5, "brier_low": float("nan")})
    assert not direction_proven(above, {"n": 100, "brier_low": 1e-9})  # eine Untergrenze auf null zaehlt nicht


def test_horizon_tables_stay_consistent():
    assert len(PURGE_DAYS) == len(HORIZONS)
    # Das Purging muss jede Zielgroesse sicher abdecken: Kalendertage mindestens wie Handelstage mal 7/5 minus Spielraum
    for purge, steps in zip(PURGE_DAYS, HORIZONS.values()):
        assert purge >= steps * 7 / 5 - 1, (purge, steps)


if __name__ == "__main__":
    tests = [f for name, f in list(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print("ok ", test.__name__, flush=True)
    print(f"{len(tests)} Tests bestanden", flush=True)
    exit_now()
