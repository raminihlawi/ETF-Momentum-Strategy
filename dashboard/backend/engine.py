#!/usr/bin/env python3
"""
ETF Dashboard Engine
Fetches prices, runs raw/sel126/reg252 (top1/top1 and top2/top2),
writes frontend/static/data.json.

Usage:
    python3 engine.py          # full run
    python3 engine.py --quick  # skip download, reuse cached prices
"""
import json
import sys
import logging
from pathlib import Path
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import yfinance as yf

# PPM engine (optional — skipped gracefully if unavailable)
try:
    from ppm_engine import run_ppm as _run_ppm
    _PPM_AVAILABLE = True
except ImportError:
    _PPM_AVAILABLE = False

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

import os as _os
BASE_DIR          = Path(__file__).parent
_DATA_DIR         = Path(_os.getenv("DATA_DIR", str(BASE_DIR.parent.parent)))
CONFIG_PATH       = _DATA_DIR / "config.json"
if not CONFIG_PATH.exists():
    CONFIG_PATH   = BASE_DIR / "config.json"   # dev fallback
CACHE_PATH        = BASE_DIR / "_price_cache.pkl"
DATA_PATH         = _DATA_DIR / "data.json"
if not DATA_PATH.parent.exists():
    DATA_PATH     = BASE_DIR.parent / "frontend" / "static" / "data.json"
SCREENING_CONFIG  = _DATA_DIR / "screening_config.json"
if not SCREENING_CONFIG.exists():
    SCREENING_CONFIG = BASE_DIR / "screening_config.json"
PPM_DATA_FILE     = BASE_DIR.parent.parent / "ppm_all_nav.csv"
DB_PATH           = _DATA_DIR / "dashboard.db"

# ── Strategy parameters ────────────────────────────────────────────
SEL_LB   = 84        # 4-month selection lookback (trading days)
REG_LB   = 84        # 4-month regime lookback
COST     = 0.0015    # transaction cost per side
CAPITAL  = 100_000   # starting capital
START    = "2019-10-01"
DL_FROM  = "2004-01-01"  # download start (warmup)

BENCHMARKS = {
    "MSCI World": "IWDA.L",
    "OMXS30":     "^OMX",
    "Nasdaq":     "^IXIC",
    "S&P 500":    "^GSPC",
}

# ── Accelerated momentum parameters ───────────────────────────────
ACCEL_LOOKBACK = 84   # ROC window (trading days)  — optimized via 160-run sweep
ACCEL_WINDOW   = 15   # days for each acceleration half-window — optimized
EMA_SPAN       = 5    # smoothing span for median price

# ── Low-correlation basket ─────────────────────────────────────────
LOW_CORR_EXTRA = {
    "UTILITIES": {"ticker": "2B7A.DE", "nordnet_name": "iShares S&P 500 Utilities Sector UCITS ETF",        "isin": "IE00B3WJKQ31", "ter_pct": 0.15},
    "COMMS":     {"ticker": "QDVH.DE", "nordnet_name": "iShares S&P 500 Communication Services UCITS ETF",  "isin": "IE00B4KBBD01", "ter_pct": 0.15},
    "GOLD":      {"ticker": "GLD",     "nordnet_name": "SPDR Gold Shares",                                   "isin": "US78463V1070", "ter_pct": 0.40},
}
LOW_CORR_SECTOR_KEEP = {"ENERGY", "HEALTHCARE", "CONS STAP"}  # kept from main config

# Fallback TER rates if not in config (annual %)
DEFAULT_TER = {
    "IWVL.L": 0.25, "IWQU.L": 0.25, "IWMO.L": 0.25, "WSML.L": 0.35,
    "IITU.L": 0.25, "IUES.L": 0.25, "IUHC.L": 0.25, "IUFS.L": 0.25,
    "IUIS.L": 0.25, "IUCD.L": 0.25, "IUCS.L": 0.25, "IUMS.L": 0.25,
    "IUUS.L": 0.25, "IUCM.L": 0.25, "IWDA.L": 0.20, "IBTS.L": 0.10,
}


# ── Config helpers ─────────────────────────────────────────────────
def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return json.load(f)


def parse_config(cfg: dict) -> tuple:
    factor_t = [(label, info["ticker"])
                for label, info in cfg["factor_sleeve"].items()]
    sector_t = [(label, info["ticker"])
                for label, info in cfg["sector_sleeve"].items()]
    regime_t        = cfg["regime_baseline"]["ticker"]
    regime_compare_t = cfg.get("regime_cash_compare", {}).get("ticker", cfg["cash_proxy"]["ticker"])
    cash_t          = cfg["cash_proxy"]["ticker"]   # may be synthetic "CASH"

    # Build TER map (from config, fallback to DEFAULT_TER)
    ter_map = dict(DEFAULT_TER)
    for sleeve in ("factor_sleeve", "sector_sleeve"):
        for info in cfg[sleeve].values():
            t = info["ticker"]
            ter_map[t] = info.get("ter_pct", DEFAULT_TER.get(t, 0.25))

    return factor_t, sector_t, regime_t, regime_compare_t, cash_t, ter_map


# ── Price data ─────────────────────────────────────────────────────
def fetch_prices(tickers: list, use_cache: bool = False) -> dict:
    """Returns {"close": df, "high": df, "low": df}."""
    if use_cache and CACHE_PATH.exists():
        try:
            cached = pd.read_pickle(CACHE_PATH)
            if isinstance(cached, dict) and "close" in cached:
                log.info("Using cached prices (OHLC)")
                return cached
        except Exception:
            pass
        log.info("Cache format outdated, re-downloading")

    log.info(f"Downloading {len(tickers)} tickers from yfinance...")
    raw = yf.download(tickers, start=DL_FROM, progress=False,
                      auto_adjust=True, threads=True)
    if isinstance(raw.columns, pd.MultiIndex):
        close = raw["Close"]
        high  = raw["High"]
        low   = raw["Low"]
    else:
        t0    = tickers[0]
        close = raw[["Close"]].rename(columns={"Close": t0})
        high  = raw[["High"]].rename(columns={"High":  t0})
        low   = raw[["Low"]].rename(columns={"Low":   t0})

    close, high, low = close.ffill(), high.ffill(), low.ffill()
    result = {"close": close, "high": high, "low": low}
    pd.to_pickle(result, CACHE_PATH)
    log.info(f"  Downloaded {close.shape[1]} tickers × {len(close)} days")
    return result


def apply_ter(prices: pd.DataFrame, ter_map: dict) -> pd.DataFrame:
    """Multiply each price series by cumulative daily TER drag."""
    result = prices.copy().astype(float)
    for col in result.columns:
        ter_pct = ter_map.get(col, 0.0)
        if ter_pct > 0:
            daily_drag = (1 - ter_pct / 100) ** (1 / 252)
            n = len(result)
            result[col] *= daily_drag ** np.arange(n)
    return result


def compute_smooth_prices(prices_high: pd.DataFrame, prices_low: pd.DataFrame,
                          prices_close: pd.DataFrame,
                          strategy_cols: list, ter_map: dict) -> pd.DataFrame:
    """EMA(EMA_SPAN) of TER-adjusted (High+Low)/2 for strategy tickers."""
    cols = [c for c in strategy_cols
            if c in prices_high.columns and c in prices_low.columns]
    median = (prices_high[cols] + prices_low[cols]) / 2
    # Fall back to close for tickers missing H/L
    for c in strategy_cols:
        if c not in cols and c in prices_close.columns:
            median[c] = prices_close[c]
    median_adj = apply_ter(median, ter_map)
    return median_adj.ewm(span=EMA_SPAN, adjust=False).mean()


# ── Backtest ───────────────────────────────────────────────────────
def month_end_dates(idx: pd.DatetimeIndex) -> set:
    s = pd.Series(idx, index=idx)
    ends = s.groupby(s.dt.to_period("M")).apply(lambda g: g.index[-1])
    return set(ends.values)


def score_composite(ticker: str, d, prices: pd.DataFrame, pos_map: dict,
                    w21: int = 21, w84: int = 84) -> float:
    """50/50 blend of 21d and 84d raw momentum."""
    SYNTHETIC_CASH = "CASH"
    if ticker == SYNTHETIC_CASH:
        return 0.0
    pos = pos_map.get(d, -1)
    if pos < w84 or ticker not in prices.columns:
        return np.nan
    p_now = float(prices.iloc[pos][ticker])
    p_21  = float(prices.iloc[pos - w21][ticker])
    p_84  = float(prices.iloc[pos - w84][ticker])
    if p_21 <= 0 or p_84 <= 0:
        return np.nan
    return 0.5 * (p_now / p_21 - 1) + 0.5 * (p_now / p_84 - 1)


def score_accel(ticker: str, d, smooth: pd.DataFrame, pos_map: dict) -> float:
    """
    Accelerated momentum on EMA-smoothed median price.
    Score = ROC(ACCEL_LOOKBACK) + Acceleration
    where Acceleration = ROC(last ACCEL_WINDOW days) - ROC(prior ACCEL_WINDOW days).
    Assets with rising momentum (positive acceleration) are rewarded.
    """
    if ticker == "CASH":
        return 0.0
    pos = pos_map.get(d, -1)
    min_pos = max(ACCEL_LOOKBACK, 2 * ACCEL_WINDOW)
    if pos < min_pos or ticker not in smooth.columns:
        return np.nan

    try:
        p_now  = float(smooth.iloc[pos][ticker])
        p_lb   = float(smooth.iloc[pos - ACCEL_LOOKBACK][ticker])
        p_w    = float(smooth.iloc[pos - ACCEL_WINDOW][ticker])
        p_2w   = float(smooth.iloc[pos - 2 * ACCEL_WINDOW][ticker])
    except Exception:
        return np.nan

    if any(v <= 0 for v in [p_now, p_lb, p_w, p_2w]):
        return np.nan

    roc   = p_now / p_lb - 1
    accel = (p_now / p_w - 1) - (p_w / p_2w - 1)
    return roc + accel


def run_backtest(prices: pd.DataFrame,
                 factor_tickers: list,   # [(label, ticker), ...]
                 sector_tickers: list,
                 regime_ticker: str,
                 regime_compare_ticker: str,  # used only for regime gate comparison
                 cash_ticker: str,            # "CASH" = synthetic flat (0% return)
                 n_factor: int = 1,
                 n_sector: int = 1,
                 metric: str = "raw",
                 prices_smooth: pd.DataFrame = None) -> tuple:
    """
    Dual-sleeve monthly rotation.
    metric: "raw" uses SEL_LB-day return; "composite" uses 50% 21d + 50% 84d return.
    Returns (equity_curve, alloc_log) where:
      equity_curve: [{"date": "YYYY-MM-DD", "value": float}, ...]
      alloc_log:    [{"date": "YYYY-MM-DD", "holdings": {ticker: weight}}, ...]
    """
    f_tickers = [t for _, t in factor_tickers]
    s_tickers = [t for _, t in sector_tickers]

    all_idx  = prices.index
    rebal_set = month_end_dates(all_idx)
    pos_map  = {d: i for i, d in enumerate(all_idx)}

    warmup   = max(REG_LB, 84 if metric == "composite" else SEL_LB)
    sim_dates = all_idx[all_idx >= pd.Timestamp(START)]
    min_date  = all_idx[warmup] if len(all_idx) > warmup else all_idx[-1]

    cash_bal = float(CAPITAL)
    shares   = {}
    equity   = []
    alloc    = []
    pending  = None

    SYNTHETIC_CASH = "CASH"   # flat ticker — price always 1.0, 0% return

    def price_at(ticker, d):
        if ticker == SYNTHETIC_CASH:
            return 1.0
        if ticker in prices.columns and d in prices.index:
            v = prices.loc[d, ticker]
            return float(v) if not np.isnan(v) else 0.0
        return 0.0

    def ret_lb(ticker, d, lb):
        if ticker == SYNTHETIC_CASH:
            return 0.0
        pos = pos_map.get(d, -1)
        if pos < lb or ticker not in prices.columns:
            return np.nan
        p0 = float(prices.iloc[pos - lb][ticker])
        p1 = float(prices.iloc[pos][ticker])
        if p0 <= 0:
            return np.nan
        return p1 / p0 - 1

    def score(ticker):
        if metric == "composite":
            return score_composite(ticker, d, prices, pos_map)
        if metric == "accelerated_momentum":
            if prices_smooth is not None:
                return score_accel(ticker, d, prices_smooth, pos_map)
            return np.nan
        return ret_lb(ticker, d, SEL_LB)

    for d in sim_dates:
        # ── Execute pending rebalance ────────────────────────────
        if pending is not None:
            all_t = set(shares) | set(pending)
            px = {t: price_at(t, d) for t in all_t}

            value = cash_bal + sum(shares.get(t, 0.0) * px.get(t, 0.0)
                                   for t in shares)
            new_sh = {}
            for t, w in pending.items():
                p = px.get(t, 0.0)
                if p > 0:
                    new_sh[t] = (value * w) / p

            # No transaction cost when moving to/from flat cash
            real_t = {t for t in all_t if t != SYNTHETIC_CASH}
            cost = sum(
                abs(new_sh.get(t, 0.0) * px.get(t, 0.0) -
                    shares.get(t, 0.0) * px.get(t, 0.0)) * COST
                for t in real_t
            )
            cash_bal = value - sum(new_sh[t] * px[t] for t in new_sh) - cost
            shares   = new_sh
            pending  = None

        # ── Mark to market ───────────────────────────────────────
        held = sum(sh * price_at(t, d) for t, sh in shares.items())
        equity.append({"date": d.strftime("%Y-%m-%d"),
                       "value": round(cash_bal + held, 2)})

        if d not in rebal_set or d < min_date:
            continue

        # ── Regime gate ──────────────────────────────────────────
        r_mkt     = ret_lb(regime_ticker,         d, REG_LB)
        r_compare = ret_lb(regime_compare_ticker, d, REG_LB)
        if (not np.isnan(r_mkt) and not np.isnan(r_compare)
                and r_mkt <= r_compare):
            pending = {cash_ticker: 1.0}
            alloc.append({"date": d.strftime("%Y-%m-%d"),
                          "holdings": {cash_ticker: 1.0}})
            continue

        # ── Selection ────────────────────────────────────────────
        def top_n(tickers, n):
            sc = {t: score(t) for t in tickers}
            sc = {t: v for t, v in sc.items() if not np.isnan(v)}
            return sorted(sc, key=sc.__getitem__, reverse=True)[:n]

        f_picks = top_n(f_tickers, n_factor)
        s_picks = top_n(s_tickers, n_sector)

        if not f_picks and not s_picks:
            continue

        w = {}
        for t in f_picks:
            w[t] = w.get(t, 0.0) + 0.5 / max(len(f_picks), 1)
        for t in s_picks:
            w[t] = w.get(t, 0.0) + 0.5 / max(len(s_picks), 1)

        pending = w
        alloc.append({"date": d.strftime("%Y-%m-%d"),
                      "holdings": {k: round(v, 4) for k, v in w.items()}})

    return equity, alloc


# ── Output helpers ─────────────────────────────────────────────────
def alloc_to_matrix(alloc_log: list) -> dict:
    """Convert alloc_log to compact matrix for the stacked-area chart."""
    # Collect all unique tickers in order of first appearance
    seen = []
    for e in alloc_log:
        for t in e["holdings"]:
            if t not in seen:
                seen.append(t)

    dates   = [e["date"] for e in alloc_log]
    weights = [[round(e["holdings"].get(t, 0.0), 4) for t in seen]
               for e in alloc_log]
    return {"tickers": seen, "dates": dates, "weights": weights}


def current_signal(alloc_log: list, cfg: dict) -> dict:
    """Most recent allocation enriched with Nordnet proxy info."""
    if not alloc_log:
        return {}
    last = alloc_log[-1]

    # Build lookup: ticker → {label, sleeve, nordnet_name, isin}
    info = {}
    for label, v in cfg["factor_sleeve"].items():
        info[v["ticker"]] = {**v, "label": label, "sleeve": "factor"}
    for label, v in cfg["sector_sleeve"].items():
        info[v["ticker"]] = {**v, "label": label, "sleeve": "sector"}
    cp = cfg["cash_proxy"]
    info[cp["ticker"]] = {**cp, "label": "CASH", "sleeve": "cash"}

    holdings = []
    for t, w in last["holdings"].items():
        i = info.get(t, {"ticker": t, "label": t, "sleeve": "", "nordnet_name": "", "isin": ""})
        holdings.append({
            "ticker":       t,
            "weight":       w,
            "sleeve":       i.get("sleeve", ""),
            "label":        i.get("label", t),
            "nordnet_name": i.get("nordnet_name", ""),
            "isin":         i.get("isin", ""),
        })

    return {
        "date":     last["date"],
        "holdings": sorted(holdings, key=lambda x: (x["sleeve"], x["label"])),
    }


def compute_stats(equity_curve: list) -> dict:
    """CAGR, Sharpe, MaxDD, annual + monthly returns from equity curve."""
    if len(equity_curve) < 20:
        return {}

    dates  = pd.to_datetime([e["date"] for e in equity_curve])
    values = np.array([e["value"] for e in equity_curve], dtype=float)

    rets   = np.diff(values) / values[:-1]
    n_yrs  = (dates[-1] - dates[0]).days / 365.25
    cagr   = (values[-1] / values[0]) ** (1 / n_yrs) - 1 if n_yrs > 0 else 0.0

    ann_ret = np.mean(rets) * 252
    ann_vol = np.std(rets, ddof=1) * np.sqrt(252)
    sharpe  = ann_ret / ann_vol if ann_vol > 0 else 0.0

    peak   = np.maximum.accumulate(values)
    max_dd = float(((values - peak) / peak).min())

    df = pd.DataFrame({"value": values}, index=dates)

    # MaxDD using only month-end NAV values (smoother, ignores intramonth spikes)
    mo_ends = df.resample("ME").last()["value"].values
    mo_peak = np.maximum.accumulate(mo_ends)
    max_dd_monthly = float(((mo_ends - mo_peak) / mo_peak).min()) if len(mo_ends) > 1 else max_dd

    # Annual stats: return, Sharpe, MaxDD, volatility — per calendar year
    annual = {}
    for yr, grp in df.groupby(df.index.year):
        yr_vals = grp["value"].values
        yr_rets = np.diff(yr_vals) / yr_vals[:-1]
        yr_ret  = float(yr_vals[-1] / yr_vals[0] - 1)
        yr_vol  = float(np.std(yr_rets, ddof=1) * np.sqrt(252)) if len(yr_rets) > 1 else 0.0
        yr_sh   = float(np.mean(yr_rets) * 252 / yr_vol) if yr_vol > 0 else 0.0
        yr_peak = np.maximum.accumulate(yr_vals)
        yr_dd   = float(((yr_vals - yr_peak) / yr_peak).min())
        # Also DD on month-end prices within the year
        yr_mo = df.loc[df.index.year == yr].resample("ME").last()["value"].values
        yr_mo_peak = np.maximum.accumulate(yr_mo)
        yr_dd_mo = float(((yr_mo - yr_mo_peak) / yr_mo_peak).min()) if len(yr_mo) > 1 else yr_dd
        annual[str(yr)] = {
            "ret":    round(yr_ret,   4),
            "sharpe": round(yr_sh,    2),
            "max_dd": round(yr_dd,    4),
            "max_dd_mo": round(yr_dd_mo, 4),
            "vol":    round(yr_vol,   4),
        }

    # Monthly returns: compare first vs last nav within each calendar month
    monthly: dict[str, dict[str, float]] = {}
    for (yr, mo), grp in df.groupby([df.index.year, df.index.month]):
        monthly.setdefault(str(yr), {})[str(mo)] = round(
            float(grp["value"].iloc[-1] / grp["value"].iloc[0] - 1), 4
        )

    return {
        "cagr":           round(float(cagr),           4),
        "sharpe":         round(float(sharpe),         4),
        "max_dd":         round(float(max_dd),         4),
        "max_dd_monthly": round(float(max_dd_monthly), 4),
        "ann_vol":        round(float(ann_vol),        4),
        "total":          round(float(values[-1] / values[0] - 1), 4),
        "annual":         annual,
        "monthly":        monthly,
    }


def prices_to_series(prices: pd.DataFrame, ticker: str) -> list:
    if ticker not in prices.columns:
        return []
    s = prices[ticker].loc[prices.index >= pd.Timestamp(START)]
    return [{"date": d.strftime("%Y-%m-%d"), "value": round(float(v), 6)}
            for d, v in s.items() if not np.isnan(v)]


# ── Main ───────────────────────────────────────────────────────────
def run(cfg: dict = None, use_cache: bool = False):
    if cfg is None:
        cfg = load_config()

    factor_t, sector_t, regime_t, regime_compare_t, cash_t, ter_map = parse_config(cfg)

    # Low-corr extra tickers: add to download list + TER map
    lc_tickers = [v["ticker"] for v in LOW_CORR_EXTRA.values()]
    for v in LOW_CORR_EXTRA.values():
        ter_map.setdefault(v["ticker"], v["ter_pct"])

    # Screening candidates: load config and add tickers to download list
    screening_cfg = {}
    screening_tickers = []
    if SCREENING_CONFIG.exists():
        try:
            screening_cfg = json.loads(SCREENING_CONFIG.read_text())
            screening_tickers = [c["ticker"] for c in screening_cfg.get("candidates", [])]
        except Exception as e:
            log.warning(f"Could not load screening_config.json: {e}")

    strategy_tickers = ([t for _, t in factor_t] + [t for _, t in sector_t]
                        + [regime_t, regime_compare_t]
                        + ([cash_t] if cash_t != "CASH" else [])
                        + lc_tickers)
    bench_tickers  = list(set(BENCHMARKS.values()))
    all_dl_tickers = list(dict.fromkeys(strategy_tickers + bench_tickers + screening_tickers))

    # Prefer SQLite DB; fall back to yfinance download
    try:
        from db import load_etf_prices
        prices_dict = load_etf_prices(all_dl_tickers, path=DB_PATH)
        if prices_dict and prices_dict.get("close") is not None and not prices_dict["close"].empty:
            log.info("Loaded prices from SQLite DB (%d tickers × %d days)",
                     prices_dict["close"].shape[1], len(prices_dict["close"]))
        else:
            log.info("DB empty — falling back to yfinance download")
            prices_dict = fetch_prices(all_dl_tickers, use_cache=use_cache)
    except Exception as _db_err:
        log.warning("DB load failed (%s) — falling back to yfinance", _db_err)
        prices_dict = fetch_prices(all_dl_tickers, use_cache=use_cache)

    prices_raw  = prices_dict["close"]
    prices_high = prices_dict.get("high", prices_raw)
    prices_low  = prices_dict.get("low",  prices_raw)

    # Apply TER to Close prices for all strategy tickers
    strategy_cols = [t for t in strategy_tickers if t in prices_raw.columns]
    prices_adj    = prices_raw.copy()
    prices_adj[strategy_cols] = apply_ter(prices_raw[strategy_cols], ter_map)

    # EMA-smoothed median prices for accelerated_momentum scoring
    prices_smooth = compute_smooth_prices(prices_high, prices_low, prices_raw,
                                          strategy_cols, ter_map)

    # Low-corr basket universe — "no_gold" variant (best from sweep B)
    # Normal factor sleeve; sector restricted to 5 low-corr sectors, no GLD
    lc_sector_t = (
        [(lbl, t) for lbl, t in sector_t if lbl in LOW_CORR_SECTOR_KEEP]
        + [(lbl, v["ticker"]) for lbl, v in LOW_CORR_EXTRA.items() if lbl != "GOLD"]
    )
    lc_factor_t = factor_t   # unchanged — no GLD in factor sleeve

    def bt(f_t, s_t, n_f, n_s, metric, label):
        log.info(f"Running {label}...")
        return run_backtest(prices_adj, f_t, s_t, regime_t, regime_compare_t, cash_t,
                            n_f, n_s, metric, prices_smooth)

    eq1,   al1   = bt(factor_t,    sector_t,    1, 1, "raw",                  "D1-raw")
    eq2,   al2   = bt(factor_t,    sector_t,    2, 2, "raw",                  "D2-raw")
    eq1c,  al1c  = bt(factor_t,    sector_t,    1, 1, "composite",            "D1-composite")
    eq2c,  al2c  = bt(factor_t,    sector_t,    2, 2, "composite",            "D2-composite")
    eq1a,  al1a  = bt(factor_t,    sector_t,    1, 1, "accelerated_momentum", "D1-accel")
    eq2a,  al2a  = bt(factor_t,    sector_t,    2, 2, "accelerated_momentum", "D2-accel")
    eq1lc, al1lc = bt(lc_factor_t, lc_sector_t, 1, 1, "raw",                 "D1-lowcorr")
    eq2lc, al2lc = bt(lc_factor_t, lc_sector_t, 2, 2, "raw",                 "D2-lowcorr")

    # Benchmark raw close series (no TER)
    benchmarks_out = {}
    for name, t in BENCHMARKS.items():
        benchmarks_out[name] = {
            "ticker": t,
            "series": prices_to_series(prices_raw, t),
        }

    def strat_entry(label, eq, al):
        return {
            "label":          label,
            "nav":            eq,
            "stats":          compute_stats(eq),
            "allocation":     alloc_to_matrix(al),
            "current_signal": current_signal(al, cfg),
        }

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "start_date":   START,
        "strategies": {
            "top1_top1":    strat_entry("D1 — raw",         eq1,   al1),
            "top2_top2":    strat_entry("D2 — raw",         eq2,   al2),
            "d1_composite": strat_entry("D1-composite",     eq1c,  al1c),
            "d2_composite": strat_entry("D2-composite",     eq2c,  al2c),
            "d1_accel":     strat_entry("D1-accel.",        eq1a,  al1a),
            "d2_accel":     strat_entry("D2-accel.",        eq2a,  al2a),
            "d1_lowcorr":   strat_entry("D1-low-corr.",    eq1lc, al1lc),
            "d2_lowcorr":   strat_entry("D2-low-corr.",    eq2lc, al2lc),
        },
        "benchmarks":      benchmarks_out,
        "config_snapshot": cfg,
    }

    # ── PPM strategy ──────────────────────────────────────────────────
    if _PPM_AVAILABLE:
        try:
            # Extract ETF-cash months directly from the in-memory allocation
            d1a_alloc = out["strategies"]["d1_accel"]["allocation"]
            cash_idx  = d1a_alloc["tickers"].index("CASH")
            from pandas import Timestamp
            etf_cash_months = {
                (Timestamp(dt).year, Timestamp(dt).month)
                for dt, w in zip(d1a_alloc["dates"], d1a_alloc["weights"])
                if w[cash_idx] > 0
            }
            ppm_result = _run_ppm(PPM_DATA_FILE, etf_cash_months, db_path=DB_PATH)
            if ppm_result is not None:
                out["strategies"]["ppm_top3"] = ppm_result
            else:
                log.warning("PPM engine returned None — skipping ppm_top3")

            ppm_recent = _run_ppm(PPM_DATA_FILE, etf_cash_months, db_path=DB_PATH,
                                  start_date="2020-01-01",
                                  label="PPM — top3 (2020+)")
            if ppm_recent is not None:
                out["strategies"]["ppm_top3_recent"] = ppm_recent
        except Exception as e:
            log.warning(f"PPM engine failed: {e}")
    else:
        log.warning("ppm_engine module not available — skipping ppm_top3")

    # ── Screening ─────────────────────────────────────────────────────
    if screening_cfg and screening_tickers:
        try:
            # Build EMA-smoothed prices for screening tickers not in prices_smooth
            scr_extra = [t for t in screening_tickers if t not in prices_smooth.columns and t in prices_raw.columns]
            if scr_extra:
                scr_smooth = prices_raw[scr_extra].ewm(span=EMA_SPAN, adjust=False).mean()
                prices_scr = pd.concat([prices_smooth, scr_smooth], axis=1)
            else:
                prices_scr = prices_smooth

            # Build pos_map for the full price index
            all_idx_sm = prices_scr.index
            pos_map_sm = {d: i for i, d in enumerate(all_idx_sm)}
            last_date  = all_idx_sm[-1]

            # Current D1-accel holdings: find min score (portfolio_threshold)
            last_alloc = al1a[-1] if al1a else None
            portfolio_threshold = 0.0
            if last_alloc:
                held_tickers = list(last_alloc["holdings"].keys())
                held_scores  = [
                    score_accel(t, last_date, prices_scr, pos_map_sm)
                    for t in held_tickers if t != "CASH"
                ]
                valid_scores = [s for s in held_scores if not np.isnan(s)]
                if valid_scores:
                    portfolio_threshold = float(min(valid_scores))

            candidates_out = []
            for cand in screening_cfg.get("candidates", []):
                ticker = cand["ticker"]
                label  = cand.get("label", ticker)
                note   = cand.get("note", "")
                try:
                    sc  = score_accel(ticker, last_date, prices_scr, pos_map_sm)
                    # Raw ROC63 from smooth prices
                    pos = pos_map_sm.get(last_date, -1)
                    roc = np.nan
                    if pos >= 63 and ticker in prices_scr.columns:
                        p0 = float(prices_scr.iloc[pos - 63][ticker])
                        p1 = float(prices_scr.iloc[pos][ticker])
                        if p0 > 0:
                            roc = p1 / p0 - 1

                    if np.isnan(sc):
                        candidates_out.append({
                            "ticker": ticker, "label": label, "note": note,
                            "score": None, "roc_63d": None,
                            "would_select": False,
                            "error": "Insufficient data or ticker not downloaded",
                        })
                    else:
                        would_select = (sc > portfolio_threshold) and (not np.isnan(roc) and roc > 0)
                        candidates_out.append({
                            "ticker": ticker, "label": label, "note": note,
                            "score":       round(float(sc),  6),
                            "roc_63d":     round(float(roc), 6) if not np.isnan(roc) else None,
                            "would_select": bool(would_select),
                            "error":        None,
                        })
                except Exception as e:
                    candidates_out.append({
                        "ticker": ticker, "label": label, "note": note,
                        "score": None, "roc_63d": None,
                        "would_select": False,
                        "error": str(e),
                    })

            out["screening"] = {
                "computed_at":         datetime.now(timezone.utc).isoformat(),
                "portfolio_threshold": round(portfolio_threshold, 6),
                "candidates":          candidates_out,
            }

            # Persist to screener_history table for streak tracking
            try:
                from db import upsert_screener_history, init_db
                init_db(DB_PATH)
                run_date = datetime.now().strftime("%Y-%m-%d")
                upsert_screener_history(candidates_out, run_date, path=DB_PATH)
                log.info(f"Screener history upserted ({len(candidates_out)} tickers, {run_date})")
            except Exception as he:
                log.warning(f"Screener history upsert failed: {he}")

        except Exception as e:
            log.warning(f"Screening computation failed: {e}")

    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(DATA_PATH, "w") as f:
        json.dump(out, f, separators=(",", ":"))

    size_kb = DATA_PATH.stat().st_size // 1024
    log.info(f"Wrote {DATA_PATH}  ({size_kb} KB)")


if __name__ == "__main__":
    use_cache = "--quick" in sys.argv
    run(use_cache=use_cache)
