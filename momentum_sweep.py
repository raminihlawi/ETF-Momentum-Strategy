"""
Parameter robustness sweep for Strategy A (Composite Momentum).

Per STRATEGY_SPEC.md section A.6 / section 3: vary the strategy's key
thresholds and report the *distribution / plateau* of results, not the
single best configuration. Decided in advance, not iterated on results:

  - SKIP_RECENT_DAYS : 0, 21        (the "12-1" convention vs Borslabbet default)
  - TOP_N            : 5, 10, 15
  - BAND_EXIT_PCT    : 0.10, 0.20, 0.30
  - quality cutoff   : 0.0 (off), 0.20, 0.40   (bottom-X% by R^2 excluded)

That's 2*3*3*3 = 54 runs. Outputs:
  - sweep_results/sweep_results.csv  -- one row per combo
  - sweep_results/sharpe_heatmaps.png -- TOP_N x BAND_EXIT_PCT heatmaps of
    Sharpe, one panel per (SKIP_RECENT_DAYS, quality cutoff)
  - sweep_results/distributions.png  -- histograms of Sharpe / CAGR / max DD
    across all combos, vs the buy & hold and naive-baseline reference lines

HONEST NOTE: this is still a single full-sample sweep (no held-out period,
no walk-forward). It answers "is there a plateau of OK configs, or one
lucky peak?" -- not "does this survive out-of-sample." That's the next step.

Run: python momentum_sweep.py
"""

import itertools
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import price_db
import backtest_engine as engine
import momentum_backtest as mb

OUT_DIR = "sweep_results"

SKIP_RECENT_DAYS_VALUES = [0, 21]
TOP_N_VALUES = [5, 10, 15]
BAND_EXIT_PCT_VALUES = [0.10, 0.20, 0.30]
QUALITY_CUTOFF_VALUES = [0.0, 0.20, 0.40]


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

    results = []
    total = (len(SKIP_RECENT_DAYS_VALUES) * len(TOP_N_VALUES)
             * len(BAND_EXIT_PCT_VALUES) * len(QUALITY_CUTOFF_VALUES))
    run_i = 0

    for skip in SKIP_RECENT_DAYS_VALUES:
        # indicators depend on skip_recent_days -> recompute once per skip value
        cfg_skip = dict(base_cfg, skip_recent_days=skip)
        data = {t: mb.add_indicators(df.copy(), cfg_skip) for t, df in raw_data.items()}

        rebal_dates = mb.month_end_dates(bench.index)
        min_start = bench.index[max(cfg_skip["horizons"].values()) + skip]
        rebal_dates = rebal_dates[rebal_dates >= min_start]

        for top_n, band, qcut in itertools.product(
                TOP_N_VALUES, BAND_EXIT_PCT_VALUES, QUALITY_CUTOFF_VALUES):
            run_i += 1
            cfg = dict(cfg_skip, top_n=top_n, band_exit_pct=band,
                       quality_cutoff_pct=qcut,
                       use_quality_filter=(qcut > 0.0))
            eq, log = mb.run_backtest(data, bench, regime_on, rebal_dates, cfg)
            stats = engine.perf_stats(eq, label=None, print_report=False)
            results.append({
                "skip_recent_days": skip, "top_n": top_n,
                "band_exit_pct": band, "quality_cutoff": qcut,
                "cagr": stats["cagr"], "sharpe": stats["sharpe"],
                "max_dd": stats["max_dd"], "ann_vol": stats["ann_vol"],
                "n_rebal": len(log), "total_cost": log["cost"].sum(),
            })
            print(f"  [{run_i}/{total}] skip={skip} top_n={top_n} "
                  f"band={band} qcut={qcut} -> CAGR {stats['cagr']*100:5.1f}%  "
                  f"Sharpe {stats['sharpe']:5.2f}  maxDD {stats['max_dd']*100:6.1f}%")

    df = pd.DataFrame(results)
    df.to_csv(os.path.join(OUT_DIR, "sweep_results.csv"), index=False)

    # ---- reference lines: naive baseline & buy & hold (use skip=0 data) ----
    cfg0 = dict(base_cfg, skip_recent_days=0)
    data0 = {t: mb.add_indicators(df_.copy(), cfg0) for t, df_ in raw_data.items()}
    rebal_dates0 = mb.month_end_dates(bench.index)
    min_start0 = bench.index[max(cfg0["horizons"].values())]
    rebal_dates0 = rebal_dates0[rebal_dates0 >= min_start0]

    naive_cfg = dict(cfg0, use_regime_gate=False, use_quality_filter=False,
                      use_banding=False, weighting="equal")
    eq_naive, _ = mb.run_backtest(data0, bench, regime_on, rebal_dates0, naive_cfg)
    naive_stats = engine.perf_stats(eq_naive, label=None, print_report=False)

    bh = engine.buy_and_hold(bench, base_cfg["starting_capital"]).reindex(eq_naive.index).ffill()
    bh_stats = engine.perf_stats(bh, label=None, print_report=False)

    plot_heatmaps(df)
    plot_distributions(df, naive_stats, bh_stats)

    print(f"\nWrote {os.path.join(OUT_DIR, 'sweep_results.csv')}")
    print(f"Wrote {os.path.join(OUT_DIR, 'sharpe_heatmaps.png')}")
    print(f"Wrote {os.path.join(OUT_DIR, 'distributions.png')}")
    print("\n=== SUMMARY ===")
    print(f"  Best Sharpe   : {df['sharpe'].max():.2f}  "
          f"(median {df['sharpe'].median():.2f}, worst {df['sharpe'].min():.2f})")
    print(f"  Naive baseline Sharpe : {naive_stats['sharpe']:.2f}")
    print(f"  Buy & hold Sharpe     : {bh_stats['sharpe']:.2f}")
    frac_beat_bh = (df["sharpe"] > bh_stats["sharpe"]).mean()
    print(f"  Fraction of {len(df)} combos beating buy & hold on Sharpe: {frac_beat_bh*100:.0f}%")
    print("  If that fraction is small, the few configs that beat B&H are likely")
    print("  noise (multiple-testing), not a real plateau.")


def plot_heatmaps(df):
    skips = sorted(df["skip_recent_days"].unique())
    qcuts = sorted(df["quality_cutoff"].unique())
    top_ns = sorted(df["top_n"].unique())
    bands = sorted(df["band_exit_pct"].unique())

    fig, axes = plt.subplots(len(skips), len(qcuts),
                              figsize=(4 * len(qcuts), 4 * len(skips)),
                              squeeze=False)

    vmin, vmax = df["sharpe"].min(), df["sharpe"].max()
    im = None
    for i, skip in enumerate(skips):
        for j, qcut in enumerate(qcuts):
            ax = axes[i][j]
            sub = df[(df["skip_recent_days"] == skip) & (df["quality_cutoff"] == qcut)]
            grid = sub.pivot(index="top_n", columns="band_exit_pct", values="sharpe")
            grid = grid.reindex(index=top_ns, columns=bands)
            im = ax.imshow(grid.values, cmap="RdYlGn", vmin=vmin, vmax=vmax, aspect="auto")
            ax.set_xticks(range(len(bands)))
            ax.set_xticklabels([f"{b:.2f}" for b in bands])
            ax.set_yticks(range(len(top_ns)))
            ax.set_yticklabels(top_ns)
            ax.set_xlabel("band_exit_pct")
            ax.set_ylabel("top_n")
            ax.set_title(f"skip_recent_days={skip}, quality_cutoff={qcut}")
            for yi in range(grid.shape[0]):
                for xi in range(grid.shape[1]):
                    val = grid.values[yi, xi]
                    if not np.isnan(val):
                        ax.text(xi, yi, f"{val:.2f}", ha="center", va="center", fontsize=8)

    fig.colorbar(im, ax=axes.ravel().tolist(), label="Sharpe", shrink=0.7)
    fig.suptitle("Strategy A robustness sweep -- Sharpe ratio (2009-2026, single full-sample run)")
    fig.tight_layout(rect=[0, 0, 0.92, 0.96])
    fig.savefig(os.path.join(OUT_DIR, "sharpe_heatmaps.png"), dpi=120)
    plt.close(fig)


def plot_distributions(df, naive_stats, bh_stats):
    fig, axes = plt.subplots(1, 3, figsize=(15, 4))

    for ax, col, title in zip(axes,
                                ["sharpe", "cagr", "max_dd"],
                                ["Sharpe ratio", "CAGR", "Max drawdown"]):
        vals = df[col] * (100 if col != "sharpe" else 1)
        ax.hist(vals, bins=15, color="steelblue", edgecolor="white")
        ref_bh = bh_stats[col] * (100 if col != "sharpe" else 1)
        ref_naive = naive_stats[col] * (100 if col != "sharpe" else 1)
        ax.axvline(ref_bh, color="black", linestyle="--", label="Buy & hold")
        ax.axvline(ref_naive, color="orange", linestyle="--", label="Naive baseline")
        ax.set_title(f"{title} across {len(df)} sweep combos")
        ax.set_xlabel(title + (" (%)" if col != "sharpe" else ""))
        ax.set_ylabel("count")
        ax.legend(fontsize=8)

    fig.suptitle("Strategy A robustness sweep -- distribution across configs")
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    fig.savefig(os.path.join(OUT_DIR, "distributions.png"), dpi=120)
    plt.close(fig)


if __name__ == "__main__":
    main()
