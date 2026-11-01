"""Phase 9: Bilanzdaten und Insiderkaeufe aus SEC EDGAR. Jede Zahl zaehlt erst ab ihrer ersten Veroeffentlichung."""
import io
import os
import pickle
import re
import time
import zipfile
from datetime import datetime

import numpy as np
import pandas as pd
import requests

from . import ROOT, ranking
from .ranking import BENCHMARK, KEEP, MONTH, RATE_SYMBOL, START, TOP, factor_scores, month_ends, select
from .store import connect, load, replace_rows
from .train import REPORTS

FACTS_FILE = ROOT / "data" / "sec_facts.pkl"
INSIDER_FILE = ROOT / "data" / "sec_insider.pkl"
CIK_FILE = ROOT / "data" / "sec_cik.pkl"
RAW_FILE = ROOT / "data" / "universe_raw.pkl"
SPACING = 0.125  # Hoechstens 8 Abfragen je Sekunde
CONCEPTS = {"ni": ("NetIncomeLoss", "ProfitLoss"), "assets": ("Assets",), "equity": ("StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest")}
FORMS = ("10-K", "10-Q")
STALE_SHARES, STALE_SURPRISE, INSIDER_DAYS = 200, 92, 180
MODEL_START = pd.Timestamp("2019-01-01", tz="UTC")
TREES = 200
MODEL = {"objective": "regression", "learning_rate": 0.05, "num_leaves": 15, "min_data_in_leaf": 100, "bagging_fraction": 0.8, "bagging_freq": 1, "feature_fraction": 0.8, "seed": 0, "verbose": -1}
STOP = {"inc", "corp", "corporation", "co", "company", "ltd", "plc", "llc", "the", "group", "holdings", "holding", "and", "lp"}


def sec_get(url, session=None):
    """Mit Kontakt im Absender, wie die SEC es verlangt. Die Adresse steht nur in .env."""
    time.sleep(SPACING)
    agent = {"User-Agent": f"IonTrader research {os.environ['SEC_CONTACT']}", "Accept-Encoding": "gzip, deflate"}
    return (session or requests).get(url, headers=agent, timeout=120)


# ---------------------------------------------------------------------------
# Firmen zuordnen
# ---------------------------------------------------------------------------

def name_key(name):
    """Firmenname ohne Rechtsform und Satzzeichen, zum Vergleich."""
    words = re.sub(r"[^a-z0-9 ]", " ", str(name).lower()).split()
    return [w for w in words if w not in STOP]


def same_firm(a, b):
    """Gleiche Firma, wenn das erste bedeutsame Wort gleich ist. Fremde Firmen unter demselben Ticker fallen so heraus."""
    x, y = name_key(a), name_key(b)
    return bool(x and y and x[0] == y[0])


def map_ciks(symbols, current, changes, session, log):
    """Symbol -> CIK. Heutige Mitglieder aus Wikipedia; fruehere ueber Ticker oder Namensliste, immer mit Namensprobe."""
    out = {s: int(c) for s, c in zip(current.Symbol, current.CIK) if s in symbols}
    names = {}
    for row in changes.itertuples():
        if pd.notna(row.rem) and row.rem not in names and pd.notna(row.rem_name):
            names[row.rem] = row.rem_name
        if pd.notna(row.add) and row.add not in names and pd.notna(row.add_name):
            names[row.add] = row.add_name
    active = {v["ticker"]: (int(v["cik_str"]), v["title"]) for v in sec_get("https://www.sec.gov/files/company_tickers.json", session).json().values()}
    open_ = []
    for s in symbols:
        if s in out:
            continue
        known = active.get(s) or active.get(s.replace(".", "-"))
        if known and s in names and same_firm(known[1], names[s]):
            out[s] = known[0]
            continue
        text = sec_get(f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={s}&type=10-K&dateb=&owner=include&count=1&output=atom", session).text
        cik, title = re.search(r"<cik>(\d+)</cik>", text), re.search(r"<conformed-name>(.*?)</conformed-name>", text)
        if cik and title and s in names and same_firm(title.group(1), names[s]):
            out[s] = int(cik.group(1))
        elif s in names:
            open_.append(s)
    log(f"Zuordnung: {len(out)} Firmen, offen nach Ticker {len(open_)}")
    if open_:
        lookup = sec_get("https://www.sec.gov/Archives/edgar/cik-lookup-data.txt", session).content.decode("latin-1")
        wanted = {}
        for s in open_:
            wanted.setdefault(" ".join(name_key(names[s])), []).append(s)
        for line in lookup.splitlines():
            parts = line.rsplit(":", 2)
            if len(parts) == 3:
                key = " ".join(name_key(parts[0]))
                for s in wanted.get(key, ()):
                    out.setdefault(s, int(parts[1]))  # ponytail: Bei Namensgleichheit gilt der erste Treffer, die Faktenpruefung sortiert leere Firmen aus
        log(f"Zuordnung nach Namen: {len(out)} Firmen")
    return out


# ---------------------------------------------------------------------------
# Fakten
# ---------------------------------------------------------------------------

def fetch_facts(ciks, session, log):
    """Nur die benoetigten Kennzahlen je Firma, zwischengespeichert. Ein Abbruch verliert nichts."""
    cache = pickle.loads(FACTS_FILE.read_bytes()) if FACTS_FILE.exists() else {}
    todo = sorted(set(ciks) - set(cache))
    for n, cik in enumerate(todo):
        response = sec_get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json", session)
        if response.status_code == 404:
            cache[cik] = {}
        elif response.ok:
            facts = response.json().get("facts", {})
            gaap = facts.get("us-gaap", {})
            kept = {}
            for key, names in CONCEPTS.items():
                rows = []
                for name in names:  # Mehrere Namen je Kennzahl: alle zusammen, je Zeitraum gewinnt die erste Meldung
                    rows += gaap.get(name, {}).get("units", {}).get("USD", [])
                kept[key] = [{k: r.get(k) for k in ("start", "end", "val", "filed", "form")} for r in rows if r.get("form") in FORMS]
            shares = facts.get("dei", {}).get("EntityCommonStockSharesOutstanding", {}).get("units", {}).get("shares", [])
            kept["shares"] = [{k: r.get(k) for k in ("end", "val", "filed", "form")} for r in shares]
            cache[cik] = kept
        if n % 50 == 49 or n == len(todo) - 1:
            FACTS_FILE.write_bytes(pickle.dumps(cache))
            log(f"Fakten: {n + 1} von {len(todo)}")
    return cache


def first_reported(rows):
    """Je Zeitraum die erste Meldung. So bleiben spaetere Korrekturen ausserhalb des Tests."""
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    for column in ("start", "end", "filed"):
        if column in frame:
            frame[column] = pd.to_datetime(frame[column])
    keys = ["start", "end"] if "start" in frame else ["end"]
    return frame.sort_values("filed", kind="stable").drop_duplicates(keys).sort_values("end").reset_index(drop=True)


def ttm_series(rows):
    """Gewinn der letzten 12 Monate: Geschaeftsjahr direkt, sonst letztes Jahr + laufend - gleicher Zeitraum im Vorjahr."""
    frame = first_reported(rows)
    columns = ["end", "filed", "ttm"]
    if frame.empty:
        return pd.DataFrame(columns=columns)
    frame["days"] = (frame.end - frame.start).dt.days
    annual = frame[frame.days.between(350, 380)]
    out = [(r.end, r.filed, r.val) for r in annual.itertuples()]
    for r in frame[frame.days.between(80, 300)].itertuples():
        year = annual[(annual.end - r.start + pd.Timedelta(days=1)).abs() <= pd.Timedelta(days=7)]
        before = frame[((frame.end - (r.end - pd.Timedelta(days=365))).abs() <= pd.Timedelta(days=10)) & ((frame.days - r.days).abs() <= 10)]
        if len(year) and len(before):
            out.append((r.end, max(r.filed, year.filed.iloc[-1]), year.val.iloc[-1] + r.val - before.val.iloc[-1]))
    result = pd.DataFrame(out, columns=columns).sort_values("end").drop_duplicates("end", keep="last").reset_index(drop=True)
    return result


def as_of(ends, available, values, max_age=None):
    """Der zuletzt bekannte Wert je Stichtag. Veroeffentlicht am Tag d zaehlt erst ab d+1."""
    order = np.argsort(available, kind="stable")
    available, values = np.asarray(available, dtype="datetime64[ns]")[order], np.asarray(values, dtype=float)[order]
    position = np.searchsorted(available, np.asarray(ends, dtype="datetime64[ns]"), side="left") - 1
    out = np.where(position >= 0, values[np.maximum(position, 0)], np.nan)
    if max_age is not None:
        age = (np.asarray(ends, dtype="datetime64[ns]") - available[np.maximum(position, 0)]) / np.timedelta64(1, "D")
        out = np.where(age <= max_age, out, np.nan)
    return out


def firm_panel(facts, ends):
    """Alle Kennzahlen einer Firma je Stichtag. Filed-Daten kommen ohne Zeitzone, die Stichtage auch."""
    out = {name: np.full(len(ends), np.nan) for name in ("ttm", "assets", "equity", "shares", "growth", "surprise")}
    ttm = ttm_series(facts.get("ni", []))
    assets = first_reported(facts.get("assets", []))
    if not ttm.empty:
        ttm = ttm.sort_values("filed", kind="stable")
        out["ttm"] = as_of(ends, ttm.filed, ttm.ttm)
    if not assets.empty:
        out["assets"] = as_of(ends, assets.filed, assets.val)
        ago = [assets.val[(assets.end - (e - pd.Timedelta(days=365))).abs() <= pd.Timedelta(days=30)].iloc[-1] if ((assets.end - (e - pd.Timedelta(days=365))).abs() <= pd.Timedelta(days=30)).any() else np.nan for e in assets.end]
        growth = assets.val.to_numpy(dtype=float) / np.array(ago, dtype=float) - 1
        ok = np.isfinite(growth)
        if ok.any():
            out["growth"] = as_of(ends, assets.filed[ok], growth[ok])
        if not ttm.empty:
            by_end = ttm.sort_values("end")
            change = by_end.ttm.diff().to_numpy(dtype=float)
            gap = by_end.end.diff().dt.days.to_numpy(dtype=float)
            size = np.interp(by_end.end.astype("int64"), assets.end.astype("int64"), assets.val.to_numpy(dtype=float))
            use = np.isfinite(change) & (gap >= 80) & (gap <= 100)
            if use.any():
                out["surprise"] = as_of(ends, by_end.filed[use], (change / size)[use], STALE_SURPRISE)
    equity = first_reported(facts.get("equity", []))
    if not equity.empty:
        out["equity"] = as_of(ends, equity.filed, equity.val)
    shares = first_reported(facts.get("shares", []))
    if not shares.empty:
        out["shares"] = as_of(ends, shares.filed, shares.val, STALE_SHARES)
    return out


# ---------------------------------------------------------------------------
# Insider
# ---------------------------------------------------------------------------

def quarters(first=(2015, 1)):
    now = datetime.now()
    y, q = first
    while (y, q) < (now.year, (now.month - 1) // 3 + 1):
        yield y, q
        y, q = (y + 1, 1) if q == 4 else (y, q + 1)


def parse_insider(archive):
    """Offene Marktkaeufe aus einem Quartalsarchiv: Firma, Tag und Insider."""
    read = lambda name, cols: pd.read_csv(archive.open(name), sep="\t", usecols=cols, dtype=str)
    buys = read("NONDERIV_TRANS.tsv", ["ACCESSION_NUMBER", "TRANS_CODE"])
    buys = buys[buys.TRANS_CODE == "P"]
    sub = read("SUBMISSION.tsv", ["ACCESSION_NUMBER", "FILING_DATE", "ISSUERCIK", "DOCUMENT_TYPE"])
    sub = sub[sub.DOCUMENT_TYPE == "4"]
    owner = read("REPORTINGOWNER.tsv", ["ACCESSION_NUMBER", "RPTOWNERCIK"])
    frame = buys.merge(sub, on="ACCESSION_NUMBER").merge(owner, on="ACCESSION_NUMBER")
    return pd.DataFrame({"cik": frame.ISSUERCIK.astype(int), "filed": pd.to_datetime(frame.FILING_DATE, format="%d-%b-%Y"), "owner": frame.RPTOWNERCIK}).drop_duplicates()


def fetch_insider(session, log):
    parts = pickle.loads(INSIDER_FILE.read_bytes()) if INSIDER_FILE.exists() else {}
    for y, q in quarters():
        if (y, q) in parts:
            continue
        response = sec_get(f"https://www.sec.gov/files/structureddata/data/insider-transactions-data-sets/{y}q{q}_form345.zip", session)
        if response.ok:
            parts[(y, q)] = parse_insider(zipfile.ZipFile(io.BytesIO(response.content)))
            INSIDER_FILE.write_bytes(pickle.dumps(parts))
            log(f"Insider {y} Q{q}: {len(parts[(y, q)]):,} Kaeufe")
        else:
            log(f"Insider {y} Q{q}: {response.status_code}")
    return pd.concat(parts.values())


def insider_count(trades, ends, window=INSIDER_DAYS):
    """Verschiedene Insider mit Kauf im Fenster vor dem Stichtag. Ohne Kauf NaN, die Aktie nimmt dann nicht teil."""
    out = np.full(len(ends), np.nan)
    days = trades.filed.to_numpy(dtype="datetime64[ns]")
    owners = trades.owner.to_numpy()
    for i, end in enumerate(np.asarray(ends, dtype="datetime64[ns]")):
        seen = (days < end) & (days >= end - np.timedelta64(window, "D"))
        if seen.any():
            out[i] = len(set(owners[seen]))
    return out


# ---------------------------------------------------------------------------
# Faktoren
# ---------------------------------------------------------------------------

def ingest_raw(symbols, log):
    """Unbereinigte Schlusskurse, nur fuer den Marktwert."""
    from alpaca.data.enums import Adjustment
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame

    client = StockHistoricalDataClient(os.environ["ALPACA_API_KEY"], os.environ["ALPACA_SECRET_KEY"])
    end = pd.Timestamp.now(tz="UTC") - pd.Timedelta(minutes=16)
    parts = []
    for i in range(0, len(symbols), 100):
        parts.append(client.get_stock_bars(StockBarsRequest(symbol_or_symbols=symbols[i:i + 100], timeframe=TimeFrame.Day, adjustment=Adjustment.RAW, start=pd.Timestamp("2016-01-01", tz="UTC"), end=end)).df)
        log(f"Rohkurse: {min(i + 100, len(symbols))} von {len(symbols)}")
    frame = pd.concat(parts).reset_index()[["symbol", "timestamp", "close"]]
    frame.to_pickle(RAW_FILE)
    return frame


def build_factors(days, close, raw, facts, ciks, trades):
    """Faktoren fuer Monatsenden und den letzten Tag, in Tage-mal-Aktien-Form. NaN ausserhalb der Stichtage."""
    positions = np.r_[month_ends(days), len(days) - 1]
    stamps = days[positions].tz_localize(None).normalize()
    names = ("Profitabilitaet", "Gewinnrendite", "Buchwert", "Geringes Bilanzwachstum", "Gewinnueberraschung", "Insiderkaeufe")
    frames = {n: np.full(close.shape, np.nan) for n in names}
    grouped = dict(tuple(trades.groupby("cik")))
    raw_at = raw.reindex(days)[close.columns].to_numpy(dtype=float)[positions]
    covered = np.zeros(close.shape[1], dtype=bool)
    for j, symbol in enumerate(close.columns):
        cik = ciks.get(symbol)
        if cik is None or not facts.get(cik):
            continue
        p = firm_panel(facts[cik], stamps)
        covered[j] = np.isfinite(p["ttm"]).any()
        cap = raw_at[:, j] * p["shares"]
        cap = np.where(cap > 0, cap, np.nan)
        assets = np.where(p["assets"] > 0, p["assets"], np.nan)
        frames["Profitabilitaet"][positions, j] = p["ttm"] / assets
        frames["Gewinnrendite"][positions, j] = p["ttm"] / cap
        frames["Buchwert"][positions, j] = p["equity"] / cap
        frames["Geringes Bilanzwachstum"][positions, j] = -p["growth"]
        frames["Gewinnueberraschung"][positions, j] = p["surprise"]
        if cik in grouped:
            frames["Insiderkaeufe"][positions, j] = insider_count(grouped[cik], stamps)
    as_frame = {n: pd.DataFrame(v, index=days, columns=close.columns) for n, v in frames.items()}
    return as_frame, covered, positions


def model_scores(factors, close, is_member, ends):
    """LightGBM auf den Raengen, je Januar neu. Gelernt wird nur, was vorher feststand; davor kein Wert."""
    import lightgbm as lgb

    names = list(factors)
    n, k = close.shape
    ranks = {name: factors[name].rank(axis=1, pct=True).to_numpy() for name in names}
    future = (close.shift(-MONTH) / close - 1).to_numpy()
    days = close.index
    scores = np.full((n, k), np.nan)
    active = ends[days[ends] >= MODEL_START]
    feature = lambda t: np.column_stack([ranks[name][t] for name in names])
    target_rank = lambda t: pd.Series(future[t]).where(is_member[t]).rank(pct=True).to_numpy()
    model, trained_year = None, None
    importance = np.zeros(len(names))
    for t in active:
        if days[t].year != trained_year:
            usable = ends[ends + MONTH < t]  # Das Ergebnis muss am Lerntag bekannt sein
            x = np.vstack([feature(s)[is_member[s]] for s in usable])
            y = np.concatenate([target_rank(s)[is_member[s]] for s in usable])
            ok = np.isfinite(y)
            model = lgb.train(MODEL, lgb.Dataset(x[ok], y[ok], feature_name=[f"f{i}" for i in range(len(names))]), TREES)
            trained_year = days[t].year
            importance += model.feature_importance()
        scores[t] = model.predict(feature(t))
    latest = n - 1
    scores[latest] = model.predict(feature(latest))
    return pd.DataFrame(scores, index=days, columns=close.columns), dict(zip(names, (importance / max(importance.sum(), 1)).tolist()))


def make_builder(raw, facts, ciks, trades, store):
    """Baut die Zielgewichte aller Strategien aus GAMEPLAN 9.5 und 9.6."""
    def builder(days, close, members):
        symbols = close.columns.tolist()
        fund, covered, _ = build_factors(days, close, raw, facts, ciks, trades)
        price, suspect = factor_scores(close)
        fund["Kombination"] = mean_ranks([fund["Profitabilitaet"], fund["Gewinnrendite"], price["Momentum 12-1"]])
        is_member = np.column_stack([members.get(s, np.zeros(len(days), dtype=bool)) for s in symbols])
        ends = month_ends(days)
        ends = ends[days[ends] >= START]
        features = {**{n: f for n, f in fund.items() if n != "Kombination"}, **price}
        model, importance = model_scores(features, close, is_member, ends)
        fund["Modell"] = model
        store.update({"fund": fund, "price": price, "suspect": suspect, "covered": covered, "importance": importance, "is_member": is_member})
        k = len(symbols)
        spy = symbols.index(BENCHMARK)
        targets = {name: {} for name in fund}
        held = {name: np.zeros(k, dtype=bool) for name in fund}
        tradable = close.notna().to_numpy()
        bad = suspect.to_numpy()
        for t in ends:
            eligible = is_member[t] & tradable[t] & ~bad[t]
            for name, frame in fund.items():
                if name == "Modell" and days[t] < MODEL_START:
                    weight = np.zeros(k)
                    weight[spy] = 1.0
                else:
                    weight = select(frame.to_numpy()[t], eligible, held[name])
                targets[name][t], held[name] = weight, weight > 0
        return targets, fund, is_member, ends
    return builder


def mean_ranks(frames):
    return sum(f.rank(axis=1, pct=True) for f in frames) / len(frames)


def coverage_rows(days, close, members, fund, ends):
    """Anteil der Mitglieder mit Wert je Faktor, getrennt nach heute noch gehandelt und verschwunden."""
    is_member = np.column_stack([members.get(s, np.zeros(len(days), dtype=bool)) for s in close.columns])
    gone = close.iloc[-1].isna().to_numpy()
    rows = []
    for name, frame in fund.items():
        has = frame.notna().to_numpy()[ends]
        member = is_member[ends]
        rows.append({"faktor": name, "alle": float(has[member].mean()), "verschwunden": float(has[member & gone[None, :]].mean())})
    return pd.DataFrame(rows)


def today_rows(fund, days, close, members, suspect):
    t = len(days) - 1
    member = pd.Series({s: members.get(s, np.zeros(len(days), dtype=bool))[t] for s in close.columns})
    rows = []
    for name, frame in fund.items():
        score = frame.iloc[t][member & ~suspect.iloc[t]].dropna()
        ranks = score.rank(ascending=False, method="first").astype(int)
        rows += [{"aktie": symbol, "faktor": name, "rang": int(rank), "von": len(ranks), "stand": str(days[t].date())} for symbol, rank in ranks.items()]
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Bericht und Lauf
# ---------------------------------------------------------------------------

def write_report(results, tests, ics, window, coverage, importance, n_ciks, n_symbols):
    p = ranking._p
    start, end = (d.date() for d in window)
    names = {"rendite": "Rendite p. a.", "sharpe": "Sharpe"}
    value = lambda v, metric: p(v) if metric == "rendite" else f"{v:+.2f}"
    lines = ["# S&P 500: Phase-9-Report", "", f"Stand {datetime.now():%Y-%m-%d %H:%M}. Statistische Auswertung, keine Anlageberatung. Es wurden keine Orders gesendet.", "",
             f"Zeitraum {start} bis {end}. Regeln wie Phase 8 (beste {TOP}, gehalten bis außerhalb der besten {KEEP}), jede Bilanzzahl erst ab dem Tag nach ihrer ersten Veröffentlichung. Alle Regeln standen vor dem ersten Lauf fest (GAMEPLAN, Phase 9).", "",
             f"**Zuordnung:** {n_ciks} von {n_symbols} Symbolen mit SEC-Kennung.", "", "| Faktor | Mitglieder mit Wert | Davon verschwundene Firmen |", "|---|---:|---:|"]
    lines += [f"| {r['faktor']} | {p(r['alle'], False)} | {p(r['verschwunden'], False)} |" for r in coverage.to_dict("records")]
    lines += ["", "## Ergebnis", "", "| Strategie | Rendite p. a. | Nach Steuer p. a. | Endwert nach Steuer | Sharpe | Schwankung | Max. Einbruch | Investiert | Orders | Kosten $ | Mit 10,000 $ Start |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    lines += [f"| {r['strategie']} | {p(r['rendite'])} | {p(r['nach_steuer'])} | {r['endwert']:,.0f} $ | {r['sharpe']:.2f} | {p(r['schwankung'], False)} | {p(r['drawdown'])} | {p(r['investiert'], False)} | {r['orders']:,} | {r['kosten']:,.0f} | {p(r['klein'])} |" for r in results.to_dict("records")]
    lines += ["", "## Belegt besser als SPY?", "", f"Vor Steuern, nach Kosten. In Klammern das 95 %-Intervall. q ist korrigiert über alle {len(tests)} Tests. Belegt heißt q < 0,05 und positiv in 2017–2021 und in 2022–2026.", "",
              "| Strategie | Kennzahl | Differenz | 2017–2021 | 2022–2026 | q | Belegt |", "|---|---|---:|---:|---:|---:|---|"]
    lines += [f"| {r['strategie']} | {names[r['kennzahl']]} | {value(r['diff'], r['kennzahl'])} ({value(r['low'], r['kennzahl'])} bis {value(r['high'], r['kennzahl'])}) | {value(r['frueh'], r['kennzahl'])} | {value(r['spaet'], r['kennzahl'])} | {r['q']:.3f} | {'ja' if r['belegt'] else 'nein'} |" for r in tests.to_dict("records")]
    lines += ["", "## Rang-IC", "", "Rangkorrelation gegen die Rendite der folgenden 21 Handelstage, je Monatsende. Beim Modell zählen die Monate ab 2019.", "", "| Faktor | Ø IC | t | Monate |", "|---|---:|---:|---:|"]
    lines += [f"| {r['faktor']} | {r['ic']:+.3f} | {r['t']:+.1f} | {r['monate']} |" for r in ics.to_dict("records")]
    lines += ["", "## Was das Modell nutzt", "", "| Merkmal | Anteil der Aufteilungen |", "|---|---:|"]
    lines += [f"| {name} | {p(share, False)} |" for name, share in sorted(importance.items(), key=lambda item: -item[1])]
    won = tests[tests.belegt == 1]
    lines += ["", "## Was das heißt", "", f"Belegt: {', '.join(sorted(set(won.strategie))) if len(won) else 'keine Strategie'}.", "",
              "**Grenzen:** Firmen ohne Zuordnung nehmen nicht teil. Bei Firmen mit mehreren Aktienklassen wie META, GOOGL und BRK.B meldet die SEC-Quelle keine Gesamtzahl an Aktien, sie fehlen deshalb bei Gewinnrendite und Buchwert. Firmen mit neuer SEC-Kennung nach einem Umbau haben nur kurze Historie, etwa XOM. Die Insiderdaten enden im März 2026, weil die SEC die Quartale danach noch nicht bereitstellt; die Insider-Strategie ist deshalb am Ende teils in Cash. Erste Fassungen stammen aus den heute abrufbaren Meldungen; Fakten vor der XBRL-Pflicht fehlen. Keine Bereinigung nach Branchen, Banken haben also strukturell niedrige Profitabilität. Ein Zeitraum mit starkem Markt. Beträge in Dollar ohne Wechselkurs.", ""]
    path = REPORTS / "SP500_phase9.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def run(con=None, log=None):
    log = log or (lambda text: print(text, flush=True))
    con = con or connect()
    session = requests.Session()
    current_symbols, changes = ranking.fetch_members()
    current = pd.read_html(io.StringIO(requests.get(ranking.WIKI + "List_of_S%26P_500_companies", headers=ranking.AGENT, timeout=60).text))[0]
    frame = pd.read_pickle(ranking.PRICES)
    days, open_, close = ranking.to_matrix(frame)
    members = ranking.membership(current_symbols, changes, days)
    symbols = close.columns.tolist()
    raw_frame = pd.read_pickle(RAW_FILE) if RAW_FILE.exists() else ingest_raw(symbols, log)
    raw = raw_frame.assign(day=pd.to_datetime(raw_frame.timestamp, utc=True).dt.normalize()).drop_duplicates(["symbol", "day"]).pivot(index="day", columns="symbol", values="close").reindex(columns=symbols)
    ciks = pickle.loads(CIK_FILE.read_bytes()) if CIK_FILE.exists() else map_ciks(symbols, current, changes, session, log)
    CIK_FILE.write_bytes(pickle.dumps(ciks))
    facts = fetch_facts(ciks.values(), session, log)
    trades = fetch_insider(session, log)
    rate_frame = load(con, RATE_SYMBOL, "1D").close
    rate = rate_frame.to_numpy(dtype=float)[np.clip(np.searchsorted(rate_frame.index.normalize(), days, side="right") - 1, 0, len(rate_frame) - 1)] / 100
    store = {}
    results, tests, ics, _, window, _ = ranking.evaluate(days, open_, close, members, rate, set(current_symbols), make_builder(raw, facts, ciks, trades, store))
    ends = month_ends(days)
    ends = ends[days[ends] >= START]
    coverage = coverage_rows(days, close, members, store["fund"], ends)
    for table, data in (("fund_result", results), ("fund_test", tests), ("fund_ic", ics), ("fund_today", today_rows(store["fund"], days, close, members, store["suspect"]))):
        replace_rows(con, table, "SP500", data)
    path = write_report(results, tests, ics, window, coverage, store["importance"], len(ciks), len(symbols))
    log(f"Report: {path}")
    log(coverage.to_string())
    log(results[["strategie", "rendite", "nach_steuer", "sharpe", "drawdown", "orders", "klein"]].to_string())
    log(tests[["strategie", "kennzahl", "diff", "low", "high", "frueh", "spaet", "q", "belegt"]].to_string())
    log(ics.to_string())
    log(str(store["importance"]))
    return results
