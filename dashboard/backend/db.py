"""
SQLite database layer — schema, connection, read/write helpers.

Tables:
  etf_prices       (ticker, date, close, high, low)
  ppm_nav          (ppm_number, date, nav_sek)
  screener_history (ticker, run_date, score, roc_63d, would_select, error)

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

CREATE TABLE IF NOT EXISTS screener_history (
    ticker       TEXT NOT NULL,
    run_date     TEXT NOT NULL,   -- 'YYYY-MM-DD' of engine run
    score        REAL,
    roc_63d      REAL,
    would_select INTEGER NOT NULL DEFAULT 0,
    error        TEXT,
    PRIMARY KEY (ticker, run_date)
);

CREATE INDEX IF NOT EXISTS ix_etf_ticker  ON etf_prices      (ticker, date);
CREATE INDEX IF NOT EXISTS ix_ppm_number  ON ppm_nav         (ppm_number, date);
CREATE INDEX IF NOT EXISTS ix_scr_ticker  ON screener_history (ticker, run_date);
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


# ── Screener history helpers ─────────────────────────────────────────
def upsert_screener_history(candidates: list[dict], run_date: str,
                             path: Path | None = None) -> None:
    """Persist one engine run's screener results. Idempotent (INSERT OR REPLACE)."""
    rows = [
        (
            c["ticker"],
            run_date,
            c.get("score"),
            c.get("roc_63d"),
            1 if c.get("would_select") else 0,
            c.get("error"),
        )
        for c in candidates
    ]
    with get_conn(path) as conn:
        conn.executemany(
            """INSERT OR REPLACE INTO screener_history
               (ticker, run_date, score, roc_63d, would_select, error)
               VALUES (?,?,?,?,?,?)""",
            rows,
        )


def load_screener_streak(path: Path | None = None) -> dict:
    """
    For every ticker in screener_history, compute how many consecutive
    calendar months (ending at the latest run month) the ticker showed
    would_select=1 on the last engine run of that month.

    Returns {ticker: {"streak": int, "last_date": "YYYY-MM-DD", "months": ["YYYY-MM", ...]}}
    """
    with get_conn(path) as conn:
        rows = conn.execute(
            """SELECT ticker, run_date, would_select
               FROM screener_history
               ORDER BY ticker, run_date"""
        ).fetchall()

    if not rows:
        return {}

    # Group by ticker → {month: last would_select value}
    from collections import defaultdict
    ticker_months: dict[str, dict[str, int]] = defaultdict(dict)
    for ticker, run_date, would_select in rows:
        month = run_date[:7]  # YYYY-MM
        # Keep the latest run's value per month (ORDER BY run_date ascending)
        ticker_months[ticker][month] = would_select

    result = {}
    for ticker, month_map in ticker_months.items():
        sorted_months = sorted(month_map.keys(), reverse=True)
        if not sorted_months:
            continue
        last_month = sorted_months[0]

        # Count consecutive months with would_select=1 going backwards
        streak = 0
        prev_month = None
        for m in sorted_months:
            # Ensure months are truly consecutive (no gaps)
            if prev_month is not None:
                y1, mo1 = map(int, prev_month.split("-"))
                y2, mo2 = map(int, m.split("-"))
                expected_prev = (y1 * 12 + mo1 - 1)
                actual        = (y2 * 12 + mo2)
                if expected_prev != actual:
                    break  # gap in months — streak ends
            if month_map[m] == 1:
                streak += 1
                prev_month = m
            else:
                break

        # Last engine-run date for this ticker
        last_run = max(r[1] for r in rows if r[0] == ticker)
        result[ticker] = {
            "streak":    streak,
            "last_date": last_run,
            "months":    sorted_months[:streak],
        }

    return result
