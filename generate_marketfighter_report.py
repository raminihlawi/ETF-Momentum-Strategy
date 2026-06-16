"""
Generate a PDF report for Strategy D (Marketfighter replica): configuration,
headline results vs. baselines, equity curve, per-year performance, the
18-combo robustness sweep, and the "how is relative momentum determined"
selection-frequency exploration (both from marketfighter_sweep.py).

Re-runs the current marketfighter_replica.py CONFIG to produce the headline
equity curve and per-year table, then assembles that together with the PNGs
already written to marketfighter_sweep_results/ by marketfighter_sweep.py.

Output: marketfighter_report.pdf

Run: python generate_marketfighter_report.py
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

OUT_DIR = "marketfighter_sweep_results"
REPORT_PATH = "marketfighter_report.pdf"


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
    """Embed a PNG at full page width, preserving its aspect ratio (the PNGs
    already carry their own titles)."""
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


def main():
    cfg = mf.CONFIG
    universe_df = pd.read_csv(cfg["universe_csv"])
    all_tickers = list(universe_df["ticker"])

    print("Loading price data and running current Strategy D config...")
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

    print("Running Strategy D (Marketfighter replica)...")
    eq_d, log_d, cf_d = mf.run_backtest(data, all_dates, rebal_dates, cfg)
    stats_d = engine.perf_stats(eq_d, label=None, print_report=False)

    print("Running baseline (a) Buy & Hold IWDA...")
    eq_a = engine.buy_and_hold(
        raw_data[eb.BASELINE_TICKER].loc[raw_data[eb.BASELINE_TICKER].index >= pd.Timestamp(cfg["start"])],
        cfg["starting_capital"]).reindex(all_dates).ffill()
    stats_a = engine.perf_stats(eq_a, label=None, print_report=False)

    print("Running baseline (b) Static 60/40...")
    eq_b, log_b = eb.run_static_alloc(data, all_dates, rebal_dates, cfg,
                                       weights={eb.BASELINE_TICKER: 0.6, eb.DEFENSIVE_TICKER: 0.4})
    stats_b = engine.perf_stats(eq_b, label=None, print_report=False)

    print("Running reference: Strategy C (full)...")
    blocks = dict(zip(universe_df["ticker"], universe_df["block"]))
    cfg_c = dict(eb.CONFIG)
    eq_c, log_c, cf_c = eb.run_backtest(data, blocks, all_dates, rebal_dates, cfg_c, mode="full")
    stats_c = engine.perf_stats(eq_c, label=None, print_report=False)

    series = {
        "Strategy D (Marketfighter replica)": (eq_d, stats_d, log_d, cf_d),
        "(a) Buy & Hold IWDA": (eq_a, stats_a, None, 0.0),
        "(b) Static 60/40": (eq_b, stats_b, log_b, 0.0),
        "Strategy C (full, reference)": (eq_c, stats_c, log_c, cf_c),
    }

    sweep_csv = os.path.join(OUT_DIR, "sweep_results.csv")
    sweep_df = pd.read_csv(sweep_csv) if os.path.exists(sweep_csv) else None

    with PdfPages(REPORT_PATH) as pdf:
        # ---- Title / executive summary ----
        sweep_lines = []
        if sweep_df is not None:
            frac_beat_bh = (sweep_df["sharpe"] > stats_a["sharpe"]).mean()
            best_row = sweep_df.loc[sweep_df["sharpe"].idxmax()]
            sweep_lines = [
                "",
                "## Robustness sweep (18 combos: lookback x momentum_metric x regime_filter)",
                f"- Sharpe ranges {sweep_df['sharpe'].min():.2f}-{sweep_df['sharpe'].max():.2f}"
                f" (median {sweep_df['sharpe'].median():.2f}); only "
                f"{frac_beat_bh*100:.0f}% of combos beat Buy & Hold IWDA"
                f" (Sharpe {stats_a['sharpe']:.2f}) on Sharpe.",
                "- 'momentum_metric' and 'lookback_days' both have a real effect"
                " (composite scoring and 252d lookback do best); the regime"
                " filter mostly affects variance rather than the median.",
                f"- Best combo: lookback={int(best_row['lookback_days'])}d, "
                f"metric={best_row['momentum_metric']}, regime_filter="
                f"{best_row['use_regime_filter']} -> Sharpe {best_row['sharpe']:.2f}, "
                f"CAGR {best_row['cagr']*100:.2f}%, MaxDD {best_row['max_dd']*100:.2f}%.",
            ]
        text_page(pdf, "Strategy D -- 'Marketfighter' Replica", [
            "A replica of the two-sleeve dual-momentum strategy described in",
            "https://www.marketfighter.com/p/my-investment-approach-that-outperformed",
            "(exact parameters not published -- 'proprietary'). Each month: hold",
            "50% in the single FACTOR ETF with the best trailing momentum (Value,",
            "Quality, Momentum, Size), and 50% in the single SECTOR ETF with the",
            "best trailing momentum (10 GICS sectors). The whole portfolio moves",
            "to cash when a market-level absolute-momentum regime filter is off.",
            "",
            "## THIS IS NOT THE PUBLISHED STRATEGY",
            "- The article gives the mechanism but not the exact lookback, ticker",
            "  universe, or regime-filter rule -- those are 'proprietary'. This is",
            "  a documented, honest interpretation of the described mechanism, not",
            "  a verified reproduction. The article's headline 16-20% CAGR claims",
            "  (2000-2025 / 2016-2025) cover a ~20-26 year period; our backtest",
            f"  window ({cfg['start']} to 2026-06-15, ~6.7 years) is far shorter and",
            "  cannot be compared apples-to-apples.",
            "",
            "## Headline result (default config: 252d lookback, raw momentum,",
            "## regime filter ON)",
            f"- Strategy D returned CAGR {stats_d['cagr']*100:.2f}% / Sharpe "
            f"{stats_d['sharpe']:.2f} / MaxDD {stats_d['max_dd']*100:.2f}%, in cash "
            f"{cf_d*100:.1f}% of days.",
            f"- It beats Static 60/40 (Sharpe {stats_b['sharpe']:.2f}) and is"
            f" roughly on par with Strategy C (Sharpe {stats_c['sharpe']:.2f}),"
            f" but trails Buy & Hold IWDA (Sharpe {stats_a['sharpe']:.2f}) -- the"
            " top-1-per-sleeve mechanism takes much less drawdown (-18.3% vs"
            " -34.1%) at the cost of some upside in this bull-dominated sample.",
        ] + sweep_lines, fontsize=10.5)

        # ---- Configuration page ----
        text_page(pdf, "Strategy D -- Current Configuration", [
            "## Mechanism",
            "- Factor sleeve (50%): best 12m-momentum ETF among IWVL.L (Value),",
            "  IWQU.L (Quality), IWMO.L (Momentum), WSML.L (Size proxy)",
            "- Sector sleeve (50%): best 12m-momentum ETF among the 10 S&P 500",
            "  GICS sector UCITS ETFs (IITU.L, IUHC.L, IUFS.L, IUES.L, IUIS.L,",
            "  IUCS.L, IUCD.L, IUUS.L, IUMS.L, IUCM.L)",
            "- No within-sleeve weighting beyond 100% concentration in the single",
            "  top-ranked asset, as described in the article -- high single-asset",
            "  concentration risk per sleeve, by design.",
            "",
            "## Config (marketfighter_replica.py CONFIG)",
            f"- Lookback: {cfg['lookback_days']} days",
            f"- Absolute momentum / regime gate: {cfg['abs_benchmark']}"
            f" (IWDA.L vs {eb.CASH_TICKER}, applied to the WHOLE portfolio)",
            f"- Rebalance: {cfg['rebal']}",
            f"- Costs: {cfg['cost_per_side']*100:.2f}% per side (commission + spread"
            f" + slippage)",
            "- TER drag applied daily per holding",
            "",
            "## Headline results (2019-10 to 2026-06)",
            f"{'':36s}{'CAGR':>8s}{'Sharpe':>9s}{'AnnVol':>9s}{'MaxDD':>9s}{'%Cash':>8s}{'TotalCost':>11s}",
        ] + [
            f"{name:36s}{stats['cagr']*100:7.2f}%{stats['sharpe']:9.2f}"
            f"{stats['ann_vol']*100:8.2f}%{stats['max_dd']*100:8.2f}%{cf*100:7.1f}%"
            f"{(log['cost'].sum()/cfg['starting_capital']*100 if log is not None and not log.empty else 0.0):10.2f}%"
            for name, (eq, stats, log, cf) in series.items()
        ], fontsize=10.5)

        # ---- Equity curve plot ----
        fig, ax = plt.subplots(figsize=(11, 7))
        for name, (eq, stats, log, cf) in series.items():
            ls = "--" if name.startswith("(a)") else "-"
            color = "black" if name.startswith("(a)") else None
            ax.plot(eq.index, eq / eq.iloc[0], label=name, lw=1.5, ls=ls, color=color)
        ax.set_yscale("log")
        ax.set_title("Growth of 1 (log scale), 2019-10 to 2026-06")
        ax.set_ylabel("Equity (normalized, log scale)")
        ax.legend(fontsize=9)
        ax.grid(alpha=0.3, which="both")
        fig.tight_layout()
        pdf.savefig(fig)
        plt.close(fig)

        # ---- Per-year table ----
        years = sorted(set(eq_d.index.year))
        rows = []
        for y in years:
            row = {"Year": y}
            for name, (eq, stats, log, cf) in series.items():
                grp = eq[eq.index.year == y]
                if len(grp) >= 2:
                    row[name] = f"{(grp.iloc[-1] / grp.iloc[0] - 1) * 100:.1f}%"
                else:
                    row[name] = "-"
            rows.append(row)
        table_df = pd.DataFrame(rows)
        short_names = {
            "Strategy D (Marketfighter replica)": "Strategy D",
            "(a) Buy & Hold IWDA": "B&H IWDA",
            "(b) Static 60/40": "60/40",
            "Strategy C (full, reference)": "Strategy C",
        }
        table_df = table_df.rename(columns=short_names)

        fig, ax = plt.subplots(figsize=(8.5, 11))
        ax.axis("off")
        ax.set_title("Per-year returns", fontsize=14, fontweight="bold", pad=20)
        tbl = ax.table(cellText=table_df.values, colLabels=table_df.columns,
                        loc="center", cellLoc="center")
        tbl.auto_set_font_size(False)
        tbl.set_fontsize(10)
        tbl.scale(1, 1.6)
        pdf.savefig(fig)
        plt.close(fig)

        # ---- Sweep results + selection-frequency (already-generated PNGs) ----
        image_page(pdf, os.path.join(OUT_DIR, "sharpe_distribution.png"))
        image_page(pdf, os.path.join(OUT_DIR, "dimension_effects.png"))

        text_page(pdf, "How Is 'Relative Momentum' Determined?", [
            "The article describes choosing the ETF with the 'best trailing",
            "momentum (e.g. 12 months)' but does not specify exactly how that",
            "score is computed. We tried three common definitions:",
            "",
            "## Metric definitions",
            "- raw: trailing total return over the lookback window (the article's",
            "  literal description)",
            "- risk_adjusted: trailing return / 126-day realized volatility (a",
            "  common 'risk-adjusted momentum' variant)",
            "- composite: average percentile rank of 3m/6m/12m returns (the",
            "  ranking method used in Strategy C)",
            "",
            "## Finding",
            "- The choice of metric materially changes BOTH performance (Sharpe",
            "  0.80 / 0.86 / 0.92 for raw / risk_adjusted / composite at 252d,",
            "  regime ON) AND which ETFs get selected each month.",
            "- Factor sleeve: risk_adjusted favors Value/Quality (IWVL.L, IWQU.L)",
            "  over Momentum (IWMO.L), while raw and composite lean more on",
            "  IWMO.L. WSML.L (Size proxy) is rarely picked under any metric.",
            "- Sector sleeve: raw and risk_adjusted concentrate heavily into",
            "  IUCM.L (Communications, ~20-32% of months); composite spreads more",
            "  evenly across IITU.L (Tech), IUCM.L and others.",
            "- Composite ranking is both the best-performing and the most",
            "  diversified across selections in this sample -- it looks like the",
            "  more defensible choice when the article's own definition is",
            "  ambiguous.",
            "",
            "See the next page for the full selection-frequency breakdown by",
            "metric (lookback=252d, regime filter ON).",
        ], fontsize=11)
        image_page(pdf, os.path.join(OUT_DIR, "selection_frequency.png"))

        # ---- Caveats / next steps ----
        text_page(pdf, "Honest Caveats & Next Steps", [
            "## This is a replica, not the published strategy",
            "- The article's exact lookback window, ticker universe, scoring",
            "  formula, and regime-filter rule are 'proprietary' and not published.",
            "  Every concrete choice here (252d lookback, IWVL/IWQU/IWMO/WSML as the",
            "  factor menu, the 10 GICS sector ETFs, the IWDA.L vs IBTS.L regime",
            "  gate) is a documented choice made for THIS replica, not the author's.",
            "",
            "## Sample period",
            f"- ~6.7 years ({cfg['start']} to 2026-06-15), same short window as",
            "  Strategy C, for the same data-availability reasons. The article's",
            "  headline 16-20% CAGR figures cover 2000-2025 / 2016-2025 -- a much",
            "  longer period that cannot be replicated with this universe's data",
            "  history. Any comparison to those figures is not apples-to-apples.",
            "",
            "## Universe substitutions / data caveats",
            "- WSML.L (iShares MSCI World Small Cap) is used as the 'Size factor'",
            "  proxy -- not a pure Size-factor index fund, but the closest",
            "  available on yfinance (data from 2018-03-27).",
            "- Same IBTS.L cash-proxy and IWDA.L baseline substitutions as",
            "  Strategy C (see etf_momentum_backtest.py header).",
            "",
            "## Concentration risk",
            "- 100% concentration in a single ETF per sleeve (as described in the",
            "  article) means each rebalance carries meaningful single-asset risk",
            "  -- by design of the replicated mechanism, not a bug.",
            "",
            "## Validation status",
            "- The 18-combo sweep (lookback x momentum_metric x regime_filter) was",
            "  chosen in advance per the project's validation discipline and shows",
            "  composite scoring + 252d lookback as a consistent improvement, not",
            "  a lucky peak. A held-out / walk-forward split has NOT been done yet",
            "  and remains the natural next step before relying on this strategy",
            "  live.",
        ], fontsize=11)

    print(f"Wrote {REPORT_PATH}")


if __name__ == "__main__":
    main()
