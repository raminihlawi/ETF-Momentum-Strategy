"""
Follow-up to momentum_horizon_sweep.py: does SKIP_RECENT_DAYS (the academic
"12-1" convention -- exclude the most recent month from each momentum
horizon, to avoid short-term reversal) help Strategy A close the gap to the
naive baseline / buy & hold? Also tests a longer horizon set (18/12/6 months)
since 12/6/3 won the previous comparison.

Combos: horizon_set in {12/6/3, 18/12/6} x skip_recent_days in {0, 21},
for both Strategy A (full) and the naive baseline. 2009-2026.

Outputs:
  - sweep_results/skip_sweep_results.csv
  - sweep_results/skip_comparison.png

Run: python momentum_skip_sweep.py
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
    "18/12/6": {"ret_18m": 378, "ret_12m": 252, "ret_6m": 126},
}
SKIP_VALUES = [0, 21]


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
    for hname, horizons in HORIZON_SETS.items():
        for skip in SKIP_VALUES:
            cfg_h = dict(base_cfg, horizons=horizons, skip_recent_days=skip)
            data = {t: mb.add_indicators(df.copy(), cfg_h) for t, df in raw_data.items()}

            rebal_dates = mb.month_end_dates(bench.index)
            min_start = bench.index[max(horizons.values()) + skip]
            rebal_dates = rebal_dates[rebal_dates >= min_start]

            for variant, cfg in [("Strategy A (full)", cfg_h),
                                  ("Naive baseline", dict(cfg_h, use_regime_gate=False,
                                                            use_quality_filter=False,
                                                            use_banding=False, weighting="equal"))]:
                eq, log = mb.run_backtest(data, bench, regime_on, rebal_dates, cfg)
                stats = engine.perf_stats(eq, label=None, print_report=False)
                results.append({
                    "horizon_set": hname, "skip": skip, "variant": variant,
                    "cagr": stats["cagr"], "sharpe": stats["sharpe"], "max_dd": stats["max_dd"],
                    "n_rebal": len(log), "total_cost": log["cost"].sum(),
                })
                print(f"  {hname:8s} skip={skip:2d} | {variant:18s} -> CAGR {stats['cagr']*100:5.1f}%  "
                      f"Sharpe {stats['sharpe']:5.2f}  maxDD {stats['max_dd']*100:6.1f}%  "
                      f"cost {log['cost'].sum():9,.0f}")

    df = pd.DataFrame(results)
    df.to_csv(os.path.join(OUT_DIR, "skip_sweep_results.csv"), index=False)
    plot_comparison(df, bh_stats)

    print(f"\nWrote {os.path.join(OUT_DIR, 'skip_sweep_results.csv')}")
    print(f"Wrote {os.path.join(OUT_DIR, 'skip_comparison.png')}")
    print(f"\n  Buy & hold reference: CAGR {bh_stats['cagr']*100:.1f}%  Sharpe {bh_stats['sharpe']:.2f}  "
          f"maxDD {bh_stats['max_dd']*100:.1f}%")


def plot_comparison(df, bh_stats):
    df["label"] = df["horizon_set"] + " / skip=" + df["skip"].astype(str)
    order = list(df["label"].unique())
    variants = df["variant"].unique()

    fig, axes = plt.subplots(1, 3, figsize=(15, 4.5))
    metrics = [("cagr", "CAGR (%)", 100), ("sharpe", "Sharpe", 1), ("max_dd", "Max drawdown (%)", 100)]

    x = range(len(order))
    width = 0.35
    for ax, (col, title, mult) in zip(axes, metrics):
        for i, variant in enumerate(variants):
            sub = df[df["variant"] == variant].set_index("label").reindex(order)
            offset = (i - 0.5) * width
            ax.bar([xi + offset for xi in x], sub[col] * mult, width, label=variant)
        ref = bh_stats[col] * mult
        ax.axhline(ref, color="black", linestyle="--", linewidth=1, label="Buy & hold")
        ax.set_xticks(list(x))
        ax.set_xticklabels(order, rotation=20, ha="right")
        ax.set_title(title)
        ax.legend(fontsize=8)

    fig.suptitle("Strategy A: SKIP_RECENT_DAYS (12-1 convention) and longer horizons, 2009-2026")
    fig.tight_layout(rect=[0, 0, 1, 0.92])
    fig.savefig(os.path.join(OUT_DIR, "skip_comparison.png"), dpi=120)
    plt.close(fig)


if __name__ == "__main__":
    main()
