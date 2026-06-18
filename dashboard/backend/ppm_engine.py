#!/usr/bin/env python3
"""
PPM Rotation Engine
Runs the optimal PPM strategy (EMA10, ROC84, ACCEL30, TOP3, ETF-cash sync)
and returns a result dict in the same format as ETF strategies in engine.py.
"""
import logging
from pathlib import Path
from datetime import datetime, timezone

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# ── Universe ───────────────────────────────────────────────────────
UNIVERSE = {
    "581371": "AP7 Aktie",
    "283408": "Tech",
    "644005": "Healthcare",
    "517748": "Energy",
    "481911": "Mining",
    "479550": "Consumer Brands",
    "768556": "US Value",
    "916354": "US Small",
    "456475": "US Quality",
    "163923": "US Growth",
    "182759": "EUR Small",
    "538462": "EUR Value",
    "162099": "Multifactor",
    "545541": "Ränta (AP7)",
}

CASH_PPM  = "545541"   # AP7 Räntefond — ETF-cash shelter
BENCH_PPM = "581371"   # AP7 Aktiefond

FUND_NAMES = {
    "581371": "AP7 Aktiefond",
    "283408": "Swedbank Robur Technology A",
    "644005": "Handelsbanken Hälsovård Tema A1",
    "517748": "BlackRock World Energy A2",
    "481911": "BlackRock World Mining A2",
    "479550": "Seligson Global Top 25 Brands A",
    "768556": "BlackRock US Basic Value A2",
    "916354": "SEB Nordamerikafond Små och Medelstora A",
    "456475": "Länsförsäkringar USA Aktiv A",
    "163923": "Öhman Global Growth A",
    "182759": "Lannebo Europa Småbolag A",
    "538462": "AMF Aktiefond Europa",
    "162099": "Storebrand Global Multifactor A",
    "545541": "AP7 Räntefond",
}

# ── Strategy parameters ────────────────────────────────────────────
EMA_SPAN   = 10
ROC_DAYS   = 84
ACCEL_WIN  = 30
TOP_N      = 3


# ── Data loading ───────────────────────────────────────────────────
def load_ppm_data(data_file: Path) -> pd.DataFrame:
    """
    Read ppm_all_nav.csv, pivot to wide (date × ppm_number),
    reindex to business days, ffill.
    Returns DataFrame with str column names (ppm_number).
    """
    df = pd.read_csv(data_file, dtype={"ppm_number": str})
    df["date"] = pd.to_datetime(df["date"])
    # Remove epoch/invalid rows
    df = df[df["date"] > "2000-01-01"]

    # Keep only funds in our universe
    universe_ids = set(UNIVERSE.keys())
    df = df[df["ppm_number"].isin(universe_ids)]

    wide = df.pivot_table(index="date", columns="ppm_number", values="nav_sek", aggfunc="last")
    wide.columns = [str(c) for c in wide.columns]
    wide = wide.sort_index()

    # Reindex to business days
    bday_idx = pd.bdate_range(wide.index[0], wide.index[-1])
    wide = wide.reindex(bday_idx).ffill()

    return wide


# ── Signal computation ─────────────────────────────────────────────
def compute_signals(wide: pd.DataFrame) -> pd.DataFrame:
    """
    scores = ema_roc + (ema_roc - ema_roc.shift(ACCEL_WIN))
    """
    ema    = wide.ewm(span=EMA_SPAN, adjust=False).mean()
    roc_sc = ema / ema.shift(ROC_DAYS) - 1
    return roc_sc + (roc_sc - roc_sc.shift(ACCEL_WIN))


# ── Backtest ───────────────────────────────────────────────────────
def _run_backtest(wide: pd.DataFrame, scores: pd.DataFrame,
                  etf_cash_months: set):
    """
    Monthly top-N rotation with two cash triggers:
    1. ETF-cash sync: D1-accel in cash → 100% AP7 Räntefond
    2. PPM momentum filter: best eligible equity score < 0 → 100% AP7 Räntefond
    """
    min_days = ROC_DAYS + 2 * ACCEL_WIN + 10

    month_ends = pd.date_range(
        wide.index.min() + pd.DateOffset(months=6),
        wide.index.max(),
        freq="BME",
    )
    month_ends = month_ends[month_ends <= wide.index.max()]

    nav          = 100.0
    alloc_log    = []
    nav_series   = {}
    monthly_rets = []
    weights      = {}
    prev_dt      = None

    for me in month_ends:
        avail = wide.index[wide.index <= me]
        if not len(avail):
            continue
        dt = avail[-1]

        # ETF-cash sync: D1-accel in cash → 100% AP7 Räntefond
        if (me.year, me.month) in etf_cash_months:
            picks = {CASH_PPM}
        else:
            elig = [
                c for c in wide.columns
                if c != CASH_PPM
                and wide[c].first_valid_index() is not None
                and (dt - wide[c].first_valid_index()).days >= min_days
                and not np.isnan(scores.loc[dt, c])
            ]
            if not elig:
                continue
            top_scores = scores.loc[dt, elig].nlargest(TOP_N)
            # PPM momentum filter: all top candidates negative → go to cash
            if top_scores.iloc[0] < 0:
                picks = {CASH_PPM}
            else:
                picks = set(top_scores.index)

        # Compute monthly return from previous holdings
        if prev_dt is not None and weights:
            prev_avail = wide.index[wide.index <= prev_dt]
            p0  = prev_avail[-1]
            w   = 1.0 / len(weights)
            ret = 0.0
            for p in weights:
                if p not in wide.columns:
                    continue
                p0_val = wide.loc[p0, p] if p0 in wide.index else np.nan
                p1_val = wide.loc[dt, p]
                if not np.isnan(p0_val) and not np.isnan(p1_val) and p0_val > 0:
                    ret += w * (p1_val / p0_val - 1)
            monthly_rets.append(ret)
            nav *= (1 + ret)

        nav_series[dt] = nav
        weights  = {p: round(1.0 / len(picks), 6) for p in picks}
        prev_dt  = me

        alloc_log.append({
            "date":     dt.strftime("%Y-%m-%d"),
            "holdings": dict(weights),
        })

    return nav_series, alloc_log, monthly_rets


# ── Stats (from monthly returns) ───────────────────────────────────
def _compute_stats_monthly(nav_series: dict, monthly_rets: list) -> dict:
    if not nav_series or len(monthly_rets) < 3:
        return {}

    dates  = sorted(nav_series)
    values = np.array([nav_series[d] for d in dates], dtype=float)

    rets = np.array(monthly_rets, dtype=float)
    n_yrs = (dates[-1] - dates[0]).days / 365.25
    cagr  = (values[-1] / values[0]) ** (1 / n_yrs) - 1 if n_yrs > 0 else 0.0

    mean_mo  = float(np.mean(rets))
    std_mo   = float(np.std(rets, ddof=1)) if len(rets) > 1 else 0.0
    ann_ret  = mean_mo * 12
    ann_vol  = std_mo  * np.sqrt(12)
    sharpe   = ann_ret / ann_vol if ann_vol > 0 else 0.0

    peak   = np.maximum.accumulate(values)
    max_dd = float(((values - peak) / peak).min())

    df = pd.DataFrame({"value": values}, index=pd.DatetimeIndex(dates))

    # Monthly NAV maxDD
    mo_vals  = df.resample("ME").last()["value"].values
    mo_peak  = np.maximum.accumulate(mo_vals)
    max_dd_mo = float(((mo_vals - mo_peak) / mo_peak).min()) if len(mo_vals) > 1 else max_dd

    # Annual stats: group monthly rets by year
    ret_dates = dates[1:]   # each return corresponds to the end-of-period date
    annual = {}
    by_year: dict[int, list] = {}
    for i, ret in enumerate(rets):
        if i >= len(ret_dates):
            break
        yr = ret_dates[i].year
        by_year.setdefault(yr, []).append(ret)

    for yr, yr_rets in by_year.items():
        yr_arr  = np.array(yr_rets, dtype=float)
        yr_ret  = float(np.prod(1 + yr_arr) - 1)
        yr_std  = float(np.std(yr_arr, ddof=1) * np.sqrt(12)) if len(yr_arr) > 1 else 0.0
        yr_mean = float(np.mean(yr_arr)) * 12
        yr_sh   = yr_mean / yr_std if yr_std > 0 else 0.0
        # MaxDD from monthly NAV within the year
        yr_nav = df.loc[df.index.year == yr]["value"].values
        yr_peak = np.maximum.accumulate(yr_nav)
        yr_dd   = float(((yr_nav - yr_peak) / yr_peak).min()) if len(yr_nav) > 1 else 0.0
        annual[str(yr)] = {
            "ret":        round(yr_ret, 4),
            "sharpe":     round(yr_sh,  2),
            "max_dd":     round(yr_dd,  4),
            "max_dd_mo":  round(yr_dd,  4),
            "vol":        round(yr_std,  4),
        }

    # Monthly returns dict
    monthly: dict[str, dict[str, float]] = {}
    for i, ret in enumerate(rets):
        if i >= len(ret_dates):
            break
        d = ret_dates[i]
        monthly.setdefault(str(d.year), {})[str(d.month)] = round(float(ret), 4)

    return {
        "cagr":           round(float(cagr),    4),
        "sharpe":         round(float(sharpe),   4),
        "max_dd":         round(float(max_dd),   4),
        "max_dd_monthly": round(float(max_dd_mo),4),
        "ann_vol":        round(float(ann_vol),  4),
        "total":          round(float(values[-1] / values[0] - 1), 4),
        "annual":         annual,
        "monthly":        monthly,
    }


# ── True daily NAV from actual fund prices ─────────────────────────
def _daily_nav_true(alloc_log: list, wide: pd.DataFrame,
                    all_idx: pd.DatetimeIndex) -> list:
    """
    Compute daily portfolio NAV by applying actual daily fund-price returns
    within each holding period. Produces a smooth curve instead of the
    staircase that results from forward-filling monthly snapshots.
    """
    if not alloc_log:
        return []

    rebals = [(pd.Timestamp(e["date"]), e["holdings"]) for e in alloc_log]
    first_date = rebals[0][0]

    nav = 100.0
    result: dict = {first_date: nav}

    for i, (rebal_date, weights) in enumerate(rebals):
        next_date = rebals[i + 1][0] if i + 1 < len(rebals) else wide.index[-1]

        # Anchor prices at rebal_date
        if rebal_date in wide.index:
            prev_prices = wide.loc[rebal_date]
        else:
            avail = wide.index[wide.index <= rebal_date]
            prev_prices = wide.loc[avail[-1]] if len(avail) else None
        if prev_prices is None:
            continue

        current_nav = nav
        period_days = all_idx[(all_idx > rebal_date) & (all_idx <= next_date)]

        for day in period_days:
            if day not in wide.index:
                result[day] = current_nav
                continue
            day_prices = wide.loc[day]
            daily_ret = 0.0
            for ppm_id, w in weights.items():
                if ppm_id in wide.columns:
                    p0 = float(prev_prices[ppm_id])
                    p1 = float(day_prices[ppm_id])
                    if not np.isnan(p0) and not np.isnan(p1) and p0 > 0:
                        daily_ret += w * (p1 / p0 - 1)
            current_nav *= (1 + daily_ret)
            result[day] = current_nav
            prev_prices = day_prices

        nav = current_nav

    nav_s = pd.Series(result)
    nav_s.index = pd.DatetimeIndex(nav_s.index)
    daily = nav_s.reindex(all_idx[all_idx >= first_date]).ffill()

    return [{"date": d.strftime("%Y-%m-%d"), "value": round(float(v), 6)}
            for d, v in daily.items() if not np.isnan(v)]


# ── Allocation matrix ──────────────────────────────────────────────
def _alloc_matrix(alloc_log: list) -> dict:
    """
    Convert alloc_log to compact matrix.
    Uses fund *labels* (not ppm_numbers) as tickers for display.
    """
    seen = []
    for e in alloc_log:
        for ppm_id in e["holdings"]:
            label = UNIVERSE.get(ppm_id, ppm_id)
            if label not in seen:
                seen.append(label)

    dates   = [e["date"] for e in alloc_log]
    weights = []
    for e in alloc_log:
        label_hold = {UNIVERSE.get(k, k): v for k, v in e["holdings"].items()}
        weights.append([round(label_hold.get(t, 0.0), 4) for t in seen])

    return {"tickers": seen, "dates": dates, "weights": weights}


# ── Current signal ─────────────────────────────────────────────────
def _current_signal(alloc_log: list) -> dict:
    if not alloc_log:
        return {}
    last = alloc_log[-1]
    holdings = []
    for ppm_id, w in last["holdings"].items():
        holdings.append({
            "ticker":       ppm_id,
            "weight":       w,
            "sleeve":       "ppm",
            "label":        UNIVERSE.get(ppm_id, ppm_id),
            "nordnet_name": FUND_NAMES.get(ppm_id, ""),
            "isin":         "",
        })
    return {
        "date":     last["date"],
        "holdings": sorted(holdings, key=lambda x: x["label"]),
    }


# ── Public entry point ─────────────────────────────────────────────
def run_ppm(data_file: Path,
            etf_cash_months: set | None = None,
            db_path: Path | None = None,
            start_date: str | None = None,
            label: str | None = None) -> dict | None:
    """
    Run the PPM backtest and return a result dict compatible with
    the ETF strategy format used by engine.py.

    etf_cash_months: set of (year, month) where D1-accel was in cash.
    start_date: ISO date string to clip the backtest start (e.g. "2020-01-01").
    """
    # Prefer SQLite DB; fall back to CSV file
    wide = None
    if db_path is not None and db_path.exists():
        try:
            from db import load_ppm_nav
            wide = load_ppm_nav(ppm_numbers=list(UNIVERSE.keys()), path=db_path)
            if wide.empty or len(wide.columns) < 2:
                log.warning("DB PPM data too sparse — falling back to CSV")
                wide = None
            else:
                log.info("Loaded PPM NAV from SQLite DB (%d funds × %d days)",
                         len(wide.columns), len(wide))
        except Exception as e:
            log.warning(f"DB PPM load failed ({e}) — falling back to CSV")
            wide = None

    if wide is None:
        if not data_file.exists():
            log.warning(f"PPM data file not found: {data_file}")
            return None
        try:
            wide = load_ppm_data(data_file)
        except Exception as e:
            log.warning(f"Failed to load PPM data: {e}")
            return None

    if wide.empty or len(wide.columns) < 2:
        log.warning("PPM data loaded but too few funds to run backtest")
        return None

    if start_date:
        wide = wide[wide.index >= pd.Timestamp(start_date)]
        if wide.empty:
            log.warning("PPM data empty after start_date filter")
            return None

    scores = compute_signals(wide)

    if etf_cash_months is None:
        etf_cash_months = set()
    log.info(f"ETF cash months: {len(etf_cash_months)}")

    try:
        nav_series, alloc_log, monthly_rets = _run_backtest(
            wide, scores, etf_cash_months
        )
    except Exception as e:
        log.warning(f"PPM backtest failed: {e}")
        return None

    if not nav_series:
        log.warning("PPM backtest produced no NAV data")
        return None

    daily  = _daily_nav_true(alloc_log, wide, wide.index)
    stats  = _compute_stats_monthly(nav_series, monthly_rets)
    alloc  = _alloc_matrix(alloc_log)
    signal = _current_signal(alloc_log)

    log.info(
        f"PPM backtest done: {len(alloc_log)} months, "
        f"CAGR {stats.get('cagr', 0):.1%}, Sharpe {stats.get('sharpe', 0):.2f}"
    )

    return {
        "label":          label or "PPM — top3 ETF-cash sync",
        "nav":            daily,
        "stats":          stats,
        "allocation":     alloc,
        "current_signal": signal,
        "fund_names":     {UNIVERSE[k]: FUND_NAMES.get(k, k) for k in UNIVERSE},
    }
