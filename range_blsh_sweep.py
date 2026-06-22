"""
Parameter robustness sweep for Strategy B (Range/BLSH), per
STRATEGY_SPEC.md B.7 / section 3.

Decided in advance, not iterated on results:
  - RANGE_WINDOW : 40, 50, 60
  - MAX_R2       : 0.25, 0.35, 0.45  (chop threshold)
  - BOTTOM_FRAC  : 0.20, 0.30, 0.40  ("low in range" threshold)

That's 3*3*3 = 27 runs (ENTRY_MODE fixed at "next_open"; the other B.1
thresholds -- MAX_ABS_SLOPE, MIN_WIDTH_ATR, SUPPORT_BAND_ATR, MIN_TOUCHES,
SUPPORT_ESTABLISHED_BARS -- are held at their CONFIG defaults since they feed
the expensive per-bar support-touch/regression loops).

RANGE_WINDOW changes require recomputing the per-bar regression / floor /
ceiling / touches columns (the slow part); MAX_R2 and BOTTOM_FRAC only
recombine existing columns into new boolean signals, so those are cheap.

Outputs:
  - sweep_results/range_sweep_results.csv
  - sweep_results/range_sharpe_heatmaps.png  -- RANGE_WINDOW x BOTTOM_FRAC
    heatmaps of Sharpe, one panel per MAX_R2
  - sweep_results/range_distributions.png    -- Sharpe / CAGR / range-failure
    rate distributions, with no-trigger baseline and buy & hold references

Also reports a separate ENTRY_MODE comparison (next_open vs
stop_above_signal) at the default thresholds.

HONEST NOTE: single full-sample sweep, no held-out period / walk-forward.
Tells you whether there's a plateau of OK configs, not whether it survives
out-of-sample.

Run: python range_blsh_sweep.py
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
import range_blsh_backtest as rb

OUT_DIR = "sweep_results"

RANGE_WINDOW_VALUES = [40, 50, 60]
MAX_R2_VALUES = [0.25, 0.35, 0.45]
BOTTOM_FRAC_VALUES = [0.20, 0.30, 0.40]


def recompute_signals(df, cfg):
    """Cheaply recombine MAX_R2 / BOTTOM_FRAC into new range_ok / low_in_range
    / entry_signal / baseline_signal columns, reusing the columns that don't
    depend on those two thresholds (ATR, floor, ceiling, width, slope_ann,
    r2, floor_age, touches, range_pos)."""
    close, openp, high, low = df["Close"], df["Open"], df["High"], df["Low"]

    flat = df["slope_ann"].abs() < cfg["max_abs_slope"]
    choppy = df["r2"] < cfg["max_r2"]
    width_ok = df["width"] >= cfg["min_width_atr"] * df["ATR"]
    established = (df["floor_age"] >= cfg["support_established_bars"]) & (close > df["floor"])
    touches_ok = df["touches"] >= cfg["min_touches"]
    range_ok = flat & choppy & width_ok & established & touches_ok

    low_in_range = (df["range_pos"] <= cfg["bottom_frac"]) & ((close - df["floor"]) <= df["ATR"])

    support_band = df["floor"] + cfg["support_band_atr"] * df["ATR"]
    touched_support = low <= support_band
    touched_recent = touched_support | touched_support.shift(1).fillna(False)
    bull_bar = close > openp
    bar_range = (high - low).replace(0, np.nan)
    closes_upper_half = ((close - low) / bar_range) >= 0.5

    candidate = range_ok & low_in_range
    df["baseline_signal"] = candidate.fillna(False)
    df["entry_signal"] = (candidate & touched_recent & bull_bar & closes_upper_half).fillna(False)
    return df


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    base_cfg = rb.CONFIG

    print("Loading benchmark & universe...")
    bench = price_db.load_prices(base_cfg["benchmark"], start=base_cfg["start"],
                                   end=base_cfg["end"]).dropna()
    universe = price_db.load_universe(base_cfg["segments"])
    tickers = [t for t, _, seg in universe if seg != "Index"]
    raw_data = rb.load_data(tickers, base_cfg["start"], base_cfg["end"], base_cfg)
    print(f"  {len(raw_data)} tickers loaded.")

    results = []
    total = len(RANGE_WINDOW_VALUES) * len(MAX_R2_VALUES) * len(BOTTOM_FRAC_VALUES)
    run_i = 0

    for rw in RANGE_WINDOW_VALUES:
        print(f"Computing indicators for range_window={rw} (slow part)...")
        cfg_rw = dict(base_cfg, range_window=rw)
        data = {t: rb.add_indicators(df.copy(), cfg_rw) for t, df in raw_data.items()}

        for max_r2, bottom_frac in itertools.product(MAX_R2_VALUES, BOTTOM_FRAC_VALUES):
            run_i += 1
            cfg = dict(cfg_rw, max_r2=max_r2, bottom_frac=bottom_frac)
            data_run = {t: recompute_signals(df.copy(), cfg) for t, df in data.items()}
            eq, trades = rb.run_backtest(data_run, bench, cfg, signal_col="entry_signal")
            stats = engine.perf_stats(eq, label=None, print_report=False)
            tstats = engine.trade_stats(trades, print_report=False)
            rfr = rb.range_failure_rate(trades)
            results.append({
                "range_window": rw, "max_r2": max_r2, "bottom_frac": bottom_frac,
                "cagr": stats["cagr"], "sharpe": stats["sharpe"], "max_dd": stats["max_dd"],
                "n_trades": tstats["n_trades"], "win_rate": tstats["win_rate"],
                "profit_factor": tstats["profit_factor"], "range_failure_rate": rfr,
            })
            print(f"  [{run_i}/{total}] rw={rw} max_r2={max_r2} bottom_frac={bottom_frac} "
                  f"-> CAGR {stats['cagr']*100:5.1f}%  Sharpe {stats['sharpe']:5.2f}  "
                  f"n_trades {tstats['n_trades']:4d}  range_fail {rfr*100 if not np.isnan(rfr) else float('nan'):5.1f}%")

    df = pd.DataFrame(results)
    df.to_csv(os.path.join(OUT_DIR, "range_sweep_results.csv"), index=False)

    # ---- references: no-trigger baseline & buy & hold, at default thresholds ----
    cfg_def = dict(base_cfg)
    data_def = {t: rb.add_indicators(df_.copy(), cfg_def) for t, df_ in raw_data.items()}
    eq_base, trades_base = rb.run_backtest(data_def, bench, cfg_def, signal_col="baseline_signal")
    base_stats = engine.perf_stats(eq_base, label=None, print_report=False)
    base_rfr = rb.range_failure_rate(trades_base)

    bh = engine.buy_and_hold(bench, base_cfg["starting_capital"]).reindex(eq_base.index).ffill()
    bh_stats = engine.perf_stats(bh, label=None, print_report=False)

    # ---- entry_mode comparison at default thresholds ----
    print("\nComparing ENTRY_MODE at default thresholds...")
    for mode in ["next_open", "stop_above_signal"]:
        cfg_mode = dict(base_cfg, entry_mode=mode)
        eq_m, trades_m = rb.run_backtest(data_def, bench, cfg_mode, signal_col="entry_signal")
        stats_m = engine.perf_stats(eq_m, label=None, print_report=False)
        tstats_m = engine.trade_stats(trades_m, print_report=False)
        rfr_m = rb.range_failure_rate(trades_m)
        print(f"  {mode:18s}: CAGR {stats_m['cagr']*100:5.1f}%  Sharpe {stats_m['sharpe']:5.2f}  "
              f"n_trades {tstats_m['n_trades']:4d}  win_rate {tstats_m['win_rate']*100:5.1f}%  "
              f"range_fail {rfr_m*100 if not np.isnan(rfr_m) else float('nan'):5.1f}%")

    plot_heatmaps(df)
    plot_distributions(df, base_stats, base_rfr, bh_stats)

    print(f"\nWrote {os.path.join(OUT_DIR, 'range_sweep_results.csv')}")
    print(f"Wrote {os.path.join(OUT_DIR, 'range_sharpe_heatmaps.png')}")
    print(f"Wrote {os.path.join(OUT_DIR, 'range_distributions.png')}")

    print("\n=== SUMMARY ===")
    print(f"  Sharpe: best {df['sharpe'].max():.2f}, median {df['sharpe'].median():.2f}, "
          f"worst {df['sharpe'].min():.2f}")
    print(f"  No-trigger baseline Sharpe : {base_stats['sharpe']:.2f}  "
          f"(range-fail rate {base_rfr*100:.1f}%)")
    print(f"  Buy & hold Sharpe          : {bh_stats['sharpe']:.2f}")
    frac_positive = (df["sharpe"] > 0).mean()
    frac_beat_bh = (df["sharpe"] > bh_stats["sharpe"]).mean()
    print(f"  Fraction of {len(df)} combos with positive Sharpe: {frac_positive*100:.0f}%")
    print(f"  Fraction beating buy & hold on Sharpe: {frac_beat_bh*100:.0f}%")
    print(f"  Median range-failure rate across combos: {df['range_failure_rate'].median()*100:.1f}%")


def plot_heatmaps(df):
    rws = sorted(df["range_window"].unique())
    r2s = sorted(df["max_r2"].unique())
    bfs = sorted(df["bottom_frac"].unique())

    fig, axes = plt.subplots(1, len(r2s), figsize=(5 * len(r2s), 5), squeeze=False)
    vmin, vmax = df["sharpe"].min(), df["sharpe"].max()
    im = None
    for j, r2 in enumerate(r2s):
        ax = axes[0][j]
        sub = df[df["max_r2"] == r2]
        grid = sub.pivot(index="range_window", columns="bottom_frac", values="sharpe")
        grid = grid.reindex(index=rws, columns=bfs)
        im = ax.imshow(grid.values, cmap="RdYlGn", vmin=vmin, vmax=vmax, aspect="auto")
        ax.set_xticks(range(len(bfs)))
        ax.set_xticklabels([f"{b:.2f}" for b in bfs])
        ax.set_yticks(range(len(rws)))
        ax.set_yticklabels(rws)
        ax.set_xlabel("bottom_frac")
        ax.set_ylabel("range_window")
        ax.set_title(f"max_r2={r2}")
        for yi in range(grid.shape[0]):
            for xi in range(grid.shape[1]):
                val = grid.values[yi, xi]
                if not np.isnan(val):
                    ax.text(xi, yi, f"{val:.2f}", ha="center", va="center", fontsize=9)

    fig.colorbar(im, ax=axes.ravel().tolist(), label="Sharpe", shrink=0.7)
    fig.suptitle("Strategy B (Range/BLSH) robustness sweep -- Sharpe ratio (2020-2026, full sample)")
    fig.tight_layout(rect=[0, 0, 0.92, 0.94])
    fig.savefig(os.path.join(OUT_DIR, "range_sharpe_heatmaps.png"), dpi=120)
    plt.close(fig)


def plot_distributions(df, base_stats, base_rfr, bh_stats):
    fig, axes = plt.subplots(1, 3, figsize=(15, 4))

    cols = [("sharpe", "Sharpe ratio", 1), ("cagr", "CAGR (%)", 100),
            ("range_failure_rate", "Range-failure rate (%)", 100)]
    for ax, (col, title, mult) in zip(axes, cols):
        vals = df[col] * mult
        ax.hist(vals.dropna(), bins=12, color="steelblue", edgecolor="white")
        if col == "sharpe":
            ax.axvline(bh_stats["sharpe"], color="black", linestyle="--", label="Buy & hold")
            ax.axvline(base_stats["sharpe"], color="orange", linestyle="--", label="No-trigger baseline")
        elif col == "cagr":
            ax.axvline(bh_stats["cagr"] * 100, color="black", linestyle="--", label="Buy & hold")
            ax.axvline(base_stats["cagr"] * 100, color="orange", linestyle="--", label="No-trigger baseline")
        else:
            ax.axvline(base_rfr * 100, color="orange", linestyle="--", label="No-trigger baseline")
        ax.set_title(f"{title} across {len(df)} combos")
        ax.set_xlabel(title)
        ax.set_ylabel("count")
        ax.legend(fontsize=8)

    fig.suptitle("Strategy B (Range/BLSH) robustness sweep -- distribution across configs")
    fig.tight_layout(rect=[0, 0, 1, 0.93])
    fig.savefig(os.path.join(OUT_DIR, "range_distributions.png"), dpi=120)
    plt.close(fig)


if __name__ == "__main__":
    main()
