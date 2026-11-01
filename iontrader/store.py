"""SQLite-Speicher fuer alle Timeframes."""
import sqlite3

import pandas as pd

from . import ROOT

DB = ROOT / "data" / "iontrader.db"
COLS = ["open", "high", "low", "close", "volume"]

SCHEMA = """CREATE TABLE IF NOT EXISTS bars(
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    ts INTEGER NOT NULL,  -- Bar-ENDE in UTC-Sekunden: ein Bar ist erst ab ts bekannt
    open REAL NOT NULL, high REAL NOT NULL, low REAL NOT NULL, close REAL NOT NULL, volume REAL NOT NULL,
    source TEXT NOT NULL,
    PRIMARY KEY(symbol, timeframe, ts)
) WITHOUT ROWID"""


def connect(path=DB):
    con = sqlite3.connect(path, timeout=120)  # parallele Downloads warten aufeinander statt abzubrechen
    con.execute("PRAGMA journal_mode=WAL")
    con.execute(SCHEMA)
    return con


def save(con, symbol, timeframe, df, source):
    """df: Index = Bar-Ende (tz-aware), Spalten = COLS. Doppelte Bars werden ersetzt."""
    rows = zip([symbol] * len(df), [timeframe] * len(df), df.index.as_unit("s").asi8.tolist(),
               *(df[c].tolist() for c in COLS), [source] * len(df))
    with con:
        con.executemany("INSERT OR REPLACE INTO bars VALUES (?,?,?,?,?,?,?,?,?)", rows)


def replace_rows(con, table, symbol, df):
    """Ergebnis-Tabelle fuer einen Ticker komplett ersetzen; das Schema kommt aus dem DataFrame."""
    with con:
        if con.execute("SELECT 1 FROM sqlite_master WHERE name=?", (table,)).fetchone():
            con.execute(f"DELETE FROM {table} WHERE symbol=?", (symbol,))
            existing = {row[1] for row in con.execute(f"PRAGMA table_info({table})")}
            for column in set(df.columns) - existing:  # neue Spalten dazu, ohne andere Ticker zu verlieren
                con.execute(f'ALTER TABLE {table} ADD COLUMN "{column}"')
        df.assign(symbol=symbol).to_sql(table, con, if_exists="append", index=False)


def load(con, symbol, timeframe):
    df = pd.read_sql_query(
        "SELECT ts, open, high, low, close, volume FROM bars WHERE symbol=? AND timeframe=? ORDER BY ts",
        con, params=(symbol, timeframe))
    df.index = pd.to_datetime(df.pop("ts"), unit="s", utc=True)
    return df
