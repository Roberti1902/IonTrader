"""Phase 4: Beziehungsgraph in SQLite. Ticker, Sektoren, Indizes und Makro mit datierten Kanten."""
import numpy as np
import pandas as pd
import yfinance as yf

from . import ingest
from .store import load
from .study import naive_seconds
from .universe import UNIVERSE

MARKET, PROXY = "SPY", "QQQ"
MACRO = ("^VIX", "^TNX")
SECTOR_ETF = {
    "Technology": "XLK", "Financial Services": "XLF", "Healthcare": "XLV", "Consumer Cyclical": "XLY",
    "Consumer Defensive": "XLP", "Energy": "XLE", "Industrials": "XLI", "Communication Services": "XLC",
    "Basic Materials": "XLB", "Real Estate": "XLRE", "Utilities": "XLU",
}
WINDOW, MIN_OBS = 252, 200

SCHEMA = """
CREATE TABLE IF NOT EXISTS nodes(id TEXT PRIMARY KEY, kind TEXT NOT NULL, name TEXT);
CREATE TABLE IF NOT EXISTS edges(
    src TEXT NOT NULL, dst TEXT NOT NULL, kind TEXT NOT NULL, weight REAL NOT NULL,
    asof INTEGER NOT NULL,  -- Stichtag in Tagen: die Kante nutzt nur Daten bis zu diesem Tag
    PRIMARY KEY(src, dst, kind, asof)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS edges_dst ON edges(dst, kind, asof);
"""


def ensure(con):
    con.executescript(SCHEMA)


def daily_returns(con, ids):
    """Log-Renditen je Handelstag. Index: Tag als Zahl, fehlende Historie: NaN."""
    series = {}
    for s in ids:
        bars = load(con, s, "1D")
        if len(bars) > 1:
            days = naive_seconds(bars.index) // 86400
            series[s] = pd.Series(np.diff(np.log(bars.close.to_numpy(dtype=float)), prepend=np.nan), index=days)
    return pd.DataFrame(series).sort_index()


def edges_at(window, stocks, members, asof):
    """Alle Kanten eines Stichtags aus den letzten Handelstagen davor."""
    columns = [c for c in window.columns if window[c].notna().sum() >= MIN_OBS]
    if len(columns) < 2:
        return []
    x = window[columns].to_numpy(dtype=float)
    x = np.nan_to_num(x - np.nanmean(x, axis=0))
    spread = x.std(axis=0)
    usable = spread > 0
    z = x[:, usable] / spread[usable]
    names = [c for c, u in zip(columns, usable) if u]
    corr, lag = z.T @ z / len(z), z[:-1].T @ z[1:] / (len(z) - 1)
    rows = []
    for i, a in enumerate(names):
        for j, b in enumerate(names):
            if i != j:
                rows.append((a, b, "corr", float(corr[i, j]), asof))
                rows.append((a, b, "lead_lag", float(lag[i, j]), asof))  # a heute, b morgen
    if MARKET not in columns:
        return rows
    data = window.fillna(0.0)
    m = data[MARKET].to_numpy()
    var_m = m @ m
    beta_market = lambda r: float(r @ m / var_m)
    for s in [c for c in columns if c != MARKET and not c.startswith("^")]:
        rows.append((s, MARKET, "beta_market", beta_market(data[s].to_numpy()), asof))
    for s in stocks:
        if s not in columns:
            continue
        sector = members.get(s, PROXY)
        sector = sector if sector in columns else PROXY
        if sector not in columns or sector == s:
            continue
        r = data[s].to_numpy()
        residual = r - beta_market(r) * m
        orth = data[sector].to_numpy() - beta_market(data[sector].to_numpy()) * m
        var_o = orth @ orth
        rows.append((s, sector, "beta_sector", float(residual @ orth / var_o) if var_o > 0 else 0.0, asof))
    return rows


def sector_of(symbol):
    """Sektor-ETF eines Tickers. Unbekannt oder ohne Verbindung: der breite Technologie-Index als Stellvertreter."""
    try:
        return SECTOR_ETF.get(yf.Ticker(symbol).info.get("sector"), PROXY)
    except Exception:  # Eine fehlende Sektor-Angabe darf den Lauf nicht stoppen
        return PROXY


def write(con, nodes, members, returns, stocks, start="2013-03-31"):
    """Schreibt den Graphen je Quartalsende neu. Der letzte Handelstag kommt als aktuellster Stichtag dazu."""
    ensure(con)
    last = int(returns.index.max())
    stichtage = [int(t.value // 86_400_000_000_000) for t in pd.date_range(start, pd.Timestamp(last, unit="D"), freq="QE")]
    if last not in stichtage:
        stichtage.append(last)
    with con:
        con.execute("DELETE FROM edges")
        con.execute("DELETE FROM nodes")
        con.executemany("INSERT INTO nodes VALUES (?,?,?)", nodes)
        con.executemany("INSERT INTO edges VALUES (?,?,?,?,?)", [(s, etf, "member_of", 1.0, 0) for s, etf in members.items()])
        for asof in stichtage:
            window = returns[returns.index <= asof].tail(WINDOW)
            con.executemany("INSERT OR REPLACE INTO edges VALUES (?,?,?,?,?)", edges_at(window, stocks, members, asof))
    return len(stichtage)


def graph_tickers(con, symbol):
    """Der Graph wird immer ganz neu geschrieben: Ticker, die schon drin sind, muessen drinbleiben."""
    ensure(con)
    known = [row[0] for row in con.execute("SELECT id FROM nodes WHERE kind='ticker'")]
    return list(dict.fromkeys([symbol, *known, *UNIVERSE]))


def build(con, stocks):
    """Laedt die Kontextreihen und baut den ganzen Graphen."""
    etfs = sorted(set(SECTOR_ETF.values()))
    for s in [MARKET, PROXY, *etfs, *MACRO]:
        ingest.ingest_daily(s, con)
    members = {s: sector_of(s) for s in stocks}
    nodes = [(s, "ticker", s) for s in stocks] + [(MARKET, "index", "S&P 500"), (PROXY, "index", "Nasdaq 100")]
    nodes += [(etf, "sector", name) for name, etf in SECTOR_ETF.items()]
    nodes += [("^VIX", "macro", "Volatilitaetsindex"), ("^TNX", "macro", "US-Rendite 10 Jahre")]
    returns = daily_returns(con, [*stocks, MARKET, PROXY, *etfs, *MACRO])
    return write(con, nodes, members, returns, stocks), members


def factor_table(con, symbol):
    """Je Stichtag die Betas eines Tickers, relational aus den Kanten zusammengesetzt."""
    return pd.read_sql_query(
        """SELECT m.asof, m.weight AS b_m, s.dst AS sector, s.weight AS b_s, t.weight AS b_sm
           FROM edges m
           JOIN edges s ON s.src = m.src AND s.asof = m.asof AND s.kind = 'beta_sector'
           JOIN edges t ON t.src = s.dst AND t.dst = m.dst AND t.asof = m.asof AND t.kind = 'beta_market'
           WHERE m.src = ? AND m.dst = ? AND m.kind = 'beta_market' ORDER BY m.asof""",
        con, params=(symbol, MARKET))


def neighbors(con, node, kind, asof=None, k=5):
    """Staerkste Kanten eines Knotens zum letzten Stichtag vor asof."""
    limit = asof if asof is not None else 10 ** 9
    latest = con.execute("SELECT MAX(asof) FROM edges WHERE src=? AND kind=? AND asof<=?", (node, kind, limit)).fetchone()[0]
    if latest is None:
        return pd.DataFrame(columns=["dst", "weight", "asof"])
    return pd.read_sql_query("SELECT dst, weight, asof FROM edges WHERE src=? AND kind=? AND asof=? ORDER BY ABS(weight) DESC LIMIT ?",
                             con, params=(node, kind, latest, k))


def reachable(con, start, depth=2):
    """Knoten, die ueber Mitgliedschaften erreichbar sind: META -> Sektor -> andere Sektor-Mitglieder."""
    rows = con.execute(
        """WITH RECURSIVE walk(node, depth) AS (
               SELECT ?, 0
               UNION
               SELECT CASE WHEN e.src = walk.node THEN e.dst ELSE e.src END, walk.depth + 1
               FROM edges e JOIN walk ON e.src = walk.node OR e.dst = walk.node
               WHERE e.kind = 'member_of' AND walk.depth < ?
           ) SELECT DISTINCT node FROM walk""", (start, depth)).fetchall()
    return sorted(r[0] for r in rows if r[0] != start)
