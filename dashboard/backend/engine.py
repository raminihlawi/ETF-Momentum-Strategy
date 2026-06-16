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

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

BASE_DIR    = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.json"
CACHE_PATH  = BASE_DIR / "_price_cache.pkl"
DATA_PATH   = BASE_DIR.parent / "frontend" / "static" / "data.json"

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
def fetch_prices(tickers: list, use_cache: bool = False) -> pd.DataFrame:
    if use_cache and CACHE_PATH.exists():
        log.info("Using cached prices")
        return pd.read_pickle(CACHE_PATH)

    log.info(f"Downloading {len(tickers)} tickers from yfinance...")
    raw = yf.download(tickers, start=DL_FROM, progress=False,
                      auto_adjust=True, threads=True)
    if isinstance(raw.columns, pd.MultiIndex):
        close = raw["Close"]
    else:
        # Single ticker
        close = raw[["Close"]].rename(columns={"Close": tickers[0]})

    close = close.ffill()
    close.to_pickle(CACHE_PATH)
    log.info(f"  Downloaded {close.shape[1]} tickers × {len(close)} days")
    return close


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


# ── Backtest ───────────────────────────────────────────────────────
def month_end_dates(idx: pd.DatetimeIndex) -> set:
    s = pd.Series(idx, index=idx)
    ends = s.groupby(s.dt.to_period("M")).apply(lambda g: g.index[-1])
    return set(ends.values)


def run_backtest(prices: pd.DataFrame,
                 factor_tickers: list,   # [(label, ticker), ...]
                 sector_tickers: list,
                 regime_ticker: str,
                 regime_compare_ticker: str,  # used only for regime gate comparison
                 cash_ticker: str,            # "CASH" = synthetic flat (0% return)
                 n_factor: int = 1,
                 n_sector: int = 1) -> tuple:
    """
    raw/sel126/reg252 dual-sleeve rotation.
    Returns (equity_curve, alloc_log) where:
      equity_curve: [{"date": "YYYY-MM-DD", "value": float}, ...]
      alloc_log:    [{"date": "YYYY-MM-DD", "holdings": {ticker: weight}}, ...]
    """
    f_tickers = [t for _, t in factor_tickers]
    s_tickers = [t for _, t in sector_tickers]

    all_idx  = prices.index
    rebal_set = month_end_dates(all_idx)
    pos_map  = {d: i for i, d in enumerate(all_idx)}

    sim_dates = all_idx[all_idx >= pd.Timestamp(START)]
    # First valid rebalance: need REG_LB trading days of history
    min_date  = all_idx[REG_LB] if len(all_idx) > REG_LB else all_idx[-1]

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

        # ── Regime gate (252d) ───────────────────────────────────
        r_mkt     = ret_lb(regime_ticker,         d, REG_LB)
        r_compare = ret_lb(regime_compare_ticker, d, REG_LB)
        if (not np.isnan(r_mkt) and not np.isnan(r_compare)
                and r_mkt <= r_compare):
            pending = {cash_ticker: 1.0}
            alloc.append({"date": d.strftime("%Y-%m-%d"),
                          "holdings": {cash_ticker: 1.0}})
            continue

        # ── Selection (126d raw return) ──────────────────────────
        def top_n(tickers, n):
            sc = {t: ret_lb(t, d, SEL_LB) for t in tickers}
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

    strategy_tickers = ([t for _, t in factor_t] + [t for _, t in sector_t]
                        + [regime_t, regime_compare_t]
                        + ([cash_t] if cash_t != "CASH" else []))
    bench_tickers    = list(set(BENCHMARKS.values()))
    all_dl_tickers   = list(dict.fromkeys(strategy_tickers + bench_tickers))

    prices_raw = fetch_prices(all_dl_tickers, use_cache=use_cache)

    # Apply TER only to strategy tickers
    strategy_cols = [t for t in strategy_tickers if t in prices_raw.columns]
    prices_adj    = prices_raw.copy()
    prices_adj[strategy_cols] = apply_ter(prices_raw[strategy_cols], ter_map)

    log.info("Running top1/top1 backtest...")
    eq1, al1 = run_backtest(prices_adj, factor_t, sector_t, regime_t, regime_compare_t, cash_t, 1, 1)

    log.info("Running top2/top2 backtest...")
    eq2, al2 = run_backtest(prices_adj, factor_t, sector_t, regime_t, regime_compare_t, cash_t, 2, 2)

    # Benchmark raw close series (no TER)
    benchmarks_out = {}
    for name, t in BENCHMARKS.items():
        benchmarks_out[name] = {
            "ticker": t,
            "series": prices_to_series(prices_raw, t),
        }

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "start_date":   START,
        "strategies": {
            "top1_top1": {
                "label":          "D1 — top1/top1",
                "nav":            eq1,
                "stats":          compute_stats(eq1),
                "allocation":     alloc_to_matrix(al1),
                "current_signal": current_signal(al1, cfg),
            },
            "top2_top2": {
                "label":          "D2 — top2/top2",
                "nav":            eq2,
                "stats":          compute_stats(eq2),
                "allocation":     alloc_to_matrix(al2),
                "current_signal": current_signal(al2, cfg),
            },
        },
        "benchmarks":      benchmarks_out,
        "config_snapshot": cfg,
    }

    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(DATA_PATH, "w") as f:
        json.dump(out, f, separators=(",", ":"))

    size_kb = DATA_PATH.stat().st_size // 1024
    log.info(f"Wrote {DATA_PATH}  ({size_kb} KB)")


if __name__ == "__main__":
    use_cache = "--quick" in sys.argv
    run(use_cache=use_cache)
