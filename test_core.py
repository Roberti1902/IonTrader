"""Selbsttest Phase 2: python test_core.py"""
import time

import ioncore
import numpy as np
import pandas as pd

from iontrader.features import PATTERNS, compute, feature_path
from iontrader.ingest import TIMEFRAMES


def path(anchors):
    """Kursverlauf aus (Bar, Preis)-Ankern mit konstanter Kerzenbreite."""
    x = np.arange(anchors[-1][0] + 1)
    c = np.interp(x, [a[0] for a in anchors], [a[1] for a in anchors])
    return c + 0.05, c - 0.05, c


def arc(top, depth, half, end):
    """Parabel-Bogen: Rand bei Bar 0, Scheitel bei half, laeuft bis end weiter."""
    return [(x, top - depth * ((x - half) / half) ** 2) for x in range(0, end + 1, 5)]


# Baerische Vorlagen als Anker; die bullische Seite entsteht durch Spiegelung
SHAPES = {
    "SKS": [(0, 100), (20, 120), (35, 110), (55, 130), (70, 110), (90, 120), (130, 80)],
    "Doppeltop": [(0, 100), (30, 130), (50, 115), (80, 130), (120, 90)],
    "Dreifachtop": [(0, 100), (20, 130), (35, 115), (55, 130), (70, 115), (90, 130), (130, 90)],
    "Absteigendes Dreieck": [(0, 120), (20, 130), (40, 110), (52, 122), (64, 110), (70, 116), (100, 90)],
    "Baerenflagge": [(0, 200), (15, 140), (30, 156), (45, 148), (60, 164), (100, 100)],
    "Baerischer Wimpel": [(0, 200), (15, 140), (30, 165), (40, 150), (50, 160), (90, 100)],
    "Baerischer Keil": [(0, 200), (15, 140), (30, 165), (40, 158), (55, 170), (95, 110)],
    "Baerisches Rechteck": [(0, 170), (30, 120), (45, 135), (60, 120), (75, 135), (115, 95)],
    "Inverse Tasse": arc(130, 30, 40, 80) + [(90, 110), (120, 80)],
    "Rounding Top": arc(130, 30, 40, 100),
}
MIRROR = {
    "SKS": "Inverse SKS", "Doppeltop": "Doppelboden", "Dreifachtop": "Dreifachboden",
    "Absteigendes Dreieck": "Aufsteigendes Dreieck", "Baerenflagge": "Bullenflagge",
    "Baerischer Wimpel": "Bullischer Wimpel", "Baerischer Keil": "Bullischer Keil",
    "Baerisches Rechteck": "Bullisches Rechteck", "Inverse Tasse": "Tasse mit Henkel",
    "Rounding Top": "Rounding Bottom",
}


def found(h, l, c, name, side):
    """Sucht das Muster auf allen Empfindlichkeiten und liefert das erste passende Ereignis."""
    wanted = PATTERNS.index(name)
    for scan in ioncore.scan(h, l, c, [1.5, 2.0, 3.0, 5.0]):
        hits = np.flatnonzero(scan["pattern"] == wanted)
        if len(hits):
            e = hits[0]
            assert scan["side"][e] == side
            assert scan["bar"][e] >= scan["start"][e]
            return {key: scan[key][e] for key in ("bar", "entry", "sl", "tp")}
    return None


def test_all_20_patterns_are_found():
    assert len(PATTERNS) == 20
    missing = []
    for bear, anchors in SHAPES.items():
        h, l, c = path(anchors)
        e = found(h, l, c, bear, -1)
        if e is None:
            missing.append(bear)
        else:
            assert e["sl"] > e["entry"] > e["tp"], bear
        # Spiegelung: gleiche Formel, Long statt Short
        h2, l2, c2 = 300 - l, 300 - h, 300 - c
        e = found(h2, l2, c2, MIRROR[bear], 1)
        if e is None:
            missing.append(MIRROR[bear])
        else:
            assert e["tp"] > e["entry"] > e["sl"], MIRROR[bear]
    assert not missing, f"nicht erkannt: {missing}"


def test_pattern_levels_follow_the_picture():
    h, l, c = path(SHAPES["Doppeltop"])
    e = found(h, l, c, "Doppeltop", -1)
    assert abs(e["sl"] - 130.05) < 1e-9  # SL am Hoch
    assert abs(e["tp"] - (115 - 0.05 - (130.05 - 114.95))) < 0.2  # TP = Hoehe unter der Nackenlinie
    h, l, c = path(SHAPES["Rounding Top"])
    e = found(h, l, c, "Rounding Top", -1)
    assert e["sl"] > 129.9  # SL auf Scheitelhoehe
    h, l, c = path(SHAPES["Baerenflagge"])
    e = found(h, l, c, "Baerenflagge", -1)
    assert e["entry"] - e["tp"] > 55  # TP = Fahnenstange (60), nicht die Flaggenbreite
    h, l, c = path(SHAPES["Baerischer Wimpel"])
    e = found(h, l, c, "Baerischer Wimpel", -1)
    assert e["entry"] - e["tp"] < 30  # TP = groesste Wimpelbreite (25)


def random_walk(n=3000, seed=7):
    rng = np.random.default_rng(seed)
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.002, n)))
    spread = np.abs(rng.normal(0, 0.1, n)) + 0.05
    o = np.r_[c[0], c[:-1]]
    idx = pd.date_range("2020-01-01", periods=n, freq="5min", tz="UTC")
    return pd.DataFrame({"open": o, "high": np.maximum(o, c) + spread, "low": np.minimum(o, c) - spread,
                         "close": c, "volume": rng.integers(100, 1000, n).astype(float)}, index=idx)


def test_no_lookahead():
    """Abgeschnittene Daten muessen bis zum Schnitt exakt dieselben Werte und Ereignisse liefern."""
    df = random_walk()
    full, events = compute(df, windows=(256, 1024))
    assert len(events) > 0
    for cut in (2100, 2500, 2999):
        part, part_events = compute(df.iloc[:cut], windows=(256, 1024))
        last = cut - 1
        a, b = full.iloc[last][part.columns].to_numpy(dtype=float), part.iloc[last].to_numpy(dtype=float)
        bad = ~(np.isclose(a, b, rtol=1e-9, atol=1e-12) | (np.isnan(a) & np.isnan(b)))
        assert not bad.any(), f"Blick in die Zukunft bei Schnitt {cut}: {part.columns[bad].tolist()}"
        cols = ["pattern", "bar", "start", "side", "k"]
        early = events[events.bar < cut][cols].sort_values(cols).reset_index(drop=True)
        pd.testing.assert_frame_equal(early, part_events[cols].sort_values(cols).reset_index(drop=True),
                                      check_dtype=False)


def test_triple_barrier():
    h = np.array([10, 11, 13, 9, 10, 10, 10, 10], dtype=float)
    l = np.array([9, 9.5, 11, 7, 9, 9, 9, 9], dtype=float)
    c = np.array([10, 10.5, 12, 8, 9.5, 9.5, 9.5, 9.5], dtype=float)
    # Long ab Bar 0: TP 12.5 wird in Bar 2 getroffen
    # Long ab Bar 0 mit SL 9.2: Bar 1 trifft den SL zuerst
    # Short ab Bar 1 mit TP 8 und SL 14: Bar 3 trifft das TP
    # Long ab Bar 2 mit TP 12.9 und SL 11.5 und Zeitlimit 0 Bars ist unten separat
    res = ioncore.triple_barrier(h, l, c, np.array([0, 0, 1], dtype=np.int64), np.array([1, 1, -1], dtype=np.int64),
                                 np.array([8.0, 9.6, 14.0]), np.array([12.5, 20.0, 8.0]),
                                 np.array([5, 5, 5], dtype=np.int64))
    assert res["outcome"].tolist() == [1, -1, 1]
    assert res["bars"].tolist() == [2, 1, 2]
    assert abs(res["r"][0] - 2.5 / 2.0) < 1e-12 and abs(res["r"][1] + 1) < 1e-12
    # Beide Barrieren im selben Bar: SL zaehlt. Zeitlimit: 0. Daten zu Ende: -2.
    res = ioncore.triple_barrier(h, l, c, np.array([2, 4, 6], dtype=np.int64), np.array([1, 1, 1], dtype=np.int64),
                                 np.array([11.0, 1.0, 1.0]), np.array([12.5, 50.0, 50.0]),
                                 np.array([5, 2, 5], dtype=np.int64))
    assert res["outcome"].tolist() == [-1, 0, -2]
    assert np.isnan(res["r"][2])


def test_dfa_recovers_known_memory():
    rng = np.random.default_rng(1)
    noise = rng.normal(0, 1, 20000)
    h_noise = np.nanmean(ioncore.rolling_mfdfa(noise, 4096)["h2"])
    assert abs(h_noise - 0.5) < 0.05, h_noise
    # Trend-Gedaechtnis: fraktionales Rauschen naeherungsweise ueber gewichtete Summe (H ~ 0.8)
    d = 0.3
    weights = np.cumprod(np.r_[1.0, (np.arange(1, 1000) - 1 + d) / np.arange(1, 1000)])
    persistent = np.convolve(noise, weights, mode="valid")
    h_persistent = np.nanmean(ioncore.rolling_mfdfa(persistent, 4096)["h2"])
    assert h_persistent > 0.68, h_persistent
    # Umkehr-Gedaechtnis: Differenzen von weissem Rauschen haben H weit unter 0,5
    h_anti = np.nanmean(ioncore.rolling_mfdfa(np.diff(noise), 4096)["h2"])
    assert h_anti < 0.3, h_anti
    # Ein konstantes Fenster liefert NaN statt eines Fantasiewerts
    assert np.isnan(ioncore.rolling_mfdfa(np.zeros(600), 256)["h2"][-1])


def test_mean_reversion_measures():
    rng = np.random.default_rng(2)
    n, theta = 5000, 0.1
    ou = np.zeros(n)
    for i in range(1, n):
        ou[i] = ou[i - 1] * (1 - theta) + rng.normal(0, 0.01)
    mr = ioncore.rolling_mr(np.exp(ou + 5), 512)
    assert np.nanmedian(mr["adf"]) < -3.4  # klar stationaer
    assert abs(np.nanmedian(mr["half_life"]) - np.log(2) / theta) < 2.5
    assert np.nanmedian(mr["vr8"]) < 0.8  # Umkehr
    walk = ioncore.rolling_mr(np.exp(np.cumsum(rng.normal(0, 0.01, n)) + 5), 512)
    assert np.nanmedian(walk["adf"]) > -2.5
    assert abs(np.nanmedian(walk["vr4"]) - 1) < 0.1


def test_shift_test_finds_only_real_signals():
    rng = np.random.default_rng(3)
    fwd = rng.normal(0, 1, 20000)
    events = rng.choice(20000, 300, replace=False).astype(np.int64)
    _, _, p_null, _ = ioncore.shift_test(fwd, events, 5000)
    assert p_null > 0.01, p_null
    fwd[events] += 1.0
    mean_ev, mean_all, p_real, k = ioncore.shift_test(fwd, events, 5000)
    assert p_real < 0.001 and mean_ev > mean_all and k == 300
    # NaN-Renditen (Ende der Daten) zaehlen nicht mit
    fwd[events[:100]] = np.nan
    assert ioncore.shift_test(fwd, events, 100)[3] == 200


def test_feature_files_do_not_collide_on_windows():
    names = {feature_path("META", tf).name.casefold() for tf in TIMEFRAMES}
    assert len(names) == len(TIMEFRAMES)


def test_control_group_separates_edge_from_drift():
    rng = np.random.default_rng(5)
    n = 30000
    returns = rng.normal(0.0002, 0.001, n)  # Aufwaertstrend wie bei einer stark gestiegenen Aktie
    events = np.sort(rng.choice(n - 500, 400, replace=False)).astype(np.int64)
    side = np.ones(400, dtype=np.int64)
    sl_atr, tp_atr, max_bars = np.full(400, -2.0), np.full(400, 2.0), np.full(400, 100, dtype=np.int64)

    def test(ret):
        c = 100 * np.exp(np.cumsum(ret))
        h, l = c * 1.0005, c * 0.9995
        atr = c * 0.001
        return ioncore.control_test(h, l, c, atr, events, side, sl_atr, tp_atr, max_bars, 2000, 1)

    r, control, p = test(returns)
    assert control > 0.05  # Der Trend allein macht Long-Einstiege profitabel ...
    assert p > 0.01, p     # ... aber zufaellige Einstiege haben dadurch noch keinen eigenen Vorsprung
    planted = returns.copy()
    for e in events:
        planted[e + 1:e + 6] += 0.001  # echter Vorsprung direkt nach dem Ereignis
    r, control, p = test(planted)
    assert r > control + 0.3 and p < 0.01, (r, control, p)


def test_threads_scale():
    x = np.random.default_rng(4).normal(0, 1, 60000)
    timing = {}
    full = ioncore.threads()
    for n in (1, full):
        ioncore.set_threads(n)
        start = time.perf_counter()
        ioncore.rolling_mfdfa(x, 1024)
        timing[n] = time.perf_counter() - start
    ioncore.set_threads(full)
    print(f"    Rolling DFA: 1 Thread {timing[1]:.2f} s, {full} Threads {timing[full]:.2f} s, "
          f"Faktor {timing[1] / timing[full]:.1f}")
    assert timing[1] / timing[full] > 3


if __name__ == "__main__":
    tests = [f for name, f in list(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print("ok ", test.__name__)
    print(f"{len(tests)} Tests bestanden")
