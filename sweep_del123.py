#!/usr/bin/env python3
"""
DEL 1/2/3 Parameter Sweep
- DEL 1: Asymmetric regime with hysteresis + Fast Recovery Trigger
- DEL 2: New ranking metrics: raw, sharpe, frog_in_the_pan, composite
- DEL 3: Full sweep 5 sel_lb × 4 metrics × 2 regime configs = 40 combos
          n_factor=1, n_sector=1 throughout
          15 bps per side enforced in all variants
Output: Top-5 by Sharpe + full table
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent / "dashboard" / "backend"))
import engine as eng

# ── Constants ───────────────────────────────────────────────────────
COST            = 0.0015
CAPITAL         = 100_000.0
START           = "2019-10-01"
SYNTHETIC_CASH  = "CASH"

SEL_LOOKBACKS   = [21, 42, 63, 84, 126]
METRICS         = ["raw", "sharpe", "frog_in_the_pan", "composite"]

# Regime parameters — DEL 1
REG_EXIT_LB       = 84    # MA length used when checking EXIT signal
REG_ENTRY_LB      = 21    # MA length used when checking ENTRY signal (asymmetric)
REG_SYM_LB        = 84    # lookback for symmetric IWDA-vs-IBTS comparison
HYST_EXIT         = 0.010  # exit if price < MA_84 * (1 - 0.010)
HYST_ENTRY        = 0.003  # enter if price > MA_21 * (1 + 0.003)
FAST_RECOVERY_PCT = 0.10   # >= 10% from 15d low => force RISK-ON
FAST_RECOVERY_LB  = 15     # days for the low scan


# ── Price utilities ─────────────────────────────────────────────────
def p_at(ticker, d, prices):
    if ticker == SYNTHETIC_CASH:
        return 1.0
    if ticker in prices.columns and d in prices.index:
        v = prices.loc[d, ticker]
        return float(v) if not np.isnan(v) else 0.0
    return 0.0


# ── Scoring metrics (DEL 2) ─────────────────────────────────────────
def score_asset(ticker, d, prices, pos_map, metric, lookback):
    if ticker == SYNTHETIC_CASH:
        return 0.0

    pos = pos_map.get(d, -1)
    if pos < 0 or ticker not in prices.columns:
        return np.nan

    if metric == "composite":
        # 50/50 of 21d and 84d raw returns — sel_lb ignored
        w21, w84 = 21, 84
        if pos < w84:
            return np.nan
        p_now  = float(prices.iloc[pos][ticker])
        p_21   = float(prices.iloc[pos - w21][ticker])
        p_84   = float(prices.iloc[pos - w84][ticker])
        if p_21 <= 0 or p_84 <= 0:
            return np.nan
        return 0.5 * (p_now / p_21 - 1) + 0.5 * (p_now / p_84 - 1)

    if pos < lookback:
        return np.nan
    window = prices.iloc[pos - lookback : pos + 1][ticker].values.astype(float)
    if len(window) < 2 or window[0] <= 0 or np.any(np.isnan(window)):
        return np.nan

    if metric == "raw":
        return window[-1] / window[0] - 1

    elif metric == "sharpe":
        rets = np.diff(window) / window[:-1]
        mu   = np.mean(rets) * 252
        sig  = np.std(rets, ddof=1) * np.sqrt(252)
        return mu / sig if sig > 0 else np.nan

    elif metric == "frog_in_the_pan":
        rets  = np.diff(window) / window[:-1]
        n_pos = np.sum(rets > 0)
        n_neg = np.sum(rets < 0)
        n_tot = len(rets)
        return float(n_pos - n_neg) / n_tot if n_tot > 0 else np.nan

    return np.nan


def top_n_assets(tickers, d, prices, pos_map, metric, lookback, n):
    scores = {t: score_asset(t, d, prices, pos_map, metric, lookback) for t in tickers}
    valid  = {t: v for t, v in scores.items() if not np.isnan(v)}
    return sorted(valid, key=valid.__getitem__, reverse=True)[:n]


# ── Regime checks (DEL 1) ───────────────────────────────────────────
def regime_symmetric(d, prices, pos_map, iwda, ibts, reg_lb=REG_SYM_LB):
    """Returns True (→ go cash) if IWDA N-day return ≤ IBTS N-day return."""
    pos = pos_map.get(d, -1)
    if pos < reg_lb or iwda not in prices.columns or ibts not in prices.columns:
        return False
    try:
        p0_mkt = float(prices.iloc[pos - reg_lb][iwda])
        p1_mkt = float(prices.iloc[pos][iwda])
        p0_cmp = float(prices.iloc[pos - reg_lb][ibts])
        p1_cmp = float(prices.iloc[pos][ibts])
    except Exception:
        return False
    if any(v <= 0 for v in [p0_mkt, p1_mkt, p0_cmp, p1_cmp]):
        return False
    return (p1_mkt / p0_mkt - 1) <= (p1_cmp / p0_cmp - 1)


def regime_asymmetric(d, prices, pos_map, iwda, currently_in_cash):
    """
    Asymmetric hysteresis regime (DEL 1):
    - Fast Recovery Trigger checked first: IWDA >= 10% above 15d low → force RISK-ON
    - If in market: exit when price < MA_84 × (1 - HYST_EXIT)
    - If in cash:   enter when price > MA_21 × (1 + HYST_ENTRY)
    Returns True if we should be in CASH.
    """
    pos = pos_map.get(d, -1)
    if iwda not in prices.columns:
        return currently_in_cash
    try:
        p_now = float(prices.iloc[pos][iwda])
    except Exception:
        return currently_in_cash
    if np.isnan(p_now) or p_now <= 0:
        return currently_in_cash

    # 1. Fast Recovery Trigger
    if pos >= FAST_RECOVERY_LB:
        lo15 = float(prices.iloc[pos - FAST_RECOVERY_LB : pos + 1][iwda].min())
        if lo15 > 0 and (p_now / lo15 - 1) >= FAST_RECOVERY_PCT:
            return False   # force RISK-ON

    # 2. State-dependent MA check
    if currently_in_cash:
        if pos < REG_ENTRY_LB:
            return True
        ma = float(prices.iloc[pos - REG_ENTRY_LB : pos + 1][iwda].mean())
        return not (p_now > ma * (1 + HYST_ENTRY))   # stay cash unless above threshold
    else:
        if pos < REG_EXIT_LB:
            return False
        ma = float(prices.iloc[pos - REG_EXIT_LB : pos + 1][iwda].mean())
        return p_now < ma * (1 - HYST_EXIT)           # exit if below threshold


# ── Backtest engine ─────────────────────────────────────────────────
def run_backtest(prices, factor_tickers, sector_tickers,
                 regime_ticker, ibts_ticker, cash_ticker,
                 sel_lb, metric, regime_mode,
                 n_factor=1, n_sector=1):
    """
    Returns (equity_curve, avg_annual_turnover).
    equity_curve: [{"date": str, "value": float}, ...]
    """
    f_ticks = [t for _, t in factor_tickers]
    s_ticks = [t for _, t in sector_tickers]

    all_idx   = prices.index
    rebal_set = eng.month_end_dates(all_idx)
    pos_map   = {d: i for i, d in enumerate(all_idx)}

    sim_dates = all_idx[all_idx >= pd.Timestamp(START)]
    warmup_lb = max(REG_EXIT_LB, sel_lb if metric != "composite" else 84)
    min_date  = all_idx[warmup_lb] if len(all_idx) > warmup_lb else all_idx[-1]

    cash_bal        = float(CAPITAL)
    shares          = {}
    current_weights = {}
    equity          = []
    pending         = None
    in_cash         = True   # initial state for asymmetric regime
    total_turnover  = 0.0
    n_rebalances    = 0

    for d in sim_dates:
        # Execute pending rebalance
        if pending is not None:
            all_t = set(shares) | set(pending)
            px    = {t: p_at(t, d, prices) for t in all_t}
            value = cash_bal + sum(shares.get(t, 0.0) * px.get(t, 0.0) for t in shares)

            new_sh = {}
            for t, w in pending.items():
                p = px.get(t, 0.0)
                if p > 0:
                    new_sh[t] = (value * w) / p

            # Turnover: sum |Δweight|
            all_tw = set(current_weights) | set(pending)
            turnover = sum(abs(pending.get(t, 0.0) - current_weights.get(t, 0.0))
                           for t in all_tw)
            total_turnover += turnover
            n_rebalances   += 1

            real_t = {t for t in all_t if t != SYNTHETIC_CASH}
            cost = sum(
                abs(new_sh.get(t, 0.0) * px.get(t, 0.0)
                    - shares.get(t, 0.0) * px.get(t, 0.0)) * COST
                for t in real_t
            )
            cash_bal        = value - sum(new_sh[t] * px[t] for t in new_sh) - cost
            shares          = new_sh
            current_weights = dict(pending)
            pending         = None

        # Mark to market
        held = sum(sh * p_at(t, d, prices) for t, sh in shares.items())
        equity.append({"date": d.strftime("%Y-%m-%d"), "value": round(cash_bal + held, 2)})

        if d not in rebal_set or d < min_date:
            continue

        # Regime gate
        if regime_mode == "symmetric":
            go_cash = regime_symmetric(d, prices, pos_map, regime_ticker, ibts_ticker)
        else:
            go_cash = regime_asymmetric(d, prices, pos_map, regime_ticker, in_cash)
        in_cash = go_cash

        if go_cash:
            pending = {cash_ticker: 1.0}
            continue

        # Selection
        f_picks = top_n_assets(f_ticks, d, prices, pos_map, metric, sel_lb, n_factor)
        s_picks = top_n_assets(s_ticks, d, prices, pos_map, metric, sel_lb, n_sector)

        if not f_picks and not s_picks:
            continue

        w = {}
        for t in f_picks:
            w[t] = w.get(t, 0.0) + 0.5 / max(len(f_picks), 1)
        for t in s_picks:
            w[t] = w.get(t, 0.0) + 0.5 / max(len(s_picks), 1)

        pending = w

    # Annualised turnover
    dates  = pd.to_datetime([e["date"] for e in equity])
    n_yrs  = (dates[-1] - dates[0]).days / 365.25 if len(dates) > 1 else 1.0
    avg_to = total_turnover / n_yrs if n_yrs > 0 else 0.0

    return equity, avg_to


# ── Stats helper ────────────────────────────────────────────────────
def compute_stats(equity_curve):
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

    df = pd.DataFrame({"v": values}, index=dates)
    mo_vals = df.resample("ME").last()["v"].values
    mo_peak = np.maximum.accumulate(mo_vals)
    max_dd_mo = float(((mo_vals - mo_peak) / mo_peak).min()) if len(mo_vals) > 1 else max_dd

    return {
        "cagr":     round(float(cagr), 4),
        "sharpe":   round(float(sharpe), 4),
        "max_dd":   round(float(max_dd), 4),
        "max_dd_mo": round(float(max_dd_mo), 4),
        "ann_vol":  round(float(ann_vol), 4),
        "total":    round(float(values[-1] / values[0] - 1), 4),
    }


# ── Main sweep ──────────────────────────────────────────────────────
def main():
    cfg = eng.load_config()
    factor_t, sector_t, regime_t, ibts_t, cash_t, ter_map = eng.parse_config(cfg)

    # Download prices (reuse cache if available)
    strategy_tickers = (
        [t for _, t in factor_t]
        + [t for _, t in sector_t]
        + [regime_t, ibts_t]
        + ([cash_t] if cash_t != SYNTHETIC_CASH else [])
    )
    prices_raw = eng.fetch_prices(list(dict.fromkeys(strategy_tickers)), use_cache=True)

    strategy_cols = [t for t in strategy_tickers if t in prices_raw.columns]
    prices_adj    = prices_raw.copy()
    prices_adj[strategy_cols] = eng.apply_ter(prices_raw[strategy_cols], ter_map)

    # Baseline: production 84/84 raw (for comparison)
    print("Running baseline (raw sel84 / symmetric 84/84)…")
    eq_base, to_base = run_backtest(
        prices_adj, factor_t, sector_t, regime_t, ibts_t, cash_t,
        sel_lb=84, metric="raw", regime_mode="symmetric",
    )
    st_base = compute_stats(eq_base)
    print(f"  Baseline → CAGR {st_base['cagr']:.1%}  Sharpe {st_base['sharpe']:.2f}"
          f"  MaxDD_mo {st_base['max_dd_mo']:.1%}  Turnover {to_base:.1f}x/yr")

    results = []

    total_runs = len(SEL_LOOKBACKS) * len(METRICS) * 2
    run_n = 0

    for regime_mode in ["symmetric", "asymmetric"]:
        for metric in METRICS:
            for sel_lb in SEL_LOOKBACKS:
                run_n += 1
                label = f"{regime_mode[:3].upper()} | {metric:<15} | lb={sel_lb:3d}"
                print(f"[{run_n:2d}/{total_runs}] {label} … ", end="", flush=True)

                eq, to = run_backtest(
                    prices_adj, factor_t, sector_t, regime_t, ibts_t, cash_t,
                    sel_lb=sel_lb, metric=metric, regime_mode=regime_mode,
                )
                st = compute_stats(eq)
                row = {
                    "regime":   regime_mode,
                    "metric":   metric,
                    "sel_lb":   sel_lb,
                    "cagr":     st.get("cagr", 0),
                    "sharpe":   st.get("sharpe", 0),
                    "max_dd":   st.get("max_dd", 0),
                    "max_dd_mo": st.get("max_dd_mo", 0),
                    "ann_vol":  st.get("ann_vol", 0),
                    "total":    st.get("total", 0),
                    "turnover": round(to, 2),
                }
                results.append(row)
                print(f"CAGR {row['cagr']:.1%}  Sharpe {row['sharpe']:.2f}"
                      f"  MaxDD_mo {row['max_dd_mo']:.1%}  TO {row['turnover']:.1f}x")

    # ── Print results ────────────────────────────────────────────────
    df = pd.DataFrame(results).sort_values("sharpe", ascending=False).reset_index(drop=True)

    print("\n" + "=" * 90)
    print("FULL RESULTS (sorted by Sharpe)")
    print("=" * 90)
    hdr = f"{'#':>3}  {'Regime':<12} {'Metric':<17} {'LB':>4}  "
    hdr += f"{'CAGR':>7}  {'Sharpe':>7}  {'MaxDD_mo':>9}  {'MaxDD_d':>8}  {'Vol':>6}  {'TO':>6}"
    print(hdr)
    print("-" * 90)
    for i, r in df.iterrows():
        print(f"{i+1:>3}  {r['regime']:<12} {r['metric']:<17} {r['sel_lb']:>4}  "
              f"{r['cagr']:>7.1%}  {r['sharpe']:>7.2f}  {r['max_dd_mo']:>9.1%}  "
              f"{r['max_dd']:>8.1%}  {r['ann_vol']:>6.1%}  {r['turnover']:>6.1f}x")

    print("\n" + "=" * 90)
    print("TOP-5 BY SHARPE")
    print("=" * 90)
    print(f"{'Rank':<5} {'Regime':<12} {'Metric':<17} {'LB':>4}  "
          f"{'CAGR':>7}  {'Sharpe':>7}  {'MaxDD_mo':>9}  {'TO/yr':>6}")
    print("-" * 70)
    for rank, r in df.head(5).iterrows():
        print(f"{rank+1:<5} {r['regime']:<12} {r['metric']:<17} {r['sel_lb']:>4}  "
              f"{r['cagr']:>7.1%}  {r['sharpe']:>7.2f}  {r['max_dd_mo']:>9.1%}  "
              f"{r['turnover']:>6.1f}x")

    print(f"\nBaseline (raw/sel84/sym84):  CAGR {st_base['cagr']:.1%}  "
          f"Sharpe {st_base['sharpe']:.2f}  MaxDD_mo {st_base['max_dd_mo']:.1%}  "
          f"TO {to_base:.1f}x")

    # Save markdown report
    out_path = Path(__file__).parent / "SWEEP_DEL123.md"
    with open(out_path, "w") as f:
        f.write("# DEL1/2/3 Sweep Results\n\n")
        f.write(f"**Baseline** (raw / sel=84 / symmetric 84/84):  "
                f"CAGR {st_base['cagr']:.1%}  Sharpe {st_base['sharpe']:.2f}  "
                f"MaxDD_mo {st_base['max_dd_mo']:.1%}  Turnover {to_base:.1f}×/yr\n\n")
        f.write("## Top-5 by Sharpe\n\n")
        f.write("| # | Regime | Metric | LB | CAGR | Sharpe | MaxDD_mo | TO/yr |\n")
        f.write("|---|--------|--------|----|------|--------|----------|-------|\n")
        for rank, r in df.head(5).iterrows():
            f.write(f"| {rank+1} | {r['regime']} | {r['metric']} | {r['sel_lb']} "
                    f"| {r['cagr']:.1%} | {r['sharpe']:.2f} | {r['max_dd_mo']:.1%} "
                    f"| {r['turnover']:.1f}× |\n")
        f.write("\n## Full Results (sorted by Sharpe)\n\n")
        f.write("| # | Regime | Metric | LB | CAGR | Sharpe | MaxDD_mo | MaxDD_d | Vol | TO/yr |\n")
        f.write("|---|--------|--------|----|------|--------|----------|---------|-----|-------|\n")
        for i, r in df.iterrows():
            f.write(f"| {i+1} | {r['regime']} | {r['metric']} | {r['sel_lb']} "
                    f"| {r['cagr']:.1%} | {r['sharpe']:.2f} | {r['max_dd_mo']:.1%} "
                    f"| {r['max_dd']:.1%} | {r['ann_vol']:.1%} | {r['turnover']:.1f}× |\n")
    print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    main()
