"""
Incremental ETF price fetcher.

For each ticker, determines the last date already in SQLite and downloads
only the missing days from yfinance. Also handles screening candidates.
"""
import logging
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf

from db import get_conn, upsert_etf_prices, last_etf_date, init_db, DB_PATH

log = logging.getLogger(__name__)


def fetch_incremental(tickers: list[str], db_path: Path | None = None) -> int:
    """
    Download only missing days for each ticker and upsert into etf_prices.
    Returns total new rows inserted across all tickers.
    """
    init_db(db_path)
    today = date.today().isoformat()
    total = 0

    for ticker in tickers:
        last = last_etf_date(ticker, db_path)
        start = (
            (date.fromisoformat(last) + timedelta(days=1)).isoformat()
            if last
            else "2004-01-01"
        )
        if start > today:
            log.debug("%s: already up to date (%s)", ticker, last)
            continue

        try:
            raw = yf.download(
                ticker,
                start=start,
                end=today,
                progress=False,
                auto_adjust=True,
                multi_level_index=False,
            )
            if raw.empty:
                log.warning("%s: no data from yfinance (possibly delisted)", ticker)
                continue

            rows = []
            for d, row in raw.iterrows():
                close = row.get("Close")
                high  = row.get("High")
                low   = row.get("Low")
                if pd.isna(close):
                    continue
                rows.append((
                    ticker,
                    d.strftime("%Y-%m-%d"),
                    float(close),
                    float(high)  if not pd.isna(high)  else None,
                    float(low)   if not pd.isna(low)   else None,
                ))

            if rows:
                upsert_etf_prices(rows, db_path)
                total += len(rows)
                log.info("%s: +%d rows (through %s)", ticker, len(rows), rows[-1][1])

        except Exception as exc:
            log.error("%s: fetch error — %s", ticker, exc)

    return total


def get_all_tickers(config: dict, screening_config: dict | None = None) -> list[str]:
    """Extract every ticker referenced by config + screening_config."""
    tickers: set[str] = set()

    for sleeve in ("factor_sleeve", "sector_sleeve"):
        for info in config.get(sleeve, {}).values():
            t = info.get("ticker", "")
            if t and not t.startswith("CASH"):
                tickers.add(t)

    for key in ("regime_baseline", "regime_cash_compare", "cash_proxy"):
        t = config.get(key, {}).get("ticker", "")
        if t and not t.startswith("CASH"):
            tickers.add(t)

    # Benchmarks hardcoded in engine.py
    tickers.update(["IWDA.L", "^OMX", "^IXIC", "^GSPC"])

    # Low-corr extras hardcoded in engine.py
    tickers.update(["2B7A.DE", "QDVH.DE", "GLD"])

    if screening_config:
        for c in screening_config.get("candidates", []):
            t = c.get("ticker", "")
            if t:
                tickers.add(t)

    return sorted(tickers)
