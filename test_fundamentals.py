"""Phase 9: Bilanzlogik ohne Netz. 12-Monats-Gewinn, erste Fassung, Zeitpunkt, Namensprobe, Insider und Modell-Zeitfenster."""
import io
import zipfile

import numpy as np
import pandas as pd

from iontrader.fundamentals import as_of, firm_panel, first_reported, insider_count, mean_ranks, model_scores, parse_insider, same_firm, ttm_series


def row(start, end, val, filed, form="10-Q"):
    return {"start": start, "end": end, "val": val, "filed": filed, "form": form}


def test_first_report_wins_over_later_restatement():
    rows = [row("2020-01-01", "2020-12-31", 100, "2021-02-01", "10-K"), row("2020-01-01", "2020-12-31", 80, "2022-02-01", "10-K")]
    assert first_reported(rows).val.tolist() == [100]


def test_ttm_uses_year_plus_current_minus_last_year():
    rows = [row("2020-01-01", "2020-12-31", 100, "2021-02-01", "10-K"), row("2020-01-01", "2020-03-31", 20, "2020-05-01"), row("2021-01-01", "2021-03-31", 30, "2021-05-01")]
    out = ttm_series(rows)
    assert out.ttm.tolist() == [100, 110], out
    assert out.filed.iloc[1] == pd.Timestamp("2021-05-01")


def test_ttm_skips_a_quarter_without_prior_year():
    rows = [row("2020-01-01", "2020-12-31", 100, "2021-02-01", "10-K"), row("2021-01-01", "2021-03-31", 30, "2021-05-01")]
    assert ttm_series(rows).ttm.tolist() == [100]


def test_value_counts_only_from_the_day_after_filing():
    filed = pd.to_datetime(["2021-02-01"])
    assert np.isnan(as_of(pd.to_datetime(["2021-02-01"]), filed, [5.0])[0])
    assert as_of(pd.to_datetime(["2021-02-02"]), filed, [5.0])[0] == 5.0


def test_stale_value_expires():
    filed = pd.to_datetime(["2021-01-01"])
    assert as_of(pd.to_datetime(["2021-07-01"]), filed, [5.0], max_age=200)[0] == 5.0
    assert np.isnan(as_of(pd.to_datetime(["2021-09-01"]), filed, [5.0], max_age=200)[0])


def test_panel_knows_nothing_before_filing():
    facts = {"ni": [row("2020-01-01", "2020-12-31", 100, "2021-02-01", "10-K")], "assets": [{"end": "2020-12-31", "val": 1000, "filed": "2021-02-01", "form": "10-K"}], "equity": [], "shares": []}
    p = firm_panel(facts, pd.to_datetime(["2021-01-31", "2021-02-26"]))
    assert np.isnan(p["ttm"][0]) and p["ttm"][1] == 100 and p["assets"][1] == 1000, p


def test_name_check_rejects_another_firm_under_the_same_ticker():
    assert same_firm("SVB Financial Group", "SVB FINANCIAL GROUP")
    assert same_firm("Aetna Inc.", "AETNA INC /PA/")
    assert not same_firm("Comcast Corp", "Twitter, Inc.")
    assert not same_firm("", "Inc")


def test_insider_counts_distinct_people_in_the_window_only():
    trades = pd.DataFrame({"filed": pd.to_datetime(["2021-01-10", "2021-01-11", "2021-01-12", "2020-01-01", "2021-03-01"]), "owner": ["a", "a", "b", "c", "d"]})
    out = insider_count(trades, pd.to_datetime(["2021-02-01", "2019-01-01"]))
    assert out[0] == 2 and np.isnan(out[1]), out


def test_insider_archive_keeps_open_market_buys_of_form_four():
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as z:
        z.writestr("NONDERIV_TRANS.tsv", "ACCESSION_NUMBER\tTRANS_CODE\nA\tP\nB\tS\nC\tP\n")
        z.writestr("SUBMISSION.tsv", "ACCESSION_NUMBER\tFILING_DATE\tISSUERCIK\tDOCUMENT_TYPE\nA\t10-JAN-2021\t123\t4\nB\t10-JAN-2021\t123\t4\nC\t10-JAN-2021\t123\t4/A\n")
        z.writestr("REPORTINGOWNER.tsv", "ACCESSION_NUMBER\tRPTOWNERCIK\nA\t9\nB\t8\nC\t7\n")
    data.seek(0)
    out = parse_insider(zipfile.ZipFile(data))
    assert out.cik.tolist() == [123] and out.owner.tolist() == ["9"], out


def test_mean_ranks_needs_all_inputs():
    a = pd.DataFrame([[1.0, 2.0]])
    b = pd.DataFrame([[np.nan, 2.0]])
    out = mean_ranks([a, b])
    assert np.isnan(out.iloc[0, 0]) and np.isfinite(out.iloc[0, 1])


def test_model_learns_only_known_outcomes_and_finds_a_planted_signal():
    days = pd.bdate_range("2017-01-02", periods=900, tz="UTC")
    rng = np.random.default_rng(0)
    k = 120
    signal = rng.normal(size=(900, k))
    returns = rng.normal(0, 0.01, (900, k))
    # Das Signal von heute treibt die Renditen der naechsten Tage
    returns[1:] += 0.01 * signal[:-1]
    held = pd.DataFrame(signal, index=days).rolling(21).mean().shift(1)  # Monatsweise ruhig, damit das Ziel lernbar ist
    returns = rng.normal(0, 0.005, (900, k)) + 0.02 * held.fillna(0).to_numpy()
    close = pd.DataFrame(100 * np.exp(returns.cumsum(0)), index=days)
    ends = np.arange(25, 880, 21)
    factors = {"plant": pd.DataFrame(np.where(np.isin(np.arange(900)[:, None], ends), held.shift(-1).to_numpy(), np.nan), index=days, columns=close.columns)}
    factors["plant"].iloc[-1] = held.iloc[-1]
    scores, importance = model_scores(factors, close, np.ones((900, k), dtype=bool), ends)
    used = ends[days[ends] >= pd.Timestamp("2019-01-01", tz="UTC")]
    assert len(used) and np.isnan(scores.to_numpy()[ends[days[ends] < pd.Timestamp("2019-01-01", tz="UTC")]]).all(), "Vor 2019 kein Einsatz"
    future = (close.shift(-21) / close - 1).to_numpy()
    corr = np.mean([pd.Series(scores.to_numpy()[t]).corr(pd.Series(future[t]), method="spearman") for t in used[:-2]])
    assert corr > 0.2, corr
    assert importance["plant"] == 1


if __name__ == "__main__":
    tests = [f for name, f in list(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print("ok ", test.__name__, flush=True)
    print(f"{len(tests)} Tests bestanden", flush=True)
