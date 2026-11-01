"""Phase 6: Der lange Weg eines Tickers durch alle Phasen, der Nacht- und der Wochenlauf. Laeuft als eigener Prozess."""
import socket
import subprocess
import sys
import time

import pandas as pd

from . import ROOT, dataset, features, graph, ingest, logbook, matrix, risk, setup, study, train
from .models import KINDS
from .store import connect, load

SCHEMA = """CREATE TABLE IF NOT EXISTS pipeline(
    symbol TEXT NOT NULL, step TEXT NOT NULL, status TEXT NOT NULL, ts INTEGER NOT NULL, message TEXT,
    PRIMARY KEY(symbol, step)
) WITHOUT ROWID"""
LOCK_PORT = 18051  # Nur ein Job zur Zeit; der Port wird beim Prozessende vom System freigegeben
LOGS = ROOT / "data" / "logs"
NIGHTLY, WEEKLY = "Nachtlauf", "Wochenlauf"
NIGHT_MINUTE = 16 * 60 + 30  # New York: Dann sind die Tagesdaten da
WEEK_SECONDS = 7 * 86400


def _nets(symbol, con):
    from . import match

    train.tournament(symbol)
    folds, holdout = dataset.fold_dates(dataset.load_ticker(con, symbol))
    match.report(con, symbol, folds[0][0], holdout, train.REPORTS / f"{symbol}_phase3.md")


def _matrix(symbol, con):
    setup.feature_ic(symbol, con)
    matrix.run_walk_forward(symbol, con, refresh=False)


def enough_history(con, symbol):
    """2 Jahre Abschlusspruefung, 5 Testjahre und mindestens 1 Lernjahr."""
    bars = load(con, symbol, "5m")
    if bars.empty:
        return False
    days = (bars.index[-1] - bars.index[0]).days
    return days >= dataset.HOLDOUT_DAYS + (dataset.N_FOLDS + 1) * dataset.FOLD_DAYS


STEPS = (
    ("Kurse", lambda s, con: ingest.ingest(s, con)),
    ("Muster", lambda s, con: features.run(s, con)),
    ("Graph", lambda s, con: graph.build(con, graph.graph_tickers(con, s))),
    ("Studie", lambda s, con: study.run(s, con)),
    ("Netze", _nets),
    ("Risiko", lambda s, con: risk.run(s)),
    ("Matrix", _matrix),
    ("Abschlusspruefung", lambda s, con: matrix.run_final(s, con)),
)
NEEDS_HISTORY = {"Netze", "Matrix", "Abschlusspruefung"}


def job_lock():
    """Ein Socket, solange dieser Prozess den Job haelt; None, wenn schon ein anderer laeuft."""
    lock = socket.socket()
    try:
        lock.bind(("127.0.0.1", LOCK_PORT))
    except OSError:
        lock.close()
        return None
    return lock


def job_running():
    lock = job_lock()
    if lock is None:
        return True
    lock.close()
    return False


def mark(con, symbol, step, status, message=""):
    con.execute(SCHEMA)
    with con:
        con.execute("INSERT OR REPLACE INTO pipeline VALUES (?,?,?,?,?)", (symbol, step, status, int(time.time()), str(message)[:500]))


def status(con, symbol):
    con.execute(SCHEMA)
    return pd.read_sql_query("SELECT step, status, ts, message FROM pipeline WHERE symbol=? ORDER BY ts", con, params=(symbol,)).set_index("step")


def missing_steps(con, symbol):
    """Schritte, die noch fehlen. Nach einem Fehler nichts mehr: Der Job wuerde sonst endlos neu starten."""
    known = status(con, symbol)
    if (train.OOS / f"{symbol}_now.npz").exists() or (known.status == "fehler").any():
        return []
    return [name for name, _ in STEPS if name not in known.index or known.status[name] not in ("fertig", "uebersprungen")]


def run(symbol, steps=STEPS, con=None, repeat=False):
    """Arbeitet alle fehlenden Schritte ab. Nach einem Fehler bleibt der Rest offen, das Dashboard laeuft mit dem, was da ist."""
    symbol = ingest.clean_ticker(symbol)
    con = con or connect()
    lock = job_lock()
    if lock is None:
        raise SystemExit("Es laeuft schon ein Job. Er muss erst fertig sein.")
    done = status(con, symbol)
    for name, step in steps:
        if not repeat and name in done.index and done.status[name] in ("fertig", "uebersprungen"):
            continue
        if name in NEEDS_HISTORY and not enough_history(con, symbol):
            mark(con, symbol, name, "uebersprungen", "Zu wenig Historie: Die Netze brauchen mindestens 8 Jahre 5-Minuten-Daten")
            continue
        print(f"--- {symbol}: {name}", flush=True)
        mark(con, symbol, name, "laeuft")
        try:
            step(symbol, con)
        except (Exception, SystemExit) as error:  # Der Job endet, der Grund steht im Dashboard
            mark(con, symbol, name, "fehler", error)
            print(f"{symbol}: {name} fehlgeschlagen: {error}", flush=True)
            return False
        mark(con, symbol, name, "fertig")
    lock.close()
    return True


def _nightly(symbol, con):
    ingest.ingest(symbol, con)
    features.run(symbol, con)
    graph.build(con, graph.graph_tickers(con, symbol))
    if (train.OOS / f"{symbol}_now.npz").exists():
        matrix.refresh_now(symbol, con)
    logbook.score(con, symbol)


def nightly(symbol):
    """Daten-Refresh, Scanner, Graph, frische Netze und die Pruefung faelliger Prognosen. Die Stack-Regeln bleiben."""
    return run(symbol, ((NIGHTLY, _nightly),), repeat=True)


def weekly(symbol):
    """Neutraining und Rekalibrierung auf den neuen Daten, mit den eingefrorenen Regeln."""
    return run(symbol, ((WEEKLY, lambda s, con: matrix.run_final(s, con, fresh=True)),), repeat=True)


def last_session_day(now):
    """Der letzte Werktag, dessen Tagesdaten laengst da sein sollten, als NY-Mitternacht. Feiertage faengt die Merkliste ab."""
    ny = pd.Timestamp(now, unit="s", tz="UTC").tz_convert(ingest.NY)
    day = ny.normalize()
    if ny.hour * 60 + ny.minute < NIGHT_MINUTE:
        day -= pd.Timedelta(days=1)
    while day.weekday() > 4:
        day -= pd.Timedelta(days=1)
    return day


def next_job(con, active, now):
    """Welcher Job als Naechstes dran ist: erst der aktive Ticker, dann Nacht- und Wochenlaeufe."""
    if active and missing_steps(con, active):
        return "pipeline", active
    con.execute(SCHEMA)
    tickers = [row[0] for row in con.execute("SELECT DISTINCT symbol FROM pipeline")]
    tickers += [active] if active and active not in tickers else []
    session_day = last_session_day(now)
    for symbol in tickers:
        known = status(con, symbol)
        # Steht noch "laeuft", obwohl kein Job mehr laeuft, wurde er unterbrochen und darf neu starten
        ran = pd.Timestamp(int(known.ts[NIGHTLY]), unit="s", tz="UTC").tz_convert(ingest.NY) if NIGHTLY in known.index and known.status[NIGHTLY] != "laeuft" else None
        bars = load(con, symbol, "1D")
        stale = bars.empty or bars.index[-1].tz_convert(ingest.NY).normalize() < session_day
        if stale and (ran is None or ran < session_day + pd.Timedelta(minutes=NIGHT_MINUTE)):
            return "nightly", symbol
    weekend = pd.Timestamp(now, unit="s", tz="UTC").tz_convert(ingest.NY).weekday() > 4
    for symbol in tickers:
        marker = train.OOS / f"{symbol}_{KINDS[0]}_solo_final.npz"
        if weekend and marker.exists() and now - marker.stat().st_mtime > WEEK_SECONDS:
            return "weekly", symbol
    return None


def spawn(job, symbol):
    """Startet den Job als eigenen Prozess; so bleibt das Dashboard frei und ein Absturz trifft nur den Job."""
    LOGS.mkdir(parents=True, exist_ok=True)
    output = open(LOGS / f"{symbol}_{job}.log", "a", encoding="utf-8")
    return subprocess.Popen([sys.executable, str(ROOT / "main.py"), job, symbol], stdout=output, stderr=subprocess.STDOUT, cwd=ROOT)
