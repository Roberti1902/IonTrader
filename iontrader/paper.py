"""Phase 10: Musterdepot ohne echtes Geld. Monatliche Entscheidungen werden eingefroren und erst danach bewertet."""
import hashlib
import io
import pickle
import subprocess
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import requests

from . import ROOT, fundamentals, ingest, ranking
from .backtest import stats
from .fundamentals import mean_ranks
from .ranking import BENCHMARK, CAPITAL, RATE_SYMBOL, TAX, factor_scores, month_ends, select
from .store import connect, load, replace_rows
from .train import REPORTS

STRATEGIES = ("Profitabilitaet", "Kombination")
PRICES = ROOT / "data" / "paper_prices.pkl"
LOG = REPORTS / "paper_log.txt"
REPORT = REPORTS / "PAPER.md"
MIN_MONTHS = 12
TABLE = "paper_decision"


def month_of(day):
    return f"{day.year}-{day.month:02d}"


def latest_month_end(days, now):
    """Letzter abgeschlossener Monat: Monatsende mit Folgetag im Kalender, oder der letzte Bar, wenn sein Monat vorbei ist."""
    ends = month_ends(days)
    if (days[-1].year, days[-1].month) < (now.year, now.month):
        return len(days) - 1
    return int(ends[-1]) if len(ends) else None


def fingerprint(month, strategy, symbols):
    return hashlib.sha256(f"{month}|{strategy}|{','.join(sorted(symbols))}".encode()).hexdigest()


def load_decisions(con):
    if not con.execute("SELECT 1 FROM sqlite_master WHERE name=?", (TABLE,)).fetchone():
        return pd.DataFrame(columns=["monat", "strategie", "aktie", "gewicht", "signaltag", "erstellt"])
    return pd.read_sql_query(f"SELECT * FROM {TABLE}", con)


def freeze(con, rows, log_path=LOG):
    """Nur anhaengen. Liegt der Monat schon vor, bleibt er, wie er ist. Liefert die neu eingefrorenen Strategien."""
    known = set(map(tuple, load_decisions(con)[["monat", "strategie"]].drop_duplicates().to_numpy()))
    done = []
    for (month, strategy), group in rows.groupby(["monat", "strategie"]):
        if (month, strategy) in known:
            continue
        with con:
            group.to_sql(TABLE, con, if_exists="append", index=False)
        with open(log_path, "a", encoding="utf-8") as out:
            out.write(f"{month} {strategy} {len(group)} Aktien {group.erstellt.iloc[0]} sha256 {fingerprint(month, strategy, group.aktie)}\n")
        done.append((month, strategy))
    return done


def choose(close, raw, facts, ciks, members, days, held):
    """Die Auswahl zum letzten Tag von close. Spaetere Daten sind vorher abgeschnitten."""
    fund, _, _ = fundamentals.build_factors(days, close, raw, facts, ciks, pd.DataFrame({"cik": pd.Series(dtype=int), "filed": pd.Series(dtype="datetime64[ns]"), "owner": pd.Series(dtype=str)}))
    price, suspect = factor_scores(close)
    scores = {"Profitabilitaet": fund["Profitabilitaet"], "Kombination": mean_ranks([fund["Profitabilitaet"], fund["Gewinnrendite"], price["Momentum 12-1"]])}
    t = len(days) - 1
    symbols = close.columns.to_numpy()
    member = np.array([members.get(s, np.zeros(len(days), dtype=bool))[t] for s in symbols])
    eligible = member & close.iloc[t].notna().to_numpy() & ~suspect.iloc[t].to_numpy()
    out = {}
    for name in STRATEGIES:
        weight = select(scores[name].iloc[t].to_numpy(), eligible, np.isin(symbols, list(held.get(name, ()))))
        out[name] = dict(zip(symbols[weight > 0], weight[weight > 0]))
    return out


def decide(con, position_day, session, log):
    """Frische Kurse und Bilanzen, dann die Entscheidung des Monats."""
    current_symbols, changes = ranking.fetch_members()
    current = pd.read_html(io.StringIO(requests.get(ranking.WIKI + "List_of_S%26P_500_companies", headers=ranking.AGENT, timeout=60).text))[0]
    frame = ranking.ingest_prices(ranking.universe_symbols(current_symbols, changes), log)
    all_days, _, all_close = ranking.to_matrix(frame)
    keep = all_days <= position_day
    days, close = all_days[keep], all_close[keep]
    symbols = close.columns.tolist()
    raw_frame = fundamentals.ingest_raw(symbols, log)
    raw = raw_frame.assign(day=pd.to_datetime(raw_frame.timestamp, utc=True).dt.normalize()).drop_duplicates(["symbol", "day"]).pivot(index="day", columns="symbol", values="close").reindex(columns=symbols)
    ciks = pickle.loads(fundamentals.CIK_FILE.read_bytes())
    ciks.update({s: int(c) for s, c in zip(current.Symbol, current.CIK) if s in symbols})
    fundamentals.CIK_FILE.write_bytes(pickle.dumps(ciks))
    facts = fundamentals.fetch_facts(ciks.values(), session, log, refresh=True)
    decisions = load_decisions(con)
    held = {}
    if len(decisions):
        last = decisions[decisions.monat == decisions.monat.max()]
        held = {name: set(group.aktie) for name, group in last.groupby("strategie")}
    members = ranking.membership(current_symbols, changes, days)
    chosen = choose(close, raw, facts, ciks, members, days, held)
    created = datetime.now(timezone.utc).isoformat(timespec="seconds")
    month = month_of(days[-1])
    rows = pd.DataFrame([{"monat": month, "strategie": name, "aktie": symbol, "gewicht": float(weight), "signaltag": str(days[-1].date()), "erstellt": created} for name, picks in chosen.items() for symbol, weight in picks.items()])
    return freeze(con, rows)


def execution_position(days, created):
    """Erster Handelstag nach dem Erstellen. Erstellt am Tag d heisst: Eroeffnung von d kann schon vorbei sein."""
    day = pd.Timestamp(created).tz_convert("UTC").normalize()
    return int(np.searchsorted(days, day, side="right"))


def targets_from(decisions, strategy, days, columns):
    """Zielgewichte fuer den Simulator: Schluessel ist der Tag vor der Ausfuehrung. Noch nicht ausfuehrbare Monate fehlen."""
    out = {}
    index = {s: j for j, s in enumerate(columns)}
    for _, group in decisions[decisions.strategie == strategy].groupby("monat"):
        position = execution_position(days, group.erstellt.iloc[0])
        if position < len(days):
            weight = np.zeros(len(columns))
            for symbol, value in zip(group.aktie, group.gewicht):
                if symbol in index:
                    weight[index[symbol]] = value
            out[position - 1] = weight
    return out


def evaluate(decisions, days, open_, close, rate):
    """Gesamtrendite je Strategie und SPY seit der ersten Ausfuehrung. Kein Urteil, bevor genug Monate da sind."""
    plans = {name: targets_from(decisions, name, days, close.columns.tolist()) for name in STRATEGIES}
    starts = [min(plan) for plan in plans.values() if plan]
    if not starts:
        return pd.DataFrame()
    first = min(starts)
    o, c = open_.to_numpy(dtype=float)[first:], close.to_numpy(dtype=float)[first:]
    r, years = rate[first:], days[first:].tz_convert(ingest.NY).year.to_numpy()
    if len(c) < 2:
        return pd.DataFrame()
    spy = np.zeros(close.shape[1])
    spy[close.columns.tolist().index(BENCHMARK)] = 1.0
    rows = []
    for name, plan in (*plans.items(), ("Halten SPY", {first: spy})):
        shifted = {key - first: value for key, value in plan.items()}
        gross = ranking.simulate(o, c, shifted, r, years, tax=0.0)
        net = ranking.simulate(o, c, shifted, r, years, tax=TAX)
        peak = np.maximum.accumulate(gross.nav)
        rows.append({"strategie": name, "seit": str(days[first + 1].date()), "bis": str(days[-1].date()), "handelstage": len(c) - 1, "rendite": float(gross.final_after_tax / CAPITAL - 1), "nach_steuer": float(net.final_after_tax / CAPITAL - 1),
                     "drawdown": float((gross.nav / peak - 1).min()), "orders": gross.orders, "kosten": float(gross.costs)})
    return pd.DataFrame(rows)


def write_report(frame, months):
    lines = ["# Musterdepot", "", f"Stand {datetime.now():%Y-%m-%d %H:%M}. Kein echtes Geld, keine Orders, keine Anlageberatung. Regeln in GAMEPLAN, Phase 10.", "",
             f"Eingefrorene Monate: {months}. Vor {MIN_MONTHS} Monaten gibt es kein Urteil, die Zahlen sind dann fast nur Zufall. Die Fingerabdrücke der Entscheidungen stehen in `paper_log.txt`.", ""]
    if frame.empty:
        lines.append("Die erste Ausführung steht noch aus.")
    else:
        lines += [f"Seit {frame.seit.iloc[0]}, Stand {frame.bis.iloc[0]}, {frame.handelstage.iloc[0]} Handelstage.", "", "| Strategie | Rendite gesamt | Nach Steuer | Max. Einbruch | Orders | Kosten $ |", "|---|---:|---:|---:|---:|---:|"]
        lines += [f"| {r['strategie']} | {ranking._p(r['rendite'])} | {ranking._p(r['nach_steuer'])} | {ranking._p(r['drawdown'])} | {r['orders']} | {r['kosten']:,.0f} |" for r in frame.to_dict("records")]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def push(paths=("reports/paper_log.txt", "reports/PAPER.md")):
    for command in (["add", *paths], ["commit", "-m", "Musterdepot: neue Monatsentscheidung"], ["push"]):
        subprocess.run(["git", *command], cwd=ROOT, check=True)


def run(push_new=False, con=None, log=None):
    log = log or (lambda text: print(text, flush=True))
    con = con or connect()
    session = requests.Session()
    decisions = load_decisions(con)
    wanted = sorted({*decisions.aktie, BENCHMARK})
    frame = ranking.ingest_prices(wanted, log, PRICES)
    days, open_, close = ranking.to_matrix(frame)
    now = pd.Timestamp.now(tz=ingest.NY)
    position = latest_month_end(days, now)
    new = []
    if position is not None and month_of(days[position]) not in set(decisions.monat):
        new = decide(con, days[position], session, log)
        log(f"Eingefroren: {new}")
        decisions = load_decisions(con)
        frame = ranking.ingest_prices(sorted({*decisions.aktie, BENCHMARK}), log, PRICES)
        days, open_, close = ranking.to_matrix(frame)
    rate_frame = load(con, RATE_SYMBOL, "1D").close
    rate = rate_frame.to_numpy(dtype=float)[np.clip(np.searchsorted(rate_frame.index.normalize(), days, side="right") - 1, 0, len(rate_frame) - 1)] / 100
    result = evaluate(decisions, days, open_, close, rate)
    replace_rows(con, "paper_result", "PAPER", result if len(result) else pd.DataFrame({"strategie": pd.Series(dtype=str)}))
    write_report(result, decisions.monat.nunique())
    log(result.to_string() if len(result) else "Erste Ausfuehrung steht noch aus")
    if new and push_new:
        push()
    return result
