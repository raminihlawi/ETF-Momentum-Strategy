"""
sp500_pit_engine.py — D1-ACCEL single-stock rotation (point-in-time S&P 500)
=============================================================================
Called by engine.py. Returns strategy entries compatible with the dashboard
format: {label, nav, stats, allocation, current_signal}.

Runs Top-5 and Top-10. Uses:
  - sp500_data/*.csv.gz          : yfinance current S&P 500 members
  - sp500_removed_tiingo_data/*.csv : Tiingo adj prices, removed members
  - sp500_ticker_start_end.csv   : point-in-time membership history
"""

import glob, os, logging
import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

ACCEL_LOOKBACK = 84
ACCEL_WINDOW   = 20
EMA_SPAN       = 3
REG_LB         = 84
COST           = 0.003
CAPITAL        = 100_000.0
START          = "2019-10-01"

TOP_NS         = [5, 7, 10]   # optimized via parameter sweep (lb=84, win=20, ema=3)


def _build_membership(csv_path: Path):
    df = pd.read_csv(csv_path)
    df["start_date"] = pd.to_datetime(df["start_date"], errors="coerce")
    df["end_date"]   = pd.to_datetime(df["end_date"],   errors="coerce")
    intervals = {}
    for _, row in df.iterrows():
        t = row["ticker"]
        intervals.setdefault(t, []).append((row["start_date"], row["end_date"]))

    def valid_at_date(date):
        valid = set()
        for t, ivs in intervals.items():
            for s, e in ivs:
                if pd.isna(s):
                    continue
                if date >= s and (pd.isna(e) or date <= e):
                    valid.add(t)
                    break
        return valid

    return valid_at_date


def _load_tiingo(path: Path):
    try:
        df = pd.read_csv(path, index_col=0, parse_dates=True)
        df.index = pd.to_datetime(df.index)
        df = df.rename(columns={"adjHigh": "High", "adjLow": "Low", "adjClose": "Close"})
        return df[["High", "Low", "Close"]].dropna().sort_index()
    except Exception:
        return None


def _load_yf_cache(path: Path):
    try:
        df = pd.read_csv(path, index_col=0, parse_dates=True, compression="gzip")
        df.index = pd.to_datetime(df.index)
        df.columns = [str(c).capitalize() for c in df.columns]
        return df[["High", "Low", "Close"]].dropna().sort_index()
    except Exception:
        return None


def _load_all_data(sp500_dir: Path, tiingo_dir: Path, intervals: dict):
    min_len = ACCEL_LOOKBACK + 2 * ACCEL_WINDOW + 50
    data = {}
    tiingo_t = {p.stem for p in tiingo_dir.glob("*.csv")} if tiingo_dir.exists() else set()
    yf_t     = {p.name.replace(".csv.gz", "") for p in sp500_dir.glob("*.csv.gz")} if sp500_dir.exists() else set()

    for t in sorted(intervals.keys()):
        frames = []
        if t in tiingo_t:
            df = _load_tiingo(tiingo_dir / f"{t}.csv")
            if df is not None and len(df) > 10:
                frames.append(df)
        if t in yf_t:
            df = _load_yf_cache(sp500_dir / f"{t}.csv.gz")
            if df is not None and len(df) > 10:
                frames.append(df)
        if not frames:
            continue
        if len(frames) == 1:
            combined = frames[0]
        else:
            overlap_start = frames[1].index[0]
            combined = pd.concat([frames[0][frames[0].index < overlap_start], frames[1]]).sort_index()
        combined = combined[~combined.index.duplicated(keep="last")]
        if len(combined) >= min_len:
            data[t] = combined
    return data


def _load_spy():
    try:
        spy = yf.download("SPY", start="2015-01-01", auto_adjust=True, progress=False)
        spy.index = pd.to_datetime(spy.index)
        spy.columns = [c[0] if isinstance(c, tuple) else c for c in spy.columns]
        return spy["Close"].rename("SPY")
    except Exception as e:
        log.warning("Could not load SPY: %s", e)
        return None


def _build_smooth(data: dict) -> pd.DataFrame:
    mid = {t: ((df["High"] + df["Low"]) / 2).rename(t) for t, df in data.items()}
    mid_df = pd.concat(mid, axis=1).sort_index()
    return mid_df.ewm(span=EMA_SPAN, adjust=False).mean()


def _month_end_dates(idx):
    s = pd.Series(idx, index=idx)
    ends = s.groupby(s.dt.to_period("M")).apply(lambda g: g.index[-1])
    return set(ends.values)


def _accel(arr, pos):
    min_pos = ACCEL_LOOKBACK + 2 * ACCEL_WINDOW
    if pos < min_pos:
        return np.nan
    p_now = arr[pos];  p_lb = arr[pos - ACCEL_LOOKBACK]
    p_w   = arr[pos - ACCEL_WINDOW];  p_2w = arr[pos - 2 * ACCEL_WINDOW]
    if any(v <= 0 or np.isnan(v) for v in [p_now, p_lb, p_w, p_2w]):
        return np.nan
    return (p_now / p_lb - 1) + (p_now / p_w - 1) - (p_w / p_2w - 1)


def _simulate(data, smooth_df, spy_close, valid_at_date, top_n):
    tickers     = list(data.keys())
    ticker_set  = set(tickers)
    all_dates   = smooth_df.index
    pos_map     = {d: i for i, d in enumerate(all_dates)}
    rebal_set   = _month_end_dates(all_dates)
    close_mat   = pd.concat({t: data[t]["Close"] for t in tickers}, axis=1).reindex(all_dates).ffill()
    spy_al      = spy_close.reindex(all_dates).ffill()
    spy_arr     = spy_al.values
    spy_idx     = {d: i for i, d in enumerate(spy_al.index)}
    smooth_arrs = {t: smooth_df[t].values for t in tickers if t in smooth_df.columns}

    start_ts = pd.Timestamp(START)
    equity   = []       # [{"date": ..., "value": ...}]
    alloc    = []       # [{"date": ..., "holdings": {ticker: weight}}]
    holdings = {}
    cash     = CAPITAL
    pending  = None

    def price_at(t, d):
        if t in close_mat.columns and d in close_mat.index:
            v = close_mat.loc[d, t]
            return float(v) if not np.isnan(v) else 0.0
        return 0.0

    for date in all_dates:
        if date < start_ts:
            continue

        # Execute pending rebalance
        if pending is not None:
            all_h = set(holdings) | set(pending)
            px = {t: price_at(t, date) for t in all_h}
            port_val = cash + sum(holdings.get(t, 0) * px.get(t, 0) for t in holdings)
            new_sh   = {t: (port_val * w) / px[t] for t, w in pending.items() if px.get(t, 0) > 0}
            traded   = sum(abs(new_sh.get(t,0)*px.get(t,0) - holdings.get(t,0)*px.get(t,0)) for t in all_h)
            cash     = port_val - sum(new_sh[t]*px[t] for t in new_sh) - traded * COST
            holdings = new_sh
            pending  = None

        # MTM
        held_val = sum(sh * price_at(t, date) for t, sh in holdings.items())
        equity.append({"date": date.strftime("%Y-%m-%d"), "value": round(cash + held_val, 2)})

        if date not in rebal_set:
            continue

        # Regime gate: SPY 84d return ≤ 0 → cash
        si = spy_idx.get(date, -1)
        if si >= REG_LB:
            spy_ret = spy_arr[si] / spy_arr[si - REG_LB] - 1
            if spy_ret <= 0:
                pending = {"__CASH__": 1.0}
                alloc.append({"date": date.strftime("%Y-%m-%d"), "holdings": {"CASH": 1.0}})
                continue

        # Point-in-time universe
        valid = valid_at_date(date) & ticker_set
        pos   = pos_map[date]
        scores = {}
        for t in valid:
            if t not in smooth_arrs:
                continue
            s = _accel(smooth_arrs[t], pos)
            if not np.isnan(s):
                scores[t] = s

        if not scores:
            continue

        top = sorted(scores, key=scores.__getitem__, reverse=True)[:top_n]
        w   = {t: 1.0 / len(top) for t in top}
        pending = w
        alloc.append({"date": date.strftime("%Y-%m-%d"),
                      "holdings": {t: round(v, 4) for t, v in w.items()}})

    return equity, alloc


def _alloc_to_matrix(alloc_log):
    seen = []
    for e in alloc_log:
        for t in e["holdings"]:
            if t not in seen:
                seen.append(t)
    dates   = [e["date"] for e in alloc_log]
    weights = [[round(e["holdings"].get(t, 0.0), 4) for t in seen] for e in alloc_log]
    return {"tickers": seen, "dates": dates, "weights": weights}


def _current_signal(alloc_log):
    if not alloc_log:
        return {}
    last = alloc_log[-1]
    holdings = []
    for t, w in last["holdings"].items():
        holdings.append({
            "ticker":       t,
            "weight":       w,
            "sleeve":       "stock",
            "label":        t,
            "nordnet_name": "",
            "isin":         "",
        })
    return {"date": last["date"], "holdings": sorted(holdings, key=lambda x: -x["weight"])}


def _compute_stats(equity_curve):
    if len(equity_curve) < 20:
        return {}
    dates  = pd.to_datetime([e["date"] for e in equity_curve])
    values = np.array([e["value"] for e in equity_curve], dtype=float)
    rets   = np.diff(values) / values[:-1]
    n_yrs  = (dates[-1] - dates[0]).days / 365.25
    cagr   = (values[-1] / values[0]) ** (1 / n_yrs) - 1 if n_yrs > 0 else 0.0
    ann_vol = np.std(rets, ddof=1) * np.sqrt(252)
    sharpe  = (np.mean(rets) * 252) / ann_vol if ann_vol > 0 else 0.0
    peak    = np.maximum.accumulate(values)
    max_dd  = float(((values - peak) / peak).min())
    df = pd.DataFrame({"value": values}, index=dates)
    mo_ends  = df.resample("ME").last()["value"].values
    mo_peak  = np.maximum.accumulate(mo_ends)
    max_dd_mo = float(((mo_ends - mo_peak) / mo_peak).min()) if len(mo_ends) > 1 else max_dd
    annual = {}
    for yr, grp in df.groupby(df.index.year):
        yr_v = grp["value"].values
        yr_r = np.diff(yr_v) / yr_v[:-1]
        yr_ret = float(yr_v[-1] / yr_v[0] - 1)
        yr_vol = float(np.std(yr_r, ddof=1) * np.sqrt(252)) if len(yr_r) > 1 else 0.0
        yr_sh  = float(np.mean(yr_r) * 252 / yr_vol) if yr_vol > 0 else 0.0
        yr_pk  = np.maximum.accumulate(yr_v)
        yr_dd  = float(((yr_v - yr_pk) / yr_pk).min())
        yr_mo  = df.loc[df.index.year == yr].resample("ME").last()["value"].values
        yr_mo_pk = np.maximum.accumulate(yr_mo)
        yr_dd_mo = float(((yr_mo - yr_mo_pk) / yr_mo_pk).min()) if len(yr_mo) > 1 else yr_dd
        annual[str(yr)] = {"ret": round(yr_ret, 4), "sharpe": round(yr_sh, 2),
                           "max_dd": round(yr_dd, 4), "max_dd_mo": round(yr_dd_mo, 4),
                           "vol": round(yr_vol, 4)}
    monthly: dict = {}
    for (yr, mo), grp in df.groupby([df.index.year, df.index.month]):
        monthly.setdefault(str(yr), {})[str(mo)] = round(
            float(grp["value"].iloc[-1] / grp["value"].iloc[0] - 1), 4)
    return {
        "cagr":           round(float(cagr), 4),
        "sharpe":         round(float(sharpe), 4),
        "max_dd":         round(float(max_dd), 4),
        "max_dd_monthly": round(float(max_dd_mo), 4),
        "ann_vol":        round(float(ann_vol), 4),
        "total":          round(float(values[-1] / values[0] - 1), 4),
        "annual":         annual,
        "monthly":        monthly,
    }


def run_sp500_pit(data_root: Path) -> dict:
    """
    Run D1-ACCEL point-in-time S&P 500 simulation.
    Returns dict of strategy entries keyed by "sp500_pit_topN".
    Returns {} if data not available.
    """
    sp500_dir  = data_root / "sp500_data"
    tiingo_dir = data_root / "sp500_removed_tiingo_data"
    member_csv = data_root / "sp500_ticker_start_end.csv"

    if not member_csv.exists():
        log.warning("sp500_ticker_start_end.csv not found — skipping stock rotation")
        return {}
    if not sp500_dir.exists() and not tiingo_dir.exists():
        log.warning("No stock price data dirs found — skipping stock rotation")
        return {}

    log.info("SP500 PIT: loading membership ...")
    member_df = pd.read_csv(member_csv)
    member_df["start_date"] = pd.to_datetime(member_df["start_date"], errors="coerce")
    member_df["end_date"]   = pd.to_datetime(member_df["end_date"],   errors="coerce")
    intervals = {}
    for _, row in member_df.iterrows():
        intervals.setdefault(row["ticker"], []).append((row["start_date"], row["end_date"]))

    valid_at_date = _build_membership(member_csv)

    log.info("SP500 PIT: loading price data ...")
    data = _load_all_data(sp500_dir, tiingo_dir, intervals)
    if not data:
        log.warning("SP500 PIT: no price data loaded")
        return {}
    log.info("SP500 PIT: %d tickers loaded", len(data))

    spy = _load_spy()
    if spy is None:
        log.warning("SP500 PIT: no SPY data")
        return {}

    log.info("SP500 PIT: building smooth prices ...")
    smooth = _build_smooth(data)

    out = {}
    for n in TOP_NS:
        log.info("SP500 PIT: simulating Top-%d ...", n)
        eq, alloc = _simulate(data, smooth, spy, valid_at_date, top_n=n)
        key   = f"sp500_pit_top{n}"
        label = f"Aktier — Top {n}"
        out[key] = {
            "label":          label,
            "nav":            eq,
            "stats":          _compute_stats(eq),
            "allocation":     _alloc_to_matrix(alloc),
            "current_signal": _current_signal(alloc),
        }
        log.info("SP500 PIT: Top-%d done (%d equity pts)", n, len(eq))

    return out
