"""Selbsttest Phase 3: python test_brain.py"""
import time

import ioncore
import numpy as np
import torch

from iontrader import exit_now
from iontrader.dataset import HOLDOUT_DAYS, INPUT, Bundle, Ticker, fold_dates, load_ticker, realized_vol
from iontrader.match import LENGTH, MatchIndex, summarize
from iontrader.models import KINDS, IonNet
from iontrader.store import connect, load
from iontrader.train import Selector, fit, fold_output, skill_scores

WINDOWS = {"5m": 32, "1D": 16}
DAYS = {"a": 1, "b": 2, "c": 3, "d": 4, "e": 5}
START, END, HOLDOUT = 2000, 2500, 2900  # Testfenster in Tagen; 10 Bars je Tag


def synthetic(signal, n=30000, seed=1, vol=False):
    """Zwei Timeframes mit 4 Features. Mit signal haengt die Zielgroesse am letzten Feature-Wert, sonst Zufall."""
    rng = np.random.default_rng(seed)
    frames, columns, ts, pos = {}, {}, {}, {}
    for tf, step in (("5m", 1), ("1D", 10)):
        rows = n // step
        frames[tf] = rng.normal(0, 1, (rows, 4)).astype(np.float32)
        columns[tf] = [f"f{i}" for i in range(4)]
        ts[tf] = (np.arange(rows) + 1) * step * 8640
        pos[tf] = np.minimum(np.arange(n) // step, rows - 1)
    y = rng.normal(0, 1, (n, 5)).astype(np.float32) + (3 * frames["5m"][:, :1] if signal else 0)
    if vol:  # Schwankung wandert langsam und ist in rv sichtbar, wie bei echten Kursen
        level = np.cumsum(rng.normal(0, 0.03, n))
        y = y * np.exp(level)[:, None]
        rv = np.stack([level + rng.normal(0, 0.1, n)] * 3, axis=1).astype(np.float32)
    else:
        rv = rng.normal(0, 0.1, (n, 3)).astype(np.float32)
    date = ts["5m"] // 86400
    label_end = date[:, None] + np.array(list(DAYS.values()))
    keep = np.flatnonzero((pos["5m"] >= 31) & (pos["1D"] >= 15))
    return Ticker("X", frames, columns, ts, {tf: p[keep] for tf, p in pos.items()}, date[keep], label_end[keep],
                  y[keep].astype(np.float32), rv[keep])


def quick_bundle(signal, vol=False):
    bundle = Bundle([synthetic(signal, vol=vol)], START, HOLDOUT, windows=WINDOWS, horizon_days=DAYS, select_days=200)
    bundle.set_fold(START, END)
    return bundle


def run_model(kind, bundle, epochs):
    model, selector = fit(kind, bundle, bundle.train_idx(), kind, lr=2e-3, epochs=epochs, checks=4, patience=6, log=lambda _: None)
    output, _ = fold_output(selector, model, bundle)
    return skill_scores(output), selector


def test_cuda_is_active():
    assert torch.cuda.is_available()
    print(f"    {torch.cuda.get_device_name(0)}, {torch.cuda.get_device_properties(0).total_memory / 2**30:.0f} GB, "
          f"PyTorch {torch.__version__}")


def test_models_start_on_base_rate():
    bundle = quick_bundle(False)
    idx = bundle.test_idx()[:64]
    for kind in KINDS:
        model = IonNet(kind, bundle.dims, bundle.windows, bundle.base_up, bundle.base_q).to(bundle.device).eval()
        with torch.inference_mode():
            logit, q, _ = model(bundle.batch(idx), bundle.ticker[idx])
        p = torch.sigmoid(logit)
        assert torch.allclose(p, bundle.base_up[0].expand_as(p), atol=1e-4), kind
        assert torch.allclose(q, bundle.base_q[0].expand_as(q), atol=1e-3), kind
        assert (q[..., 0] <= q[..., 1]).all() and (q[..., 1] <= q[..., 2]).all(), kind


def test_all_models_learn_a_real_signal():
    bundle = quick_bundle(True)
    for kind in KINDS:
        tic = time.perf_counter()
        rows, _ = run_model(kind, bundle, 3)
        skills = [r["brier_skill"] for r in rows]
        print(f"    {kind}: Brier Skill bei echtem Signal {min(skills):+.2f} bis {max(skills):+.2f}, {time.perf_counter() - tic:.0f} s")
        assert min(skills) > 0.2, (kind, skills)


def test_models_find_nothing_in_noise():
    bundle = quick_bundle(False)
    for kind in KINDS:
        rows, _ = run_model(kind, bundle, 2)
        skills = [r["brier_skill"] for r in rows]
        print(f"    {kind}: Brier Skill bei reinem Rauschen {min(skills):+.3f} bis {max(skills):+.3f}")
        assert max(skills) < 0.03, (kind, skills)  # Kein Datenleck: Aus Rauschen darf keine Vorhersage entstehen


def test_selector_only_accepts_proven_gains():
    rng = np.random.default_rng(4)
    n = 4000
    mask = np.ones((n, 2), dtype=bool)
    blocks = np.c_[np.arange(n) // 20, np.zeros(n, dtype=np.int64)]  # Horizont 1 hat nur einen einzigen Block
    selector = Selector(np.array([1.0, 0.5]), mask, blocks)
    net = torch.nn.Linear(1, 1)
    base_weight = net.weight.detach().clone()
    base = rng.normal(0.7, 0.2, (n, 2))
    selector.update(base, base + 0.3, net)
    with torch.no_grad():
        net.weight.fill_(5.0)
    # Nur die Spanne von Horizont 0 wird klar besser. Richtung: reines Rauschen um denselben Wert.
    noise = base + rng.normal(0, 0.2, (n, 2))
    selector.update(noise, base + np.array([0.2, 0.3]), net)
    assert selector.which[0, 1] > 0
    assert selector.which[0, 0] == 0
    # Ein einziger Block belegt nichts, auch wenn der Gewinn gross aussieht: Das Ziel bleibt auf der Basis
    with torch.no_grad():
        net.weight.fill_(9.0)
    selector.update(noise, base, net)
    assert selector.which[1, 0] == 0 and selector.which[1, 1] == 0
    assert torch.equal(selector.states[0]["weight"], base_weight)


def test_har_captures_known_volatility():
    bundle = quick_bundle(False, vol=True)
    model, selector = fit("gru", bundle, bundle.train_idx()[:0], "gru", lr=1e-3, epochs=1, checks=1, patience=0, log=lambda _: None)
    rows = skill_scores(fold_output(selector, model, bundle)[0])
    skills = [r["har_skill"] for r in rows]
    print(f"    HAR gegen feste Quantile bei wandernder Schwankung: {min(skills):+.2f} bis {max(skills):+.2f}")
    assert min(skills) > 0.1, skills
    # Ohne Training steht das Modell exakt auf HAR
    assert max(abs(r["pinball_skill"]) for r in rows) < 1e-3


def test_realized_vol_uses_only_the_past():
    ret = np.random.default_rng(5).normal(0, 0.01, 3000).astype(np.float32)
    full = realized_vol(ret)
    part = realized_vol(ret[:2000])
    assert np.allclose(full[:2000], part)
    assert full.shape == (3000, 3) and np.isfinite(full).all()
    doubled = realized_vol(2 * ret)
    assert np.allclose(doubled[2000:] - full[2000:], np.log(2), atol=1e-4)


def test_fold_masks_never_overlap():
    bundle = quick_bundle(False)
    ticker = synthetic(False)
    train, select, test = (m.cpu().numpy() for m in (bundle.mask_train, bundle.mask_select, bundle.mask_test))
    for h, days in enumerate(DAYS.values()):
        select_start = START - days - 200
        # Training: Zielwert bekannt, bevor das Auswahlfenster beginnt
        assert (ticker.label_end[train[:, h], h] < select_start).all()
        # Auswahl: Zielwert bekannt, bevor das Testjahr beginnt
        assert (ticker.label_end[select[:, h], h] < START).all()
        assert (ticker.date[select[:, h]] >= select_start).all()
        # Test: nur das Testjahr, und nichts reicht in die unangetastete Zeit
        assert (ticker.date[test[:, h]] >= START).all() and (ticker.date[test[:, h]] < END).all()
        assert (ticker.label_end[test[:, h], h] < HOLDOUT).all()
        assert train[:, h].sum() > 1000 and select[:, h].sum() > 1000 and test[:, h].sum() > 1000
    # Die Skalierung nutzt nur Daten vor dem ersten Testjahr; alles ist geklemmt
    assert bundle.x["5m"].abs().max().item() <= 5


def test_real_data_has_no_lookahead():
    con = connect()
    t = load_ticker(con, "META")
    ts5 = load(con, "META", "5m").index.as_unit("s").asi8
    anchor = ts5[np.searchsorted(ts5, t.ts["5m"][t.pos["5m"]])]
    for tf, w in INPUT.items():
        assert (t.ts[tf][t.pos[tf]] <= anchor).all(), tf
        assert (t.pos[tf] >= w - 1).all(), tf
    folds, holdout = fold_dates(t)
    assert holdout == int(t.date.max()) - HOLDOUT_DAYS and folds[-1][1] == holdout and len(folds) == 5
    assert all(folds[i][1] == folds[i + 1][0] for i in range(4))
    known = np.isfinite(t.y)
    assert (t.label_end[known] > np.repeat(t.date[:, None], 5, axis=1)[known]).all()
    # Das Intraday-Volumen ist verzoegert
    col = t.columns["5m"].index("rel_volume")
    assert np.isnan(t.frames["5m"][:4, col]).all()


def test_make_windows_and_dtw():
    x = np.cumsum(np.random.default_rng(1).normal(0, 1, 500))
    m = ioncore.make_windows(x, 128, LENGTH)
    assert m.shape == (500 - 128 + 1, LENGTH)
    assert np.allclose(np.linalg.norm(m, axis=1), 1, atol=1e-5)
    assert np.allclose(m.mean(axis=1), 0, atol=1e-5)
    flat = ioncore.make_windows(np.ones(100), 32, LENGTH)
    assert (flat == 0).all()
    # Skalen- und Niveau-unabhaengig: 3-fache Amplitude plus Verschiebung ergibt dieselbe Form
    assert np.allclose(ioncore.make_windows(3 * x + 50, 64, LENGTH), ioncore.make_windows(x, 64, LENGTH), atol=1e-4)
    d = ioncore.dtw(m[0], m[:3].copy(), 6)
    assert d[0] < 1e-6 and d[1] > 0


def planted_index():
    rng = np.random.default_rng(2)
    shape = np.sin(np.linspace(0, 6 * np.pi, 64)) * np.linspace(1, 3, 64) * 0.3
    series = {}
    for tf, stretch, place in (("5m", 1, 5000), ("1h", 2, 3000)):
        n = 20000
        logp = np.cumsum(rng.normal(0, 0.001, n))
        wide = np.interp(np.linspace(0, 63, 64 * stretch), np.arange(64), shape)
        logp[place:place + len(wide)] += wide - wide[0]
        logp[place + len(wide):] += wide[-1] - wide[0]
        series[tf] = {"logp": logp, "ts": np.arange(n) * 300, "day": np.arange(n) // 78, "rets": rng.normal(0, 0.01, (n, 5))}
    return MatchIndex(series), shape


def test_planted_pattern_is_found_across_scales():
    index, shape = planted_index()
    found = index.query(shape * 5 + 2, 10 ** 9, candidates=512, k=20)  # andere Amplitude, anderes Niveau
    assert found.iloc[0].score > 0.97, found.iloc[0]
    hits = found[found.score > 0.97]
    assert {"5m", "1h"} <= set(hits.timeframe), hits[["timeframe", "window", "bar", "score"]]
    assert ((hits.timeframe == "5m") & hits.bar.between(5058, 5068)).any()
    assert ((hits.timeframe == "1h") & hits.bar.between(3120, 3135)).any()


def test_matching_never_sees_the_future():
    index, shape = planted_index()
    before = index.query(shape, 2000 * 300, candidates=512, k=20)
    assert before.ts.max() <= 2000 * 300
    assert before.score.max() < 0.9  # Das Muster liegt erst spaeter in den Daten
    # Es zaehlen nur Folgerenditen, die zum Abfragezeitpunkt schon bekannt waren
    summary = summarize(before.assign(day=np.arange(len(before))), query_day=10)
    assert summary["1T"]["n"] == 9  # Tag + 1 < 10
    assert summary["1J"]["n"] == 0


def test_query_is_fast_on_millions():
    n = 4_000_000
    vectors = torch.randn(n, LENGTH, device="cuda")
    vectors /= vectors.norm(dim=1, keepdim=True)
    index = MatchIndex.__new__(MatchIndex)
    index.device, index.vectors = "cuda", vectors
    index.tf_names = ["5m"]
    index.tf, index.window, index.bar = np.zeros(n, dtype=np.int8), np.full(n, 64, dtype=np.int16), np.arange(n)
    index.ts, index.day = np.arange(n, dtype=np.int64), np.arange(n) // 78
    index.ts_gpu = torch.from_numpy(index.ts).to("cuda")
    index.rets = np.zeros((n, 5), dtype=np.float32)
    x = np.cumsum(np.random.default_rng(3).normal(0, 1, 64))
    index.query(x, n)  # Aufwaermen
    tic = time.perf_counter()
    for _ in range(10):
        index.query(x, n)
    ms = (time.perf_counter() - tic) / 10 * 1000
    print(f"    {n:,} Sequenzen: {ms:.0f} ms je Abfrage")
    assert ms < 5000
    del index, vectors
    torch.cuda.empty_cache()


if __name__ == "__main__":
    tests = [f for name, f in list(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print("ok ", test.__name__, flush=True)
    print(f"{len(tests)} Tests bestanden", flush=True)
    exit_now()
