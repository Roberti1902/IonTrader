"""Prognose-Logbuch: Jede Live-Prognose wird gespeichert und spaeter mit dem echten Kurs verglichen."""
import numpy as np
import pandas as pd

from .dataset import HORIZON_DAYS
from .store import replace_rows
from .study import HORIZONS, forward_returns

SCHEMA = """CREATE TABLE IF NOT EXISTS forecast_log(
    symbol TEXT NOT NULL, ts INTEGER NOT NULL, horizont TEXT NOT NULL, kurs REAL NOT NULL,
    p_bull REAL NOT NULL, basisrate REAL NOT NULL, von REAL, bis REAL,
    PRIMARY KEY(symbol, ts, horizont)
) WITHOUT ROWID"""


def write(con, symbol, ts, price, rows):
    con.execute(SCHEMA)
    with con:
        con.executemany("INSERT OR REPLACE INTO forecast_log VALUES (?,?,?,?,?,?,?,?)",
                        [(symbol, int(ts), r["horizont"], price, r["p_bull"], r["basisrate"], r.get("von"), r.get("bis")) for r in rows])


def score(con, symbol):
    """Vergleicht alle faelligen Prognosen mit dem Kurs zur gleichen Uhrzeit x Handelstage spaeter und speichert das Ergebnis."""
    con.execute(SCHEMA)
    log = pd.read_sql_query("SELECT * FROM forecast_log WHERE symbol=? ORDER BY ts", con, params=(symbol,))
    if log.empty:
        return pd.DataFrame()
    moments = np.sort(log.ts.unique())
    fwd, _ = forward_returns(con, symbol, "5m", pd.to_datetime(moments, unit="s", utc=True))
    position = np.searchsorted(moments, log.ts.to_numpy())
    rows = []
    for name in HORIZONS:
        part = log.horizont == name
        real = fwd[name][position[part]]
        done = np.isfinite(real)
        row = {"horizont": name, "prognosen": int(part.sum()), "faellig": int(done.sum())}
        if done.any():
            p, base, up = log.p_bull[part].to_numpy()[done], log.basisrate[part].to_numpy()[done], (real[done] > 0).astype(float)
            simple = np.expm1(real[done])
            low, high = log.von[part].to_numpy(dtype=float)[done], log.bis[part].to_numpy(dtype=float)[done]
            base_error = ((base - up) ** 2).sum()
            row |= {"unabhaengig": int(len(np.unique(log.ts[part].to_numpy()[done] // (86400 * HORIZON_DAYS[name])))), "angezeigt": float(p.mean()), "tatsaechlich": float(up.mean()),
                    "brier_skill": float(1 - ((p - up) ** 2).sum() / base_error) if base_error > 0 else np.nan,
                    "in_spanne": float(((simple >= low) & (simple <= high)).mean()) if np.isfinite(low).all() else np.nan}
        rows.append(row)
    frame = pd.DataFrame(rows)
    replace_rows(con, "forecast_score", symbol, frame)
    return frame
