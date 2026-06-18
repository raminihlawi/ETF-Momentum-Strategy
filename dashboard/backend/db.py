"""
SQLite database layer — schema, connection, read/write helpers.

Tables:
  etf_prices  (ticker, date, close, high, low)
  ppm_nav     (ppm_number, date, nav_sek)

DB location is controlled by the DATA_DIR environment variable (default /data).
In development, fall back to the project's own directory.
"""
import os
import sqlite3
from pathlib import Path

import pandas as pd

# ── Path resolution ────────────────────────────────────────────────
_DEFAULT_DEV = Path(__file__).parent.parent.parent  # repo root
DATA_DIR = Path(os.getenv("DATA_DIR", str(_DEFAULT_DEV)))
DB_PATH  = DATA_DIR / "dashboard.db"

# ── Schema ─────────────────────────────────────────────────────────
_DDL = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous  = NORMAL;

CREATE TABLE IF NOT EXISTS etf_prices (
    ticker TEXT    NOT NULL,
    date   TEXT    NOT NULL,   -- 'YYYY-MM-DD'
    close  REAL    NOT NULL,
    high   REAL,
    low    REAL,
    PRIMARY KEY (ticker, date)
);

CREATE TABLE IF NOT EXISTS ppm_nav (
    ppm_number TEXT NOT NULL,
    date       TEXT NOT NULL,  -- 'YYYY-MM-DD'
    nav_sek    REAL NOT NULL,
    PRIMARY KEY (ppm_number, date)
);

CREATE INDEX IF NOT EXISTS ix_etf_ticker ON etf_prices (ticker, date);
CREATE INDEX IF NOT EXISTS ix_ppm_number ON ppm_nav  (ppm_number, date);
"""


# ── Connection ──────────────────────────────────────────────────────
def get_conn(path: Path | None = None) -> sqlite3.Connection:
    p = path or DB_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p), check_same_thread=False)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous  = NORMAL")
    return conn


def init_db(path: Path | None = None) -> None:
    with get_conn(path) as conn:
        conn.executescript(_DDL)


# ── ETF helpers ─────────────────────────────────────────────────────
def upsert_etf_prices(rows: list[tuple], path: Path | None = None) -> None:
    """rows: list of (ticker, date_str, close, high, low)"""
    with get_conn(path) as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO etf_prices(ticker,date,close,high,low) VALUES(?,?,?,?,?)",
            rows,
        )


def last_etf_date(ticker: str, path: Path | None = None) -> str | None:
    with get_conn(path) as conn:
        row = conn.execute(
            "SELECT MAX(date) FROM etf_prices WHERE ticker=?", (ticker,)
        ).fetchone()
    return row[0] if row else None


def load_etf_prices(
    tickers: list[str],
    start: str | None = None,
    path: Path | None = None,
) -> dict[str, pd.DataFrame]:
    """
    Return {"close": df, "high": df, "low": df} — same shape as engine.fetch_prices().
    Columns = tickers, index = DatetimeIndex.
    """
    if not tickers:
        return {}
    placeholders = ",".join("?" * len(tickers))
    q = f"SELECT ticker,date,close,high,low FROM etf_prices WHERE ticker IN ({placeholders})"
    params: list = list(tickers)
    if start:
        q += " AND date >= ?"
        params.append(start)

    with get_conn(path) as conn:
        df = pd.read_sql_query(q, conn, params=params, parse_dates=["date"])

    if df.empty:
        return {}

    def pivot(col: str) -> pd.DataFrame:
        p = df.pivot_table(index="date", columns="ticker", values=col, aggfunc="last")
        p.columns.name = None
        return p.sort_index().ffill()

    return {
        "close": pivot("close"),
        "high":  pivot("high"),
        "low":   pivot("low"),
    }


# ── PPM helpers ─────────────────────────────────────────────────────
def upsert_ppm_nav(rows: list[tuple], path: Path | None = None) -> None:
    """rows: list of (ppm_number, date_str, nav_sek)"""
    with get_conn(path) as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO ppm_nav(ppm_number,date,nav_sek) VALUES(?,?,?)",
            rows,
        )


def last_ppm_date(path: Path | None = None) -> str | None:
    with get_conn(path) as conn:
        row = conn.execute("SELECT MAX(date) FROM ppm_nav").fetchone()
    return row[0] if row else None


def load_ppm_nav(
    ppm_numbers: list[str] | None = None,
    path: Path | None = None,
) -> pd.DataFrame:
    """
    Return wide DataFrame (DatetimeIndex × ppm_number columns), business-day
    reindexed and forward-filled — same shape as ppm_engine.load_ppm_data().
    Pass ppm_numbers to restrict to a specific universe (strongly recommended).
    """
    q = "SELECT ppm_number, date, nav_sek FROM ppm_nav"
    params: list = []
    if ppm_numbers:
        placeholders = ",".join("?" * len(ppm_numbers))
        q += f" WHERE ppm_number IN ({placeholders})"
        params = list(ppm_numbers)

    with get_conn(path) as conn:
        df = pd.read_sql_query(q, conn, params=params, parse_dates=["date"])

    if df.empty:
        return pd.DataFrame()

    wide = df.pivot_table(index="date", columns="ppm_number", values="nav_sek", aggfunc="last")
    wide.columns = [str(c) for c in wide.columns]
    wide = wide.sort_index()

    bday_idx = pd.bdate_range(wide.index[0], wide.index[-1])
    return wide.reindex(bday_idx).ffill()
