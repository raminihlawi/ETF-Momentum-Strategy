"""
stock_fetcher.py — Incremental price download for OMXS, STOXX, SP500 universes.

Saves to:
  {data_root}/stock_prices/omxs/{ticker}.csv.gz
  {data_root}/stock_prices/stoxx/{ticker}.csv.gz
  {data_root}/stock_prices/sp500/{ticker}.csv.gz
  {data_root}/stock_prices/fx/{ticker}.csv.gz      (SEKUSD=X, EURUSD=X)
  {data_root}/stock_prices/gates/{ticker}.csv.gz   (SPY, EXSA.DE, ^OMX)

Each file contains a single "Close" column with daily prices.
Downloads are incremental: only fetches bars newer than the last cached date.
"""
import logging
import time
from pathlib import Path

import pandas as pd
import yfinance as yf

log = logging.getLogger(__name__)

DOWNLOAD_START = "2004-01-01"
FX_TICKERS     = ["SEKUSD=X", "EURUSD=X"]
GATE_TICKERS   = ["SPY", "QQQ", "EXSA.DE", "^OMX"]
BATCH_SIZE     = 25   # yfinance batch size per download call
RATE_SLEEP     = 0.5  # seconds between batches


def _safe_filename(ticker: str) -> str:
    return ticker.replace("/", "_")


def _load_cached(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    try:
        df = pd.read_csv(path, index_col=0, parse_dates=True, compression="gzip")
        if df.empty or "Close" not in df.columns:
            return None
        return df[["Close"]].dropna()
    except Exception:
        return None


def _fetch_ticker(ticker: str, start: str) -> pd.DataFrame | None:
    try:
        df = yf.download(ticker, start=start, progress=False, auto_adjust=True)
        if df is None or df.empty:
            return None
        close = df["Close"].squeeze()
        if isinstance(close, pd.DataFrame):
            close = close.iloc[:, 0]
        return close.dropna().rename("Close").to_frame()
    except Exception as e:
        log.debug("yfinance error for %s: %s", ticker, e)
        return None


def _update_file(path: Path, ticker: str) -> int:
    """Download incremental data for ticker, merge with cache, save. Returns new rows."""
    cached = _load_cached(path)
    if cached is not None and not cached.empty:
        last_date = cached.index.max()
        fetch_start = (last_date + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    else:
        cached      = None
        fetch_start = DOWNLOAD_START

    new_data = _fetch_ticker(ticker, fetch_start)
    if new_data is None or new_data.empty:
        return 0

    if cached is not None:
        combined = pd.concat([cached, new_data]).sort_index()
        combined = combined[~combined.index.duplicated(keep="last")]
    else:
        combined = new_data

    path.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(path, compression="gzip")
    return len(new_data)


def fetch_universe(universe: str, tickers: list[str], data_root: Path) -> int:
    """Download prices for all tickers in a universe. Returns total new rows."""
    out_dir = data_root / "stock_prices" / universe
    out_dir.mkdir(parents=True, exist_ok=True)
    total_new = 0
    ok = err = 0
    for i, ticker in enumerate(tickers):
        path = out_dir / f"{_safe_filename(ticker)}.csv.gz"
        try:
            n = _update_file(path, ticker)
            total_new += n
            ok += 1
        except Exception as e:
            log.warning("Failed %s/%s: %s", universe, ticker, e)
            err += 1
        if (i + 1) % BATCH_SIZE == 0:
            time.sleep(RATE_SLEEP)
    log.info("fetch_universe(%s): %d ok, %d errors, %d new rows", universe, ok, err, total_new)
    return total_new


def fetch_fx_and_gates(data_root: Path) -> int:
    """Download FX rates and gate ETFs. Returns total new rows."""
    total = 0
    for ticker in FX_TICKERS:
        path = data_root / "stock_prices" / "fx" / f"{_safe_filename(ticker)}.csv.gz"
        try:
            total += _update_file(path, ticker)
        except Exception as e:
            log.warning("FX fetch failed %s: %s", ticker, e)
    for ticker in GATE_TICKERS:
        path = data_root / "stock_prices" / "gates" / f"{_safe_filename(ticker)}.csv.gz"
        try:
            total += _update_file(path, ticker)
        except Exception as e:
            log.warning("Gate fetch failed %s: %s", ticker, e)
    log.info("fetch_fx_and_gates: %d new rows", total)
    return total


def load_ticker_lists(backend_dir: Path) -> dict[str, list[str]]:
    """Load committed ticker lists from dashboard/data/."""
    data_dir = backend_dir.parent / "data"
    import json
    omxs   = json.loads((data_dir / "omxs_tickers.json").read_text())
    stoxx  = json.loads((data_dir / "stoxx_tickers.json").read_text())
    nasdaq = json.loads((data_dir / "nasdaq_tickers.json").read_text())
    import pandas as pd
    pit   = pd.read_csv(data_dir / "sp500_ticker_start_end.csv")
    sp500 = sorted(pit["ticker"].unique().tolist())
    return {"omxs": omxs, "stoxx": stoxx, "sp500": sp500, "nasdaq": nasdaq}


def fetch_all(data_root: Path, backend_dir: Path) -> dict[str, int]:
    """Fetch all universes + FX. Returns dict of new row counts."""
    tickers = load_ticker_lists(backend_dir)
    result  = {}
    log.info("Starting stock price fetch: %d OMXS, %d STOXX, %d SP500, %d Nasdaq tickers",
             len(tickers["omxs"]), len(tickers["stoxx"]),
             len(tickers["sp500"]), len(tickers["nasdaq"]))
    result["fx_gates"]   = fetch_fx_and_gates(data_root)
    result["omxs"]       = fetch_universe("omxs",   tickers["omxs"],   data_root)
    result["stoxx"]      = fetch_universe("stoxx",  tickers["stoxx"],  data_root)
    result["sp500"]      = fetch_universe("sp500",  tickers["sp500"],  data_root)
    result["nasdaq"]     = fetch_universe("nasdaq", tickers["nasdaq"], data_root)
    log.info("fetch_all done: %s", result)
    return result
