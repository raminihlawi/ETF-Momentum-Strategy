"""
PDF report for the "Strategy C Upgrade & Strategy D 'Secret Sauce'" work:
  - Task 1: global macro regime gate added to Strategy C
            (etf_momentum_backtest.py, use_global_regime_gate).
  - Task 2/3: 4 new momentum-scoring metrics for Strategy D
            (marketfighter_replica.add_secret_sauce_indicators) and the
            36-combo sweep (marketfighter_sweep2.py).

Re-runs Strategy C with the global regime gate ON (current default) vs. OFF
(old behaviour) for a before/after comparison, re-runs Strategy D under its
default config plus the best-Sharpe and best-CAGR "secret sauce" configs from
the sweep, and assembles everything with the sweep2 distribution/dimension
plots (generated here) and the sweep2_results.csv top-5 table.

Output: marketfighter_v2_report.pdf

Run: python generate_marketfighter_v2_report.py
"""

import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import pandas as pd

import backtest_engine as engine
import etf_momentum_backtest as eb
import marketfighter_replica as mf
import marketfighter_sweep2 as mf2

OUT_DIR = "marketfighter_sweep2_results"
REPORT_PATH = "marketfighter_v2_report.pdf"


def text_page(pdf, title, lines, fontsize=11):
    fig = plt.figure(figsize=(11, 8.5))
    fig.text(0.06, 0.94, title, fontsize=18, fontweight="bold", va="top")
    y = 0.86
    for line in lines:
        fs = fontsize
        weight = "normal"
        if line.startswith("## "):
            line = line[3:]
            fs = 13
            weight = "bold"
            y -= 0.01
        elif line.startswith("- "):
            line = "  • " + line[2:]
        fig.text(0.06, y, line, fontsize=fs, fontweight=weight, va="top", wrap=True)
        y -= 0.032 if fs == 11 else 0.04
    plt.axis("off")
    pdf.savefig(fig)
    plt.close(fig)


def image_page(pdf, png_path):
    if not os.path.exists(png_path):
        return
    img = plt.imread(png_path)
    h, w = img.shape[0], img.shape[1]
    fig_w = 11.0
    fig_h = fig_w * h / w
    fig = plt.figure(figsize=(fig_w, fig_h))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.imshow(img)
    ax.axis("off")
    pdf.savefig(fig)
    plt.close(fig)


def plot_sweep2_distribution(df, bh_stats):
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
    fig.suptitle("Strategy D 'secret sauce' sweep -- distribution across 36 configs")
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    path = os.path.join(OUT_DIR, "sweep2_distribution.png")
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path


def plot_sweep2_dimension_effects(df):
    dims = ["lookback_days", "momentum_metric", "use_global_regime_filter"]
    fig, axes = plt.subplots(1, 3, figsize=(16, 4.5))
    for ax, dim in zip(axes, dims):
        groups = sorted(df[dim].unique(), key=str)
        data_by_group = [df[df[dim] == g]["sharpe"].values for g in groups]
        ax.boxplot(data_by_group, tick_labels=[str(g) for g in groups])
        ax.set_title(f"Sharpe by {dim}")
        ax.set_ylabel("Sharpe")
        if dim == "momentum_metric":
            ax.tick_params(axis="x", rotation=30)
        ax.grid(alpha=0.3)
    fig.suptitle("Strategy D 'secret sauce' sweep: effect of each dimension on Sharpe (36 combos)")
    fig.tight_layout(rect=[0, 0, 1, 0.92])
    path = os.path.join(OUT_DIR, "sweep2_dimension_effects.png")
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path


def main():
    cfg = mf.CONFIG
    universe_df = pd.read_csv(cfg["universe_csv"])
    all_tickers = list(universe_df["ticker"])
    blocks = dict(zip(universe_df["ticker"], universe_df["block"]))

    print("Loading price data...")
    raw_data = eb.load_data(all_tickers, start="2005-01-01", end=cfg["end"], cfg=cfg)
    data = eb.build_ter_adjusted_data(raw_data, cfg)
    for t in data:
        data[t] = eb.add_indicators(data[t].copy(), cfg)
    for t in data:
        data[t] = data[t].loc[data[t].index >= pd.Timestamp(cfg["start"])]
        if cfg["end"]:
            data[t] = data[t].loc[data[t].index <= pd.Timestamp(cfg["end"])]

    all_dates = data[eb.BASELINE_TICKER].index
    rebal_dates = eb.month_end_dates(all_dates)
    min_lb = cfg["lookback_days"]
    if len(all_dates) > min_lb:
        min_start = all_dates[min_lb]
        rebal_dates = rebal_dates[rebal_dates >= min_start]

    # ---- TASK 1: Strategy C, global regime gate ON (new default) vs OFF (old) ----
    print("Running Strategy C with global regime gate ON (new default)...")
    cfg_c_on = dict(eb.CONFIG, use_global_regime_gate=True)
    eq_c_on, log_c_on, dc_c_on = eb.run_backtest(data, blocks, all_dates, rebal_dates, cfg_c_on, mode="full")
    stats_c_on = engine.perf_stats(eq_c_on, label=None, print_report=False)

    print("Running Strategy C with global regime gate OFF (old behaviour)...")
    cfg_c_off = dict(eb.CONFIG, use_global_regime_gate=False)
    eq_c_off, log_c_off, dc_c_off = eb.run_backtest(data, blocks, all_dates, rebal_dates, cfg_c_off, mode="full")
    stats_c_off = engine.perf_stats(eq_c_off, label=None, print_report=False)

    print("Running baseline (a) Buy & Hold IWDA...")
    eq_a = engine.buy_and_hold(
        raw_data[eb.BASELINE_TICKER].loc[raw_data[eb.BASELINE_TICKER].index >= pd.Timestamp(cfg["start"])],
        cfg["starting_capital"]).reindex(all_dates).ffill()
    stats_a = engine.perf_stats(eq_a, label=None, print_report=False)

    # ---- TASK 2/3: Strategy D, default vs best "secret sauce" configs ----
    sweep2_csv = os.path.join(OUT_DIR, "sweep2_results.csv")
    sweep2_df = pd.read_csv(sweep2_csv)

    print("Running Strategy D (default: raw, 252d, regime ON)...")
    mf_cfg_d = dict(mf.CONFIG)
    ter_data = eb.build_ter_adjusted_data(raw_data, mf_cfg_d)
    data_252 = {}
    for t, df in ter_data.items():
        d = eb.add_indicators(df.copy(), dict(mf_cfg_d, composite=True))
        d = mf.add_secret_sauce_indicators(d, dict(mf_cfg_d, lookback_days=252))
        data_252[t] = d.loc[d.index >= pd.Timestamp(mf_cfg_d["start"])]
    all_dates_252 = data_252[eb.BASELINE_TICKER].index
    rebal_dates_252 = eb.month_end_dates(all_dates_252)
    rebal_dates_252 = rebal_dates_252[rebal_dates_252 >= all_dates_252[252]]

    eq_d_default, _, _, _ = mf2.run_backtest(data_252, all_dates_252, rebal_dates_252,
                                              dict(mf_cfg_d, lookback_days=252, composite=True),
                                              metric="raw", use_regime_filter=True)
    stats_d_default = engine.perf_stats(eq_d_default, label=None, print_report=False)

    print("Running Strategy D best-Sharpe config (frog_in_the_pan, 252d, regime ON)...")
    eq_d_bestsharpe, _, _, _ = mf2.run_backtest(data_252, all_dates_252, rebal_dates_252,
                                                 dict(mf_cfg_d, lookback_days=252, composite=True),
                                                 metric="frog_in_the_pan", use_regime_filter=True)
    stats_d_bestsharpe = engine.perf_stats(eq_d_bestsharpe, label=None, print_report=False)

    print("Running Strategy D best-CAGR config (frog_in_the_pan, 252d, regime OFF)...")
    eq_d_bestcagr, _, _, _ = mf2.run_backtest(data_252, all_dates_252, rebal_dates_252,
                                               dict(mf_cfg_d, lookback_days=252, composite=True),
                                               metric="frog_in_the_pan", use_regime_filter=False)
    stats_d_bestcagr = engine.perf_stats(eq_d_bestcagr, label=None, print_report=False)

    # ---- sweep2 plots ----
    bh_stats_252 = engine.perf_stats(
        engine.buy_and_hold(
            raw_data[eb.BASELINE_TICKER].loc[raw_data[eb.BASELINE_TICKER].index >= pd.Timestamp(mf_cfg_d["start"])],
            mf_cfg_d["starting_capital"]), label=None, print_report=False)
    dist_png = plot_sweep2_distribution(sweep2_df, bh_stats_252)
    dim_png = plot_sweep2_dimension_effects(sweep2_df)

    with PdfPages(REPORT_PATH) as pdf:
        # ---- Title / executive summary ----
        text_page(pdf, "Strategy C Upgrade & Strategy D 'Secret Sauce' Sweep", [
            "Two upgrades made to the ETF rotation strategies:",
            "",
            "## 1. Strategy C: global macro regime gate",
            "- Added use_global_regime_gate (default True): if IWDA.L's trailing",
            "  12m return <= IBTS.L's (cash proxy), the WHOLE portfolio is forced",
            "  to 100% cash, bypassing per-asset relative-momentum ranking. This",
            "  targets the 'whipsaw near the cash hurdle' failure mode where",
            "  individual assets keep flip-flopping just above/below their own",
            "  abs-momentum gate while the broad market is clearly weak.",
            f"- Effect: Sharpe {stats_c_off['sharpe']:.2f} -> {stats_c_on['sharpe']:.2f}, "
            f"MaxDD {stats_c_off['max_dd']*100:.2f}% -> {stats_c_on['max_dd']*100:.2f}%, "
            f"CAGR {stats_c_off['cagr']*100:.2f}% -> {stats_c_on['cagr']*100:.2f}%.",
            "  A real, if modest, improvement in risk-adjusted terms and drawdown.",
            "",
            "## 2. Strategy D: 4 new 'relative momentum' scoring metrics",
            "- skip_1m_12m (12-1 momentum), r2_adjusted (return x trend-smoothness",
            "  R^2), frog_in_the_pan (information discreteness), sma_200_distance",
            "  (extension above/below the 200d moving average).",
            "- 36-combo sweep (3 lookbacks x 6 metrics x regime filter on/off).",
            "",
            "## Headline finding",
            f"- Best Sharpe: frog_in_the_pan, 252d, regime ON -> Sharpe "
            f"{stats_d_bestsharpe['sharpe']:.2f} (vs. default raw/252d/regime-ON "
            f"Sharpe {stats_d_default['sharpe']:.2f}), CAGR "
            f"{stats_d_bestsharpe['cagr']*100:.2f}%, MaxDD "
            f"{stats_d_bestsharpe['max_dd']*100:.2f}%.",
            f"- Best CAGR: frog_in_the_pan, 252d, regime OFF -> CAGR "
            f"{stats_d_bestcagr['cagr']*100:.2f}% (close to but still below the",
            f"  article's claimed ~16%), Sharpe {stats_d_bestcagr['sharpe']:.2f}, "
            f"MaxDD {stats_d_bestcagr['max_dd']*100:.2f}%.",
            "- NO combo reaches CAGR >= 14% with MaxDD shallower than -20% --",
            "  the article's 16% CAGR + shallow-drawdown combination was not",
            "  reproduced by any of the 36 'secret sauce' configs in this sample.",
            "- 252d lookback remains dominant for every new metric, consistent",
            "  with the original sweep.",
        ], fontsize=10.5)

        # ---- Strategy C before/after table ----
        text_page(pdf, "Strategy C -- Global Regime Gate: Before vs. After", [
            "## Headline results (2019-10 to 2026-06)",
            f"{'':42s}{'CAGR':>8s}{'Sharpe':>9s}{'AnnVol':>9s}{'MaxDD':>9s}{'%Def/Cash':>11s}",
            f"{'Strategy C, regime gate OFF (old)':42s}{stats_c_off['cagr']*100:7.2f}%"
            f"{stats_c_off['sharpe']:9.2f}{stats_c_off['ann_vol']*100:8.2f}%"
            f"{stats_c_off['max_dd']*100:8.2f}%{dc_c_off*100:10.1f}%",
            f"{'Strategy C, regime gate ON (new default)':42s}{stats_c_on['cagr']*100:7.2f}%"
            f"{stats_c_on['sharpe']:9.2f}{stats_c_on['ann_vol']*100:8.2f}%"
            f"{stats_c_on['max_dd']*100:8.2f}%{dc_c_on*100:10.1f}%",
            f"{'(a) Buy & Hold IWDA':42s}{stats_a['cagr']*100:7.2f}%"
            f"{stats_a['sharpe']:9.2f}{stats_a['ann_vol']*100:8.2f}%"
            f"{stats_a['max_dd']*100:8.2f}%{0.0:10.1f}%",
            "",
            "## What changed",
            "- The gate only fires when the GLOBAL market (IWDA.L) is below its",
            "  own cash hurdle -- a relatively rare, high-conviction signal, so",
            "  the change in time-in-cash is modest but concentrated in the",
            "  worst stretches (e.g. 2022).",
            f"- % of days with >50% in defensive/cash: {dc_c_off*100:.1f}% (off) ->"
            f" {dc_c_on*100:.1f}% (on).",
            "- The improvement is modest, not transformative: this is a real",
            "  incremental fix for the whipsaw failure mode, not a silver bullet",
            "  -- Strategy C still trails Buy & Hold IWDA on Sharpe in this",
            "  bull-dominated sample.",
        ], fontsize=10.5)

        # ---- Strategy C equity curve ----
        fig, ax = plt.subplots(figsize=(11, 7))
        for name, eq, ls, color in [
            ("Strategy C, regime gate OFF (old)", eq_c_off, "-", None),
            ("Strategy C, regime gate ON (new default)", eq_c_on, "-", None),
            ("(a) Buy & Hold IWDA", eq_a, "--", "black"),
        ]:
            ax.plot(eq.index, eq / eq.iloc[0], label=name, lw=1.5, ls=ls, color=color)
        ax.set_yscale("log")
        ax.set_title("Strategy C: global regime gate, growth of 1 (log scale)")
        ax.set_ylabel("Equity (normalized, log scale)")
        ax.legend(fontsize=9)
        ax.grid(alpha=0.3, which="both")
        fig.tight_layout()
        pdf.savefig(fig)
        plt.close(fig)

        # ---- Strategy D equity curve: default vs secret-sauce configs ----
        fig, ax = plt.subplots(figsize=(11, 7))
        for name, eq, ls, color in [
            ("Strategy D default (raw, 252d, regime ON)", eq_d_default, "-", None),
            ("Strategy D best-Sharpe (frog_in_the_pan, 252d, regime ON)", eq_d_bestsharpe, "-", None),
            ("Strategy D best-CAGR (frog_in_the_pan, 252d, regime OFF)", eq_d_bestcagr, "-", None),
            ("(a) Buy & Hold IWDA", eq_a, "--", "black"),
        ]:
            ax.plot(eq.index, eq / eq.iloc[0], label=name, lw=1.5, ls=ls, color=color)
        ax.set_yscale("log")
        ax.set_title("Strategy D: 'secret sauce' metrics, growth of 1 (log scale)")
        ax.set_ylabel("Equity (normalized, log scale)")
        ax.legend(fontsize=9)
        ax.grid(alpha=0.3, which="both")
        fig.tight_layout()
        pdf.savefig(fig)
        plt.close(fig)

        # ---- sweep2 distribution + dimension effects ----
        image_page(pdf, dist_png)
        image_page(pdf, dim_png)

        # ---- Top-5 table ----
        top5 = sweep2_df.sort_values("sharpe", ascending=False).head(5).copy()
        top5["lookback_days"] = top5["lookback_days"].astype(int)
        top5["cagr"] = (top5["cagr"] * 100).round(2).astype(str) + "%"
        top5["sharpe"] = top5["sharpe"].round(2)
        top5["max_dd"] = (top5["max_dd"] * 100).round(2).astype(str) + "%"
        top5["turnover_pct"] = top5["turnover_pct"].round(1).astype(str) + "%/rebal"
        top5 = top5[["lookback_days", "momentum_metric", "use_global_regime_filter",
                      "sharpe", "cagr", "max_dd", "turnover_pct"]]
        top5.columns = ["Lookback", "Metric", "Global regime", "Sharpe", "CAGR", "MaxDD", "Turnover"]

        fig, ax = plt.subplots(figsize=(11, 4))
        ax.axis("off")
        ax.set_title("Top 5 configs by Sharpe (36-combo sweep)", fontsize=14, fontweight="bold", pad=20)
        tbl = ax.table(cellText=top5.values, colLabels=top5.columns, loc="center", cellLoc="center")
        tbl.auto_set_font_size(False)
        tbl.set_fontsize(10)
        tbl.scale(1, 1.8)
        pdf.savefig(fig)
        plt.close(fig)

        # ---- Caveats ----
        text_page(pdf, "Honest Caveats & Next Steps", [
            "## Sample period",
            "- Same ~6.7-year window (2019-10 to 2026-06) as all prior reports --",
            "  short, equity-bull-dominated, and not comparable to the article's",
            "  16% CAGR claims (2000-2025 / 2016-2025).",
            "",
            "## Strategy C global regime gate",
            "- Applies uniformly to 'full', 'naive', and 'no_tilts' modes (a",
            "  portfolio-level overlay on top of whatever per-asset logic each",
            "  mode uses). This changes the headline numbers for all of",
            "  Strategy C's baselines slightly vs. earlier reports.",
            "- The gate fires rarely (it requires the BROAD market to be below",
            "  its own cash hurdle), so its effect on time-in-cash is small --",
            "  the Sharpe/MaxDD improvement should be read as a modest,",
            "  plausible refinement, not a major regime change.",
            "",
            "## Strategy D 'secret sauce' metrics",
            "- r2_lb (trend-smoothness R^2) uses a rolling linear-regression fit",
            "  of Close vs. time -- computationally heavier than the other",
            "  metrics but still O(n) per ticker via numpy.corrcoef.",
            "- frog_in_the_pan, the new best-Sharpe metric, is a SINGLE winning",
            "  combo out of 36 in a SHORT sample -- it has not been validated",
            "  out-of-sample or against a longer history, and should be treated",
            "  as a promising lead, not a conclusion.",
            "- None of the 36 combos reproduce the article's 16% CAGR while",
            "  keeping MaxDD shallower than -20% -- consistent with the earlier",
            "  finding that the article's headline figures likely reflect a much",
            "  longer sample and/or genuinely undisclosed ('proprietary')",
            "  parameters that cannot be recovered from this universe's data",
            "  history.",
            "",
            "## Validation status",
            "- All sweep dimensions (lookback, metric, regime filter) were",
            "  defined in the instruction spec BEFORE running the sweep -- not",
            "  tuned to results. A held-out / walk-forward split remains the",
            "  natural next step before treating any single combo (e.g.",
            "  frog_in_the_pan) as a live candidate.",
        ], fontsize=11)

    print(f"Wrote {REPORT_PATH}")


if __name__ == "__main__":
    main()
