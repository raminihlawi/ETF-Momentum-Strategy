#!/usr/bin/env python3
"""
Test PPM momentum strategy with all available funds in DB (no manual universe).
Does NOT modify dashboard or engine.py — read-only experiment.

Usage:
    python3 scripts/test_broad_ppm.py [--db path/to/dashboard.db] [--top N]
"""
import argparse
import logging
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

# Same signal params as ppm_engine.py
EMA_SPAN  = 10
ROC_DAYS  = 84
ACCEL_WIN = 30
TOP_N     = 3
MIN_DAYS  = ROC_DAYS + 2 * ACCEL_WIN + 10  # 154

# AP7 Räntefond — cash shelter
CASH_PPM  = "545541"
# AP7 Aktiefond — benchmark
BENCH_PPM = "581371"


def load_all_funds(db_path: Path) -> pd.DataFrame:
    import sqlite3
    con = sqlite3.connect(db_path)
    df = pd.read_sql(
        "SELECT ppm_number, date, nav_sek FROM ppm_nav WHERE date >= '2000-01-01' ORDER BY date",
        con,
    )
    con.close()

    df["date"] = pd.to_datetime(df["date"])
    wide = df.pivot_table(index="date", columns="ppm_number", values="nav_sek", aggfunc="last")
    wide.columns = [str(c) for c in wide.columns]
    wide = wide.sort_index()

    bday_idx = pd.bdate_range(wide.index[0], wide.index[-1])
    wide = wide.reindex(bday_idx).ffill()

    log.info("Loaded %d funds × %d days", len(wide.columns), len(wide))
    return wide


def compute_signals(wide: pd.DataFrame) -> pd.DataFrame:
    ema   = wide.ewm(span=EMA_SPAN, adjust=False).mean()
    roc   = ema / ema.shift(ROC_DAYS) - 1
    return roc + (roc - roc.shift(ACCEL_WIN))


def run_backtest(wide: pd.DataFrame, scores: pd.DataFrame, top_n: int = TOP_N) -> tuple:
    month_ends = pd.date_range(
        wide.index.min() + pd.DateOffset(months=6),
        wide.index.max(),
        freq="BME",
    )

    nav = 100.0
    nav_series   = {}
    monthly_rets = []
    weights      = {}
    prev_dt      = None
    cash_count   = 0

    for me in month_ends:
        avail = wide.index[wide.index <= me]
        if not len(avail):
            continue
        dt = avail[-1]

        # Eligible: enough history, valid score, not cash fund
        elig = [
            c for c in wide.columns
            if c != CASH_PPM
            and wide[c].first_valid_index() is not None
            and (dt - wide[c].first_valid_index()).days >= MIN_DAYS
            and not np.isnan(scores.loc[dt, c])
        ]
        if not elig:
            continue

        top_scores = scores.loc[dt, elig].nlargest(top_n)
        if top_scores.iloc[0] < 0:
            picks = {CASH_PPM}
            cash_count += 1
        else:
            picks = set(top_scores.index)

        # Monthly return
        if prev_dt is not None and weights:
            prev_avail = wide.index[wide.index <= prev_dt]
            p0 = prev_avail[-1]
            w  = 1.0 / len(weights)
            ret = 0.0
            for p in weights:
                if p not in wide.columns:
                    continue
                p0v = wide.loc[p0, p] if p0 in wide.index else np.nan
                p1v = wide.loc[dt, p]
                if not np.isnan(p0v) and not np.isnan(p1v) and p0v > 0:
                    ret += w * (p1v / p0v - 1)
            monthly_rets.append(ret)
            nav *= (1 + ret)

        nav_series[dt] = nav
        weights  = {p: 1.0 / len(picks) for p in picks}
        prev_dt  = me

    return nav_series, monthly_rets, cash_count


def stats(nav_series: dict, monthly_rets: list, top_n: int = TOP_N) -> dict:
    dates  = sorted(nav_series)
    values = np.array([nav_series[d] for d in dates], dtype=float)
    rets   = np.array(monthly_rets, dtype=float)

    n_yrs  = (dates[-1] - dates[0]).days / 365.25
    cagr   = (values[-1] / values[0]) ** (1 / n_yrs) - 1
    sharpe = (rets.mean() * 12) / (rets.std(ddof=1) * np.sqrt(12))
    peak   = np.maximum.accumulate(values)
    max_dd = ((values - peak) / peak).min()

    # Annual returns
    by_year: dict[int, list] = {}
    ret_dates = dates[1:]
    for i, r in enumerate(rets):
        if i < len(ret_dates):
            by_year.setdefault(ret_dates[i].year, []).append(r)

    print(f"\n{'═'*46}")
    print(f"  BROAD PPM — top {top_n} from all funds")
    print(f"{'═'*46}")
    print(f"  Period : {dates[0].date()} → {dates[-1].date()}  ({n_yrs:.1f} yr)")
    print(f"  CAGR   : {cagr*100:.1f}%")
    print(f"  Sharpe : {sharpe:.2f}")
    print(f"  Max DD : {max_dd*100:.1f}%")
    print(f"  Total  : {(values[-1]/values[0]-1)*100:.0f}%")
    print()
    print(f"  {'Year':<6} {'Return':>8}  {'Sharpe':>7}")
    for yr in sorted(by_year):
        yr_rets = np.array(by_year[yr])
        yr_ret  = np.prod(1 + yr_rets) - 1
        yr_sh   = (yr_rets.mean()*12) / (yr_rets.std(ddof=1)*np.sqrt(12)) if len(yr_rets)>1 else 0
        print(f"  {yr:<6} {yr_ret*100:>+7.1f}%  {yr_sh:>7.2f}")
    print(f"{'═'*46}\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db",  default=None)
    parser.add_argument("--top", type=int, default=TOP_N)
    args = parser.parse_args()

    top_n = args.top

    if args.db:
        db_path = Path(args.db)
    else:
        repo  = Path(__file__).parent.parent
        data  = Path(os.getenv("DATA_DIR", str(repo)))
        db_path = data / "dashboard.db"

    if not db_path.exists():
        log.error("DB not found: %s", db_path); sys.exit(1)

    wide   = load_all_funds(db_path)
    scores = compute_signals(wide)

    log.info("Running backtest…")
    nav_series, monthly_rets, cash_count = run_backtest(wide, scores, top_n)
    log.info("Cash months: %d / %d", cash_count, len(monthly_rets))

    stats(nav_series, monthly_rets, top_n)

    # Show what funds are selected right now
    dt = wide.index[-1]
    elig = [
        c for c in wide.columns
        if c != CASH_PPM
        and wide[c].first_valid_index() is not None
        and (dt - wide[c].first_valid_index()).days >= MIN_DAYS
        and not np.isnan(scores.loc[dt, c])
    ]
    top = scores.loc[dt, elig].nlargest(top_n)
    print("Current top picks (broad universe):")
    for ppm_id, score in top.items():
        print(f"  {ppm_id}  score={score:.4f}")


if __name__ == "__main__":
    main()
