"""
Robustness sweep for Strategy C (Multi-Asset ETF Dual-Momentum Rotation).

Per ETF_MOMENTUM_SPEC_2.md section 7: vary these dimensions, decided in
advance, not tuned to results:

  - lookback_days     : 126 (6m), 189 (9m), 252 (12m)
  - hold_n            : 3, 4, 5
  - composite         : False, True
  - abs_benchmark     : "cash_proxy", "zero"
  - use_max_per_block : True, False

That's 3*3*2*2*2 = 72 combos, all run with mode="full".

Also runs (once, at default CONFIG) the four reference baselines:
  (a) Buy & Hold IWDA, (b) Static 60/40, (c) naive (mode="naive"),
  (d) no_tilts (mode="no_tilts").

Outputs:
  - etf_sweep_results/sweep_results.csv
  - etf_sweep_results/sharpe_distribution.png
  - etf_sweep_results/dimension_effects.png

Run: python etf_sweep.py
"""

import itertools
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

import backtest_engine as engine
import etf_momentum_backtest as eb

OUT_DIR = "etf_sweep_results"

LOOKBACK_VALUES = [126, 189, 252]
HOLD_N_VALUES = [3, 4, 5]
COMPOSITE_VALUES = [False, True]
ABS_BENCHMARK_VALUES = ["cash_proxy", "zero"]
USE_MAX_PER_BLOCK_VALUES = [True, False]


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    base_cfg = eb.CONFIG

    universe_df = pd.read_csv(base_cfg["universe_csv"])
    blocks = dict(zip(universe_df["ticker"], universe_df["block"]))
    all_tickers = list(universe_df["ticker"])

    print("Loading price data...")
    raw_data = eb.load_data(all_tickers, start="2005-01-01", end=base_cfg["end"], cfg=base_cfg)
    print(f"  {len(raw_data)} tickers loaded.")

    print("Applying TER drag...")
    ter_data = eb.build_ter_adjusted_data(raw_data, base_cfg)

    bench_index_full = ter_data[eb.BASELINE_TICKER].index

    def prep_data(lookback, composite):
        """Compute indicators for a given (lookback, composite) pair, then
        restrict to the backtest window. Returns (data, all_dates, rebal_dates)."""
        cfg_tmp = dict(base_cfg, lookback_days=lookback, composite=composite)
        data = {}
        for t, df in ter_data.items():
            data[t] = eb.add_indicators(df.copy(), cfg_tmp)
        for t in data:
            data[t] = data[t].loc[data[t].index >= pd.Timestamp(base_cfg["start"])]
            if base_cfg["end"]:
                data[t] = data[t].loc[data[t].index <= pd.Timestamp(base_cfg["end"])]
        all_dates = data[eb.BASELINE_TICKER].index
        rebal_dates = eb.month_end_dates(all_dates)
        min_lb = lookback
        if len(all_dates) > min_lb:
            min_start = all_dates[min_lb]
            rebal_dates = rebal_dates[rebal_dates >= min_start]
        return data, all_dates, rebal_dates

    # cache prepped data per (lookback, composite) pair -- 6 distinct combos
    prepped_cache = {}

    results = []
    combos = list(itertools.product(LOOKBACK_VALUES, HOLD_N_VALUES, COMPOSITE_VALUES,
                                      ABS_BENCHMARK_VALUES, USE_MAX_PER_BLOCK_VALUES))
    total = len(combos)
    print(f"\nRunning {total} sweep combos for Strategy C (full)...")

    for i, (lookback, hold_n, composite, abs_bench, use_mpb) in enumerate(combos, start=1):
        key = (lookback, composite)
        if key not in prepped_cache:
            prepped_cache[key] = prep_data(lookback, composite)
        data, all_dates, rebal_dates = prepped_cache[key]

        cfg = dict(base_cfg, lookback_days=lookback, hold_n=hold_n, composite=composite,
                    abs_benchmark=abs_bench, use_max_per_block=use_mpb)

        eq, log, dc = eb.run_backtest(data, blocks, all_dates, rebal_dates, cfg, mode="full")
        stats = engine.perf_stats(eq, label=None, print_report=False)
        total_cost = log["cost"].sum() if log is not None and not log.empty else 0.0

        results.append({
            "lookback_days": lookback, "hold_n": hold_n, "composite": composite,
            "abs_benchmark": abs_bench, "use_max_per_block": use_mpb,
            "cagr": stats["cagr"], "sharpe": stats["sharpe"],
            "ann_vol": stats["ann_vol"], "max_dd": stats["max_dd"],
            "pct_defensive_cash": dc, "total_cost": total_cost,
            "n_rebal": len(log) if log is not None else 0,
        })
        print(f"  [{i}/{total}] lb={lookback} hold_n={hold_n} composite={composite} "
              f"abs={abs_bench} mpb={use_mpb} -> CAGR {stats['cagr']*100:5.1f}% "
              f"Sharpe {stats['sharpe']:5.2f} maxDD {stats['max_dd']*100:6.1f}%")

    df = pd.DataFrame(results)
    df.to_csv(os.path.join(OUT_DIR, "sweep_results.csv"), index=False)

    # ---- baselines at default CONFIG ----
    print("\nRunning reference baselines at default CONFIG...")
    data_def, all_dates_def, rebal_dates_def = prep_data(base_cfg["lookback_days"], base_cfg["composite"])
    cfg_def = base_cfg

    eq_bh = engine.buy_and_hold(
        raw_data[eb.BASELINE_TICKER].loc[raw_data[eb.BASELINE_TICKER].index >= pd.Timestamp(cfg_def["start"])],
        cfg_def["starting_capital"]).reindex(all_dates_def).ffill()
    stats_bh = engine.perf_stats(eq_bh, label=None, print_report=False)

    eq_6040, _ = eb.run_static_alloc(data_def, all_dates_def, rebal_dates_def, cfg_def,
                                       weights={eb.BASELINE_TICKER: 0.6, eb.DEFENSIVE_TICKER: 0.4})
    stats_6040 = engine.perf_stats(eq_6040, label=None, print_report=False)

    eq_naive, _, _ = eb.run_backtest(data_def, blocks, all_dates_def, rebal_dates_def, cfg_def, mode="naive")
    stats_naive = engine.perf_stats(eq_naive, label=None, print_report=False)

    eq_notilt, _, _ = eb.run_backtest(data_def, blocks, all_dates_def, rebal_dates_def, cfg_def, mode="no_tilts")
    stats_notilt = engine.perf_stats(eq_notilt, label=None, print_report=False)

    baselines = {
        "(a) Buy & Hold IWDA": stats_bh,
        "(b) Static 60/40": stats_6040,
        "(c) Naive relative momentum": stats_naive,
        "(d) No sector/factor tilts": stats_notilt,
    }

    plot_sharpe_distribution(df, baselines)
    plot_dimension_effects(df)

    print(f"\nWrote {os.path.join(OUT_DIR, 'sweep_results.csv')}")
    print(f"Wrote {os.path.join(OUT_DIR, 'sharpe_distribution.png')}")
    print(f"Wrote {os.path.join(OUT_DIR, 'dimension_effects.png')}")

    # ---- summary ----
    print("\n=== SUMMARY ===")
    print(f"  Sharpe across {len(df)} combos: median {df['sharpe'].median():.2f}, "
          f"best {df['sharpe'].max():.2f}, worst {df['sharpe'].min():.2f}")
    frac_beat_a = (df["sharpe"] > stats_bh["sharpe"]).mean()
    frac_beat_b = (df["sharpe"] > stats_6040["sharpe"]).mean()
    print(f"  Fraction beating (a) Buy & Hold IWDA (Sharpe {stats_bh['sharpe']:.2f}): {frac_beat_a*100:.0f}%")
    print(f"  Fraction beating (b) Static 60/40 (Sharpe {stats_6040['sharpe']:.2f}): {frac_beat_b*100:.0f}%")

    dims = ["lookback_days", "hold_n", "composite", "abs_benchmark", "use_max_per_block"]
    spreads = {}
    for dim in dims:
        means = df.groupby(dim)["sharpe"].mean()
        spreads[dim] = means.max() - means.min()
    biggest = max(spreads, key=spreads.get)
    print("  Sharpe spread (max group-mean - min group-mean) by dimension:")
    for dim, spread in sorted(spreads.items(), key=lambda x: -x[1]):
        print(f"    {dim:<20s}: {spread:.3f}")
    print(f"  -> Dimension with largest effect on Sharpe: {biggest}")


def plot_sharpe_distribution(df, baselines):
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.hist(df["sharpe"], bins=15, color="steelblue", edgecolor="white")
    colors = ["black", "gray", "orange", "green"]
    for (name, stats), color in zip(baselines.items(), colors):
        ax.axvline(stats["sharpe"], color=color, linestyle="--", label=f"{name} ({stats['sharpe']:.2f})")
    ax.set_title(f"Strategy C robustness sweep -- Sharpe ratio distribution across {len(df)} combos")
    ax.set_xlabel("Sharpe ratio")
    ax.set_ylabel("count")
    ax.legend(fontsize=9)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT_DIR, "sharpe_distribution.png"), dpi=120)
    plt.close(fig)


def plot_dimension_effects(df):
    dims = ["lookback_days", "hold_n", "composite", "abs_benchmark", "use_max_per_block"]
    fig, axes = plt.subplots(2, 3, figsize=(15, 9))
    axes = axes.ravel()

    for ax, dim in zip(axes, dims):
        groups = sorted(df[dim].unique(), key=lambda x: str(x))
        data_by_group = [df.loc[df[dim] == g, "sharpe"].values for g in groups]
        ax.boxplot(data_by_group, labels=[str(g) for g in groups])
        ax.set_title(f"Sharpe by {dim}")
        ax.set_ylabel("Sharpe")
        ax.grid(alpha=0.3)

    for ax in axes[len(dims):]:
        ax.axis("off")

    fig.suptitle("Strategy C robustness sweep -- Sharpe by dimension (72 combos, full-sample)")
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    fig.savefig(os.path.join(OUT_DIR, "dimension_effects.png"), dpi=120)
    plt.close(fig)


if __name__ == "__main__":
    main()
