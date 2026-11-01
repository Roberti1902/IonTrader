"""Phase 3: Trainings-Universum. Gross im Jahr 2016, nicht heute, damit nicht nur spaetere Gewinner drin sind."""
from concurrent.futures import ThreadPoolExecutor, as_completed

from . import features, ingest
from .store import connect, load

# ponytail: Liste von Hand aus den US-Schwergewichten Anfang 2016; alle haben ueberlebt, die Verzerrung ist also
# kleiner, aber nicht weg. Fuer sauberes Survivorship-Handling braeuchte es historische Indexmitglieder.
UNIVERSE = [
    "AAPL", "MSFT", "AMZN", "GOOGL", "JPM", "JNJ", "XOM", "WFC", "BAC", "PG", "T", "GE", "CVX", "VZ", "PFE",
    "KO", "HD", "INTC", "DIS", "CSCO", "MRK", "ORCL", "IBM", "WMT", "C", "BA", "MMM", "GILD", "CMCSA", "PEP",
]


def available(con):
    """Ticker mit fertigen Features fuer alle Modell-Timeframes."""
    return [s for s in UNIVERSE if features.feature_path(s, "5m").exists() and not load(con, s, "5m").empty]


def build(downloads=4):
    """Laedt fehlende Ticker parallel (5m-Basis genuegt) und scannt sie danach auf allen CPU-Threads."""
    con = connect()
    missing = [s for s in UNIVERSE if load(con, s, "1D").empty or load(con, s, "5m").empty]
    print(f"Universum: {len(UNIVERSE)} Ticker, {len(missing)} zu laden", flush=True)
    with ThreadPoolExecutor(downloads) as pool:
        jobs = {pool.submit(ingest.ingest, s, None, 5): s for s in missing}
        for job in as_completed(jobs):
            try:
                print(f"{jobs[job]}: geladen ({job.result()})", flush=True)
            except (Exception, SystemExit) as error:  # ein defekter Ticker stoppt nicht den Rest
                print(f"{jobs[job]}: FEHLER {error}", flush=True)
    total_wall, total_cpu = 0.0, 0.0
    for s in UNIVERSE:
        if load(con, s, "5m").empty or features.feature_path(s, "5m").exists():
            continue
        wall, cpu = features.run(s, con)
        total_wall, total_cpu = total_wall + wall, total_cpu + cpu
    print(f"Scan: {total_wall:.0f} s, CPU-Auslastung {total_cpu / max(total_wall, 1e-9) / features.ioncore.threads():.0%}", flush=True)
    print(f"Fertig: {len(available(con))} von {len(UNIVERSE)} Tickern", flush=True)
