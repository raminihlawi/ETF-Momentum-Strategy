"""
"Secret sauce" parameter sweep for Strategy D (Marketfighter replica).

Per the INSTRUCTION SPEC: Strategy C Upgrade & Strategy D 'Secret Sauce'
Parameter Sweep (Task 3).

Sweeps:
  - LOOKBACK            : 126, 189, 252 (6m, 9m, 12m)
  - MOMENTUM_METRIC     : raw, composite, skip_1m_12m, r2_adjusted,
                          frog_in_the_pan, sma_200_distance
  - USE_GLOBAL_REGIME_FILTER : True / False
      (= marketfighter_replica.regime_ok: IWDA.L vs IBTS.L absolute-momentum
      gate on the whole portfolio -- the Strategy D analogue of Strategy C's
      new use_global_regime_gate.)

That's 3 x 6 x 2 = 36 combos.

Metric definitions (see marketfighter_replica.add_secret_sauce_indicators
for the indicator columns):
  - raw             : trailing return over `lookback_days` (ret_lb)
  - composite       : avg percentile rank of fixed 3/6/12m returns
  - skip_1m_12m     : "12-1" momentum, ret_lb excluding the most recent
                      ~21 trading days (ret_skip1)
  - r2_adjusted     : ret_lb x R^2 of a linear fit of Close over the
                      lookback window (r2_lb) -- penalizes jagged paths
  - frog_in_the_pan : sign(ret_lb) x (n_up - n_down) / n_total over the
                      lookback window (frog_lb) -- rewards steady grinds
  - sma_200_distance: (Close - SMA200) / SMA200 (sma200_dist)

Outputs:
  - marketfighter_sweep2_results/sweep2_results.csv
  - Top-5 configs by Sharpe printed to stdout
  - Flags any combo with CAGR within ~2pp of the article's 16% claim AND
    MaxDD shallower than -20%

Run: python marketfighter_sweep2.py
"""

import itertools
import os

import numpy as np
import pandas as pd

import backtest_engine as engine
import etf_momentum_backtest as eb
import marketfighter_replica as mf

OUT_DIR = "marketfighter_sweep2_results"

LOOKBACK_VALUES = [126, 189, 252]
MOMENTUM_METRICS = ["raw", "composite", "skip_1m_12m", "r2_adjusted",
                    "frog_in_the_pan", "sma_200_distance"]
REGIME_FILTER_VALUES = [True, False]

NEW_COLS = ["ret_skip1", "r2_lb", "frog_lb", "sma200_dist"]


# ============================ SCORING ============================
def compute_score(snapshot, tickers, metric, cfg):
    """Return a Series of scores (higher = better), indexed by ticker,
    for the candidates in `tickers` that are present in `snapshot`."""
    cands = [t for t in tickers if t in snapshot.index]
    if not cands:
        return pd.Series(dtype=float)

    if metric == "raw":
        return snapshot.loc[cands, "ret_lb"].dropna()

    if metric == "composite":
        cols = list(cfg["composite_horizons"].keys())
        sub = snapshot.loc[cands, cols].dropna()
        if sub.empty:
            return pd.Series(dtype=float)
        sub = sub.copy()
        for c in cols:
            sub[c + "_pct"] = sub[c].rank(pct=True)
        return sub[[c + "_pct" for c in cols]].mean(axis=1)

    if metric == "skip_1m_12m":
        return snapshot.loc[cands, "ret_skip1"].dropna()

    if metric == "r2_adjusted":
        s = snapshot.loc[cands, "ret_lb"] * snapshot.loc[cands, "r2_lb"]
        return s.dropna()

    if metric == "frog_in_the_pan":
        return snapshot.loc[cands, "frog_lb"].dropna()

    if metric == "sma_200_distance":
        return snapshot.loc[cands, "sma200_dist"].dropna()

    raise ValueError(f"unknown metric {metric}")


def best_of(snapshot, tickers, metric, cfg):
    s = compute_score(snapshot, tickers, metric, cfg)
    return None if s.empty else s.idxmax()


# ============================ BACKTEST ============================
def run_backtest(data, all_dates, rebal_dates, cfg, metric, use_regime_filter):
    cash_bal = cfg["starting_capital"]
    shares = {}
    equity_curve = []
    rebal_log = []
    pending = None
    rebal_set = set(rebal_dates)
    cash_days, total_days = 0, 0
    turnover_total = 0.0

    for d in all_dates:
        if pending is not None:
            value = cash_bal
            open_px = {}
            for t in set(list(shares.keys()) + list(pending.keys())):
                df = data[t]
                if d in df.index:
                    open_px[t] = df.loc[d, "Open"]
                else:
                    open_px[t] = df["Close"].reindex(all_dates).ffill().loc[d]
            for t in shares:
                value += shares[t] * open_px.get(t, 0.0)

            new_shares = {}
            for t, w in pending.items():
                px = open_px.get(t)
                if px is None or np.isnan(px) or px <= 0:
                    continue
                new_shares[t] = (value * w) / px

            cost = 0.0
            turnover_value = 0.0
            for t in set(list(shares.keys()) + list(new_shares.keys())):
                old_val = shares.get(t, 0.0) * open_px.get(t, 0.0)
                new_val = new_shares.get(t, 0.0) * open_px.get(t, 0.0)
                delta = abs(new_val - old_val)
                turnover_value += delta
                rate = cfg["cost_per_side_overrides"].get(t, cfg["cost_per_side"])
                cost += delta * rate

            if value > 0:
                turnover_total += turnover_value / value

            invested = sum(new_shares[t] * open_px[t] for t in new_shares)
            cash_bal = value - invested - cost
            shares = new_shares
            rebal_log.append((d, len(shares), cost))
            pending = None

        held = 0.0
        for t, sh in shares.items():
            df = data[t]
            if d in df.index:
                px = df.loc[d, "Close"]
            else:
                px = df["Close"].reindex(all_dates).ffill().loc[d]
            held += sh * px
        equity_curve.append((d, cash_bal + held))

        total_days += 1
        nav_today = cash_bal + held
        if nav_today > 0 and (cash_bal / nav_today) > 0.5:
            cash_days += 1

        if d in rebal_set:
            rows = {}
            for t, df in data.items():
                if d not in df.index:
                    continue
                row = df.loc[d]
                entry = {"ret_lb": row["ret_lb"], "vol": row["vol"]}
                for c in cfg["composite_horizons"]:
                    entry[c] = row.get(c, np.nan)
                for c in NEW_COLS:
                    entry[c] = row.get(c, np.nan)
                rows[t] = entry
            if not rows:
                pending = {}
                continue
            snapshot = pd.DataFrame(rows).T

            if use_regime_filter and not mf.regime_ok(snapshot, cfg):
                pending = {}
                continue

            best_factor = best_of(snapshot, mf.FACTOR_TICKERS, metric, cfg)
            best_sector = best_of(snapshot, mf.SECTOR_TICKERS, metric, cfg)

            weights = {}
            if best_factor is not None:
                weights[best_factor] = weights.get(best_factor, 0.0) + 0.5
            if best_sector is not None:
                weights[best_sector] = weights.get(best_sector, 0.0) + 0.5
            pending = weights

    eq = pd.Series({d: v for d, v in equity_curve}).sort_index()
    cash_frac = cash_days / total_days if total_days else 0.0
    n_rebal = len(rebal_dates)
    turnover_pct = (turnover_total / n_rebal * 100) if n_rebal else 0.0
    return eq, pd.DataFrame(rebal_log, columns=["date", "n_holdings", "cost"]), cash_frac, turnover_pct


# ============================ MAIN ============================
def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    base_cfg = dict(mf.CONFIG)
    universe_df = pd.read_csv(base_cfg["universe_csv"])
    all_tickers = list(universe_df["ticker"])

    print("Loading price data...")
    raw_data = eb.load_data(all_tickers, start="2005-01-01", end=base_cfg["end"], cfg=base_cfg)
    ter_data = eb.build_ter_adjusted_data(raw_data, base_cfg)
    print(f"  {len(raw_data)} tickers loaded.")

    bh = engine.buy_and_hold(
        raw_data[eb.BASELINE_TICKER].loc[raw_data[eb.BASELINE_TICKER].index >= pd.Timestamp(base_cfg["start"])],
        base_cfg["starting_capital"])
    bh_stats = engine.perf_stats(bh, label=None, print_report=False)

    # ---- build indicator caches per lookback ----
    indicator_cache = {}
    for lookback in LOOKBACK_VALUES:
        cfg_lb = dict(base_cfg, lookback_days=lookback, composite=True)
        data = {}
        for t, df in ter_data.items():
            d = eb.add_indicators(df.copy(), cfg_lb)
            d = mf.add_secret_sauce_indicators(d, cfg_lb)
            data[t] = d.loc[d.index >= pd.Timestamp(base_cfg["start"])]
        indicator_cache[lookback] = data

    all_dates = indicator_cache[252][eb.BASELINE_TICKER].index
    rebal_dates_all = eb.month_end_dates(all_dates)
    # warmup: max(lookback, 200) for SMA200 + lookback-based cols
    warmup = max(LOOKBACK_VALUES + [200])
    min_start = all_dates[warmup]
    rebal_dates_all = rebal_dates_all[rebal_dates_all >= min_start]

    print(f"\nBacktest window: {all_dates[0].date()} -> {all_dates[-1].date()}, "
          f"{len(rebal_dates_all)} rebalances")
    print(f"Buy & hold IWDA reference: CAGR {bh_stats['cagr']*100:.1f}%  Sharpe {bh_stats['sharpe']:.2f}  "
          f"MaxDD {bh_stats['max_dd']*100:.1f}%")

    total = len(LOOKBACK_VALUES) * len(MOMENTUM_METRICS) * len(REGIME_FILTER_VALUES)
    run_i = 0
    results = []
    for lookback in LOOKBACK_VALUES:
        cfg_lb = dict(base_cfg, lookback_days=lookback, composite=True)
        data = indicator_cache[lookback]
        min_start_lb = all_dates[warmup]
        rebal_dates = rebal_dates_all  # same warmup for all combos

        for metric, use_regime in itertools.product(MOMENTUM_METRICS, REGIME_FILTER_VALUES):
            run_i += 1
            eq, log, cash_frac, turnover_pct = run_backtest(
                data, all_dates, rebal_dates, cfg_lb, metric=metric, use_regime_filter=use_regime)
            stats = engine.perf_stats(eq, label=None, print_report=False)
            results.append({
                "lookback_days": lookback, "momentum_metric": metric,
                "use_global_regime_filter": use_regime,
                "cagr": stats["cagr"], "sharpe": stats["sharpe"],
                "max_dd": stats["max_dd"], "ann_vol": stats["ann_vol"],
                "cash_frac": cash_frac, "turnover_pct": turnover_pct,
                "n_rebal": len(log), "total_cost": log["cost"].sum(),
            })
            print(f"  [{run_i:2d}/{total}] lookback={lookback:3d} metric={metric:17s} "
                  f"global_regime={use_regime!s:5s} -> CAGR {stats['cagr']*100:6.2f}%  "
                  f"Sharpe {stats['sharpe']:5.2f}  maxDD {stats['max_dd']*100:6.1f}%  "
                  f"turnover {turnover_pct:5.1f}%/rebal")

    df = pd.DataFrame(results)
    csv_path = os.path.join(OUT_DIR, "sweep2_results.csv")
    df.to_csv(csv_path, index=False)
    print(f"\nWrote {csv_path}")

    # ---- top 5 by Sharpe ----
    print("\n=== TOP 5 CONFIGS BY SHARPE ===")
    top5 = df.sort_values("sharpe", ascending=False).head(5)
    for _, r in top5.iterrows():
        print(f"  lookback={int(r['lookback_days']):3d}  metric={r['momentum_metric']:17s} "
              f"global_regime={str(r['use_global_regime_filter']):5s}  "
              f"Sharpe {r['sharpe']:.2f}  CAGR {r['cagr']*100:5.2f}%  "
              f"MaxDD {r['max_dd']*100:6.2f}%  turnover {r['turnover_pct']:.1f}%/rebal")

    # ---- "16% CAGR + MaxDD shallower than -20%" check ----
    print("\n=== Combos with CAGR within 2pp of the article's 16% claim "
          "AND MaxDD shallower than -20% ===")
    target = df[(df["cagr"] >= 0.14) & (df["max_dd"] > -0.20)]
    if target.empty:
        print("  None. Best CAGR overall:"
              f" {df['cagr'].max()*100:.2f}% (vs B&H IWDA {bh_stats['cagr']*100:.2f}%);"
              f" best (CAGR, shallow-MaxDD) combo:")
        # report the best CAGR among shallow-MaxDD combos, and best MaxDD among
        # high-CAGR combos, for context
        shallow = df[df["max_dd"] > -0.20]
        if not shallow.empty:
            r = shallow.loc[shallow["cagr"].idxmax()]
            print(f"    Among MaxDD > -20% combos, best CAGR: lookback={int(r['lookback_days'])}"
                  f" metric={r['momentum_metric']} global_regime={r['use_global_regime_filter']}"
                  f" -> CAGR {r['cagr']*100:.2f}% Sharpe {r['sharpe']:.2f} MaxDD {r['max_dd']*100:.2f}%")
    else:
        for _, r in target.iterrows():
            print(f"    lookback={int(r['lookback_days'])} metric={r['momentum_metric']}"
                  f" global_regime={r['use_global_regime_filter']}"
                  f" -> CAGR {r['cagr']*100:.2f}% Sharpe {r['sharpe']:.2f} MaxDD {r['max_dd']*100:.2f}%")

    print("\n=== SWEEP2 SUMMARY ===")
    print(f"  Sharpe: median {df['sharpe'].median():.2f}, best {df['sharpe'].max():.2f}, "
          f"worst {df['sharpe'].min():.2f}")
    for dim in ["lookback_days", "momentum_metric", "use_global_regime_filter"]:
        spread = df.groupby(dim)["sharpe"].mean().max() - df.groupby(dim)["sharpe"].mean().min()
        print(f"  Effect of {dim:28s}: group-mean Sharpe spread = {spread:.3f}")


if __name__ == "__main__":
    main()
