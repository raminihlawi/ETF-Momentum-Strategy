"""
Shared helper for reading the local Stockholm OHLCV SQLite database built by
build_price_db.py. Used by pullback_screener.py and trend_following_backtest.py
so neither has to hit yfinance directly.
"""

import sqlite3
import pandas as pd

DB_PATH = "stockholm_ohlc.sqlite3"


def get_connection(db_path=DB_PATH):
    return sqlite3.connect(db_path)


def load_universe(segments=None, conn=None):
    """Return list of (ticker, name, segment) rows, optionally filtered by segment."""
    own = conn is None
    conn = conn or get_connection()
    try:
        query = "SELECT ticker, name, segment FROM tickers"
        params = ()
        if segments:
            placeholders = ",".join("?" * len(segments))
            query += f" WHERE segment IN ({placeholders})"
            params = tuple(segments)
        return conn.execute(query, params).fetchall()
    finally:
        if own:
            conn.close()


def load_prices(ticker, start=None, end=None, conn=None):
    """Load OHLCV for one ticker as a DataFrame indexed by date (Open/High/Low/Close/Volume)."""
    own = conn is None
    conn = conn or get_connection()
    try:
        query = "SELECT date, open, high, low, close, volume FROM ohlc WHERE ticker = ?"
        params = [ticker]
        if start:
            query += " AND date >= ?"
            params.append(start)
        if end:
            query += " AND date <= ?"
            params.append(end)
        query += " ORDER BY date"
        df = pd.read_sql_query(query, conn, params=params, parse_dates=["date"])
        if df.empty:
            return df
        df = df.set_index("date")
        df.columns = ["Open", "High", "Low", "Close", "Volume"]
        return df
    finally:
        if own:
            conn.close()
