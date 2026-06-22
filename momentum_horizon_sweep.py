"""
Compare shorter composite-momentum lookback combinations against the
STRATEGY_SPEC.md default (3/6/12 months).

The spec's default combines 3/6/12-month returns. This sweep tests whether
shorter horizons -- more responsive, but noisier and costlier (more
turnover) -- do better on the Stockholm universe, 2009-2026.

Horizon sets tested (in trading days, ~21/month):
  - "12/6/3"  : {3m, 6m, 12m}   <- spec default
  - "6/3/1"   : {1m, 3m, 6m}
  - "3/1"     : {1m, 3m}
  - "3/2/1"   : {1m, 2m, 3m}
  - "1"       : {1m} only

Each is run for both Strategy A (full) and the naive baseline, at the
default thresholds otherwise (skip_recent_days=0).

Outputs:
  - sweep_results/horizon_sweep_results.csv
  - sweep_results/horizon_comparison.png -- bar charts of CAGR, Sharpe,
    max DD, and total rebalancing cost across horizon sets

Run: python momentum_horizon_sweep.py
"""

import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

import price_db
import backtest_engine as engine
import momentum_backtest as mb

OUT_DIR = "sweep_results"

HORIZON_SETS = {
    "12/6/3":  {"ret_12m": 252, "ret_6m": 126, "ret_3m": 63},
    "6/3/1":   {"ret_6m": 126, "ret_3m": 63, "ret_1m": 21},
    "3/1":     {"ret_3m": 63, "ret_1m": 21},
    "3/2/1":   {"ret_3m": 63, "ret_2m": 42, "ret_1m": 21},
    "1":       {"ret_1m": 21},
}


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    base_cfg = mb.CONFIG

    print("Loading benchmark & universe...")
    bench = price_db.load_prices(base_cfg["benchmark"], start=base_cfg["start"],
                                   end=base_cfg["end"]).dropna()
    universe = price_db.load_universe(base_cfg["segments"])
    tickers = [t for t, _, seg in universe if seg != "Index"]
    raw_data = mb.load_data(tickers, base_cfg["start"], base_cfg["end"])
    print(f"  {len(raw_data)} tickers loaded.")

    regime_on = bench["Close"] > bench["Close"].rolling(base_cfg["regime_sma"]).mean()

    bh = engine.buy_and_hold(bench, base_cfg["starting_capital"])
    bh_stats = engine.perf_stats(bh, label=None, print_report=False)

    results = []
    for name, horizons in HORIZON_SETS.items():
        cfg_h = dict(base_cfg, horizons=horizons)
        data = {t: mb.add_indicators(df.copy(), cfg_h) for t, df in raw_data.items()}

        rebal_dates = mb.month_end_dates(bench.index)
        min_start = bench.index[max(horizons.values()) + cfg_h["skip_recent_days"]]
        rebal_dates = rebal_dates[rebal_dates >= min_start]

        for variant, cfg in [("Strategy A (full)", cfg_h),
                              ("Naive baseline", dict(cfg_h, use_regime_gate=False,
                                                        use_quality_filter=False,
                                                        use_banding=False, weighting="equal"))]:
            eq, log = mb.run_backtest(data, bench, regime_on, rebal_dates, cfg)
            stats = engine.perf_stats(eq, label=None, print_report=False)
            results.append({
                "horizon_set": name, "variant": variant,
                "cagr": stats["cagr"], "sharpe": stats["sharpe"], "max_dd": stats["max_dd"],
                "n_rebal": len(log), "total_cost": log["cost"].sum(),
            })
            print(f"  {name:8s} | {variant:18s} -> CAGR {stats['cagr']*100:5.1f}%  "
                  f"Sharpe {stats['sharpe']:5.2f}  maxDD {stats['max_dd']*100:6.1f}%  "
                  f"cost {log['cost'].sum():9,.0f}")

    df = pd.DataFrame(results)
    df.to_csv(os.path.join(OUT_DIR, "horizon_sweep_results.csv"), index=False)
    plot_comparison(df, bh_stats)

    print(f"\nWrote {os.path.join(OUT_DIR, 'horizon_sweep_results.csv')}")
    print(f"Wrote {os.path.join(OUT_DIR, 'horizon_comparison.png')}")
    print(f"\n  Buy & hold reference: CAGR {bh_stats['cagr']*100:.1f}%  Sharpe {bh_stats['sharpe']:.2f}  "
          f"maxDD {bh_stats['max_dd']*100:.1f}%")


def plot_comparison(df, bh_stats):
    horizon_order = list(HORIZON_SETS.keys())
    variants = df["variant"].unique()

    fig, axes = plt.subplots(1, 4, figsize=(18, 4.5))
    metrics = [("cagr", "CAGR (%)", 100), ("sharpe", "Sharpe", 1),
               ("max_dd", "Max drawdown (%)", 100), ("total_cost", "Total rebal. cost", 1)]

    x = range(len(horizon_order))
    width = 0.35
    for ax, (col, title, mult) in zip(axes, metrics):
        for i, variant in enumerate(variants):
            sub = df[df["variant"] == variant].set_index("horizon_set").reindex(horizon_order)
            offset = (i - 0.5) * width
            ax.bar([xi + offset for xi in x], sub[col] * mult, width, label=variant)
        if col in ("cagr", "sharpe", "max_dd"):
            ref = bh_stats[col] * mult
            ax.axhline(ref, color="black", linestyle="--", linewidth=1, label="Buy & hold")
        ax.set_xticks(list(x))
        ax.set_xticklabels(horizon_order)
        ax.set_title(title)
        ax.set_xlabel("horizon set")
        ax.legend(fontsize=8)

    fig.suptitle("Composite momentum: shorter vs spec-default (3/6/12m) horizons, 2009-2026")
    fig.tight_layout(rect=[0, 0, 1, 0.93])
    fig.savefig(os.path.join(OUT_DIR, "horizon_comparison.png"), dpi=120)
    plt.close(fig)


if __name__ == "__main__":
    main()
