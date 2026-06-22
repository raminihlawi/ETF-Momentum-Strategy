"""
Robustness sweep + "how is relative momentum determined" exploration for
Strategy D (Marketfighter replica, see marketfighter_replica.py).

PART 1 -- Robustness sweep
Per the same validation discipline as Strategy A/C: vary, decided in
advance, not tuned to results:
  - lookback_days       : 126 (6m), 189 (9m), 252 (12m)
  - momentum_metric      : "raw" (trailing total return -- the article's
                            description), "risk_adjusted" (return / 126d
                            vol -- a common alternative "relative momentum"
                            definition), "composite" (avg percentile rank
                            of 3/6/12m returns, as used in Strategy C)
  - use_regime_filter    : True / False (the market-level absolute-momentum
                            cash gate)
That's 3 x 3 x 2 = 18 combos.

Outputs:
  - marketfighter_sweep_results/sweep_results.csv
  - marketfighter_sweep_results/sharpe_distribution.png
  - marketfighter_sweep_results/dimension_effects.png

PART 2 -- How relative momentum is determined
The article doesn't specify HOW "best momentum" is computed beyond "trailing
return over N months". This matters: different scoring rules pick different
ETFs in the same month. At the default lookback (252d, regime filter ON),
for each of the 3 momentum_metric definitions, track which factor ETF and
which sector ETF gets selected each month and plot selection frequencies
side by side.

Outputs:
  - marketfighter_sweep_results/selection_frequency.png

Run: python marketfighter_sweep.py
"""

import itertools
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import backtest_engine as engine
import etf_momentum_backtest as eb
import marketfighter_replica as mf

OUT_DIR = "marketfighter_sweep_results"

LOOKBACK_VALUES = [126, 189, 252]
MOMENTUM_METRICS = ["raw", "risk_adjusted", "composite"]
REGIME_FILTER_VALUES = [True, False]


# ============================ SCORING ============================
def compute_score(snapshot, tickers, metric, cfg):
    """Return a Series of scores (higher = better), indexed by ticker,
    for the candidates in `tickers` that are present in `snapshot`."""
    cands = [t for t in tickers if t in snapshot.index]
    if not cands:
        return pd.Series(dtype=float)

    if metric == "raw":
        s = snapshot.loc[cands, "ret_lb"]
        return s.dropna()

    if metric == "risk_adjusted":
        ret = snapshot.loc[cands, "ret_lb"]
        vol = snapshot.loc[cands, "vol"].replace(0, np.nan)
        s = ret / vol
        return s.dropna()

    if metric == "composite":
        cols = list(cfg["composite_horizons"].keys())
        sub = snapshot.loc[cands, cols].dropna()
        if sub.empty:
            return pd.Series(dtype=float)
        sub = sub.copy()
        for c in cols:
            sub[c + "_pct"] = sub[c].rank(pct=True)
        return sub[[c + "_pct" for c in cols]].mean(axis=1)

    raise ValueError(f"unknown metric {metric}")


def best_of(snapshot, tickers, metric, cfg):
    s = compute_score(snapshot, tickers, metric, cfg)
    return None if s.empty else s.idxmax()


# ============================ BACKTEST (generalized) ============================
def run_backtest(data, all_dates, rebal_dates, cfg, metric, use_regime_filter,
                  record_selections=None):
    cash_bal = cfg["starting_capital"]
    shares = {}
    equity_curve = []
    rebal_log = []
    pending = None
    rebal_set = set(rebal_dates)
    cash_days, total_days = 0, 0

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
            for t in set(list(shares.keys()) + list(new_shares.keys())):
                old_val = shares.get(t, 0.0) * open_px.get(t, 0.0)
                new_val = new_shares.get(t, 0.0) * open_px.get(t, 0.0)
                delta = abs(new_val - old_val)
                rate = cfg["cost_per_side_overrides"].get(t, cfg["cost_per_side"])
                cost += delta * rate

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
                rows[t] = entry
            if not rows:
                pending = {}
                continue
            snapshot = pd.DataFrame(rows).T

            ok = True
            if use_regime_filter:
                ok = mf.regime_ok(snapshot, cfg)

            if not ok:
                pending = {}
                if record_selections is not None:
                    record_selections.append((d, None, None))
                continue

            best_factor = best_of(snapshot, mf.FACTOR_TICKERS, metric, cfg)
            best_sector = best_of(snapshot, mf.SECTOR_TICKERS, metric, cfg)
            if record_selections is not None:
                record_selections.append((d, best_factor, best_sector))

            weights = {}
            if best_factor is not None:
                weights[best_factor] = weights.get(best_factor, 0.0) + 0.5
            if best_sector is not None:
                weights[best_sector] = weights.get(best_sector, 0.0) + 0.5
            pending = weights

    eq = pd.Series({d: v for d, v in equity_curve}).sort_index()
    cash_frac = cash_days / total_days if total_days else 0.0
    return eq, pd.DataFrame(rebal_log, columns=["date", "n_holdings", "cost"]), cash_frac


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

    # ---- PART 1: robustness sweep ----
    results = []
    indicator_cache = {}  # lookback_days -> data with indicators

    for lookback in LOOKBACK_VALUES:
        cfg_lb = dict(base_cfg, lookback_days=lookback, composite=True)  # composite=True so both ret_lb and 3/6/12m cols exist
        data = {t: eb.add_indicators(df.copy(), cfg_lb) for t, df in ter_data.items()}
        for t in data:
            data[t] = data[t].loc[data[t].index >= pd.Timestamp(base_cfg["start"])]
        indicator_cache[lookback] = data

    all_dates = indicator_cache[252][eb.BASELINE_TICKER].index
    rebal_dates_all = eb.month_end_dates(all_dates)
    min_start = all_dates[252]
    rebal_dates_all = rebal_dates_all[rebal_dates_all >= min_start]

    print(f"\nBacktest window: {all_dates[0].date()} -> {all_dates[-1].date()}, "
          f"{len(rebal_dates_all)} rebalances")
    print(f"Buy & hold IWDA reference: CAGR {bh_stats['cagr']*100:.1f}%  Sharpe {bh_stats['sharpe']:.2f}  "
          f"MaxDD {bh_stats['max_dd']*100:.1f}%")

    total = len(LOOKBACK_VALUES) * len(MOMENTUM_METRICS) * len(REGIME_FILTER_VALUES)
    run_i = 0
    for lookback in LOOKBACK_VALUES:
        cfg_lb = dict(base_cfg, lookback_days=lookback, composite=True)
        data = indicator_cache[lookback]
        min_start_lb = all_dates[lookback] if lookback < len(all_dates) else all_dates[-1]
        rebal_dates = rebal_dates_all[rebal_dates_all >= min_start_lb]

        for metric, use_regime in itertools.product(MOMENTUM_METRICS, REGIME_FILTER_VALUES):
            run_i += 1
            eq, log, cash_frac = run_backtest(data, all_dates, rebal_dates, cfg_lb,
                                               metric=metric, use_regime_filter=use_regime)
            stats = engine.perf_stats(eq, label=None, print_report=False)
            results.append({
                "lookback_days": lookback, "momentum_metric": metric,
                "use_regime_filter": use_regime,
                "cagr": stats["cagr"], "sharpe": stats["sharpe"],
                "max_dd": stats["max_dd"], "ann_vol": stats["ann_vol"],
                "cash_frac": cash_frac, "n_rebal": len(log), "total_cost": log["cost"].sum(),
            })
            print(f"  [{run_i}/{total}] lookback={lookback:3d} metric={metric:13s} "
                  f"regime={use_regime!s:5s} -> CAGR {stats['cagr']*100:6.2f}%  "
                  f"Sharpe {stats['sharpe']:5.2f}  maxDD {stats['max_dd']*100:6.1f}%  "
                  f"cash {cash_frac*100:4.1f}%")

    df = pd.DataFrame(results)
    df.to_csv(os.path.join(OUT_DIR, "sweep_results.csv"), index=False)

    plot_distribution(df, bh_stats)
    plot_dimension_effects(df)

    print(f"\nWrote {os.path.join(OUT_DIR, 'sweep_results.csv')}")
    print(f"Wrote {os.path.join(OUT_DIR, 'sharpe_distribution.png')}")
    print(f"Wrote {os.path.join(OUT_DIR, 'dimension_effects.png')}")
    print("\n=== SWEEP SUMMARY ===")
    print(f"  Sharpe: median {df['sharpe'].median():.2f}, best {df['sharpe'].max():.2f}, "
          f"worst {df['sharpe'].min():.2f}")
    frac_beat_bh = (df["sharpe"] > bh_stats["sharpe"]).mean()
    print(f"  Fraction of {len(df)} combos beating Buy & Hold IWDA on Sharpe: {frac_beat_bh*100:.0f}%")
    for dim in ["lookback_days", "momentum_metric", "use_regime_filter"]:
        spread = df.groupby(dim)["sharpe"].mean().max() - df.groupby(dim)["sharpe"].mean().min()
        print(f"  Effect of {dim:18s}: group-mean Sharpe spread = {spread:.3f}")

    # ---- PART 2: how is "best momentum" determined? selection frequency ----
    print("\n=== PART 2: selection frequency by momentum_metric (lookback=252, regime ON) ===")
    data252 = indicator_cache[252]
    rebal_dates_252 = rebal_dates_all[rebal_dates_all >= all_dates[252]]

    selection_records = {}
    for metric in MOMENTUM_METRICS:
        recs = []
        run_backtest(data252, all_dates, rebal_dates_252, dict(base_cfg, lookback_days=252, composite=True),
                      metric=metric, use_regime_filter=True, record_selections=recs)
        selection_records[metric] = recs

    plot_selection_frequency(selection_records)
    print(f"Wrote {os.path.join(OUT_DIR, 'selection_frequency.png')}")


def plot_distribution(df, bh_stats):
    fig, axes = plt.subplots(1, 3, figsize=(15, 4))
    for ax, col, title in zip(axes, ["sharpe", "cagr", "max_dd"],
                                ["Sharpe ratio", "CAGR", "Max drawdown"]):
        vals = df[col] * (100 if col != "sharpe" else 1)
        ax.hist(vals, bins=12, color="steelblue", edgecolor="white")
        ref = bh_stats[col] * (100 if col != "sharpe" else 1)
        ax.axvline(ref, color="black", linestyle="--", label="Buy & hold IWDA")
        ax.set_title(f"{title} across {len(df)} combos")
        ax.set_xlabel(title + (" (%)" if col != "sharpe" else ""))
        ax.set_ylabel("count")
        ax.legend(fontsize=8)
    fig.suptitle("Strategy D (Marketfighter replica) robustness sweep -- distribution across 18 configs")
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    fig.savefig(os.path.join(OUT_DIR, "sharpe_distribution.png"), dpi=120)
    plt.close(fig)


def plot_dimension_effects(df):
    dims = ["lookback_days", "momentum_metric", "use_regime_filter"]
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.5))
    for ax, dim in zip(axes, dims):
        groups = sorted(df[dim].unique(), key=str)
        data_by_group = [df[df[dim] == g]["sharpe"].values for g in groups]
        ax.boxplot(data_by_group, labels=[str(g) for g in groups])
        ax.set_title(f"Sharpe by {dim}")
        ax.set_ylabel("Sharpe")
        ax.grid(alpha=0.3)
    fig.suptitle("Strategy D: effect of each swept dimension on Sharpe (18 combos)")
    fig.tight_layout(rect=[0, 0, 1, 0.92])
    fig.savefig(os.path.join(OUT_DIR, "dimension_effects.png"), dpi=120)
    plt.close(fig)


def plot_selection_frequency(selection_records):
    fig, axes = plt.subplots(2, 3, figsize=(16, 8))
    for col, metric in enumerate(MOMENTUM_METRICS):
        recs = selection_records[metric]
        factors = [f for _, f, s in recs if f is not None]
        sectors = [s for _, f, s in recs if s is not None]
        n = len(recs)

        for row, (picks, tickers, label) in enumerate([
                (factors, mf.FACTOR_TICKERS, "Factor sleeve"),
                (sectors, mf.SECTOR_TICKERS, "Sector sleeve")]):
            ax = axes[row][col]
            counts = pd.Series(picks).value_counts()
            counts = counts.reindex(tickers).fillna(0)
            pct = counts / n * 100
            ax.bar(range(len(tickers)), pct.values, color="steelblue")
            ax.set_xticks(range(len(tickers)))
            ax.set_xticklabels(tickers, rotation=45, ha="right", fontsize=8)
            ax.set_ylim(0, 100)
            ax.set_title(f"{label} -- metric={metric}")
            ax.set_ylabel("% of months selected")

    fig.suptitle("How 'relative momentum' is determined: which ETF gets picked each month,\n"
                  "by momentum scoring method (lookback=252d, regime filter ON)")
    fig.tight_layout(rect=[0, 0, 1, 0.93])
    fig.savefig(os.path.join(OUT_DIR, "selection_frequency.png"), dpi=120)
    plt.close(fig)


if __name__ == "__main__":
    main()
