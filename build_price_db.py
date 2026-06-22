"""
Build / update a local SQLite database of daily OHLCV for the Stockholm
exchange (Large/Mid/Small Cap) so the screener and backtests don't have to
hit yfinance every run.

USAGE
    python build_price_db.py            # full build / incremental update
    python build_price_db.py --full      # force re-download full history

The ticker universe lives in tickers_stockholm.csv (ticker,name,segment).
Edit that file to add/remove names - this is a starting list and should be
reviewed (see PROJECT_SPEC.md note on survivorship bias: it reflects today's
index membership, not the constituents as of any past date).

Requires: pip install yfinance pandas
"""

import sqlite3
import sys
from pathlib import Path

import pandas as pd

try:
    import yfinance as yf
except ImportError:
    raise SystemExit("Install yfinance first:  pip install yfinance pandas")


# ============================ CONFIG ============================
CONFIG = {
    "db_path": "stockholm_ohlc.sqlite3",
    "tickers_csv": "tickers_stockholm.csv",
    "benchmark": "^OMX",        # OMX Stockholm 30 index, stored alongside tickers
    "start_date": "2000-01-01",  # used for the initial full download
}


# ============================ DB SETUP ============================
def init_db(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tickers (
            ticker TEXT PRIMARY KEY,
            name TEXT,
            segment TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ohlc (
            ticker TEXT NOT NULL,
            date TEXT NOT NULL,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            volume INTEGER,
            PRIMARY KEY (ticker, date)
        )
    """)
    conn.commit()


def load_universe(csv_path, benchmark):
    df = pd.read_csv(csv_path)
    rows = list(df[["ticker", "name", "segment"]].itertuples(index=False, name=None))
    rows.append((benchmark, "OMX Stockholm 30", "Index"))
    return rows


def last_date_for(conn, ticker):
    row = conn.execute(
        "SELECT MAX(date) FROM ohlc WHERE ticker = ?", (ticker,)
    ).fetchone()
    return row[0]


def fetch(ticker, start, end=None):
    df = yf.download(ticker, start=start, end=end, interval="1d",
                      auto_adjust=True, progress=False)
    if df is None or df.empty:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
    df.index = df.index.strftime("%Y-%m-%d")
    return df


def upsert(conn, ticker, df):
    rows = [
        (ticker, r.Index, r.Open, r.High, r.Low, r.Close, int(r.Volume))
        for r in df.itertuples(name="Row")
    ]
    conn.executemany("""
        INSERT INTO ohlc (ticker, date, open, high, low, close, volume)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(ticker, date) DO UPDATE SET
            open=excluded.open, high=excluded.high, low=excluded.low,
            close=excluded.close, volume=excluded.volume
    """, rows)
    conn.commit()


# ============================ MAIN ============================
def main():
    cfg = CONFIG
    full = "--full" in sys.argv

    db_path = Path(cfg["db_path"])
    conn = sqlite3.connect(db_path)
    init_db(conn)

    universe = load_universe(cfg["tickers_csv"], cfg["benchmark"])
    conn.executemany(
        "INSERT OR REPLACE INTO tickers (ticker, name, segment) VALUES (?, ?, ?)",
        universe,
    )
    conn.commit()

    ok, failed = 0, []
    for ticker, name, segment in universe:
        last = None if full else last_date_for(conn, ticker)
        if last:
            start = (pd.Timestamp(last) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        else:
            start = cfg["start_date"]

        if last and start > pd.Timestamp.today().strftime("%Y-%m-%d"):
            ok += 1
            continue

        print(f"{ticker:<12} ({segment:<6}) from {start} ...", end=" ")
        df = fetch(ticker, start)
        if df is None or df.empty:
            print("no new data")
            if last is None:
                failed.append(ticker)
            else:
                ok += 1
            continue

        upsert(conn, ticker, df)
        print(f"+{len(df)} rows")
        ok += 1

    print(f"\nDone. {ok}/{len(universe)} tickers up to date.")
    if failed:
        print(f"Failed (no data at all): {', '.join(failed)}")
    conn.close()


if __name__ == "__main__":
    main()
