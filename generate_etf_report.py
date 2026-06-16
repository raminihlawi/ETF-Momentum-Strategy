"""
Generate a PDF report summarizing Strategy C (Multi-Asset ETF Dual-Momentum
Rotation) validation work: configuration, headline results vs. baselines,
equity curves, per-year performance, and the robustness sweep already run
by etf_sweep.py.

Re-runs the current etf_momentum_backtest.py CONFIG to produce the headline
equity curve and per-year table, then assembles that together with the PNGs
already written to etf_sweep_results/ by etf_sweep.py.

Output: etf_report.pdf

Run: python generate_etf_report.py
"""

import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import pandas as pd

import backtest_engine as engine
import etf_momentum_backtest as eb

OUT_DIR = "etf_sweep_results"
REPORT_PATH = "etf_report.pdf"


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
    cfg = eb.CONFIG
    universe_df = pd.read_csv(cfg["universe_csv"])
    blocks = dict(zip(universe_df["ticker"], universe_df["block"]))
    all_tickers = list(universe_df["ticker"])

    print("Loading price data and running current Strategy C config...")
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

    print("Running Strategy C (full)...")
    eq_c, log_c, dc_c = eb.run_backtest(data, blocks, all_dates, rebal_dates, cfg, mode="full")
    stats_c = engine.perf_stats(eq_c, label=None, print_report=False)

    print("Running baseline (a) Buy & Hold IWDA...")
    eq_a = engine.buy_and_hold(
        raw_data[eb.BASELINE_TICKER].loc[raw_data[eb.BASELINE_TICKER].index >= pd.Timestamp(cfg["start"])],
        cfg["starting_capital"]).reindex(all_dates).ffill()
    stats_a = engine.perf_stats(eq_a, label=None, print_report=False)

    print("Running baseline (b) Static 60/40...")
    eq_b, log_b = eb.run_static_alloc(data, all_dates, rebal_dates, cfg,
                                       weights={eb.BASELINE_TICKER: 0.6, eb.DEFENSIVE_TICKER: 0.4})
    stats_b = engine.perf_stats(eq_b, label=None, print_report=False)

    print("Running baseline (c) Naive relative momentum...")
    eq_cnv, log_cnv, dc_cnv = eb.run_backtest(data, blocks, all_dates, rebal_dates, cfg, mode="naive")
    stats_cnv = engine.perf_stats(eq_cnv, label=None, print_report=False)

    print("Running baseline (d) No sector/factor tilts...")
    eq_d, log_d, dc_d = eb.run_backtest(data, blocks, all_dates, rebal_dates, cfg, mode="no_tilts")
    stats_d = engine.perf_stats(eq_d, label=None, print_report=False)

    series = {
        "Strategy C (full)": (eq_c, stats_c, log_c, dc_c),
        "(a) Buy & Hold IWDA": (eq_a, stats_a, None, 0.0),
        "(b) Static 60/40": (eq_b, stats_b, log_b, 0.0),
        "(c) Naive relative momentum": (eq_cnv, stats_cnv, log_cnv, dc_cnv),
        "(d) No sector/factor tilts": (eq_d, stats_d, log_d, dc_d),
    }

    sweep_csv = os.path.join(OUT_DIR, "sweep_results.csv")
    sweep_df = pd.read_csv(sweep_csv) if os.path.exists(sweep_csv) else None

    with PdfPages(REPORT_PATH) as pdf:
        # ---- Title / executive summary ----
        sweep_lines = []
        if sweep_df is not None:
            sweep_lines = [
                f"- The 72-combo robustness sweep (lookback x hold_n x composite x",
                f"  abs-benchmark x max-per-block) shows a real plateau: median Sharpe "
                f"{sweep_df['sharpe'].median():.2f}",
                f"  (range {sweep_df['sharpe'].min():.2f}-{sweep_df['sharpe'].max():.2f}).",
                f"  {(sweep_df['sharpe'] > stats_b['sharpe']).mean()*100:.0f}% of combos beat"
                f" Static 60/40 on Sharpe, but only "
                f"{(sweep_df['sharpe'] > stats_a['sharpe']).mean()*100:.0f}% beat Buy & Hold"
                " IWDA -- lookback_days is by far the dominant knob (12m lookback gives"
                " noticeably higher Sharpe than 9m or 6m in this sample).",
            ]
        text_page(pdf, "Strategy C -- Multi-Asset ETF Dual-Momentum Rotation", [
            "Strategy C rotates monthly across a 26-ETF 'menu' into the top-ranked",
            "assets by trailing momentum, subject to an absolute-momentum (cash) gate,",
            "block diversification caps, and inverse-volatility weighting -- falling",
            "back to a defensive govt bond or cash when momentum is broadly weak.",
            "",
            "## Universe (26 tickers, 6 blocks)",
            "- Region (4): broad equity -- Europe, US, Pacific ex-Japan, Nordic (^OMX proxy)",
            "- Sector (9): S&P 500 GICS sectors (Tech, Health Care, Financials, Energy,",
            "  Industrials, Staples, Discretionary, Utilities, Materials, Communication)",
            "- Factor (5): Value, Quality, Momentum, Growth (EQQQ.L substitute), Min Vol",
            "- Emerging Markets (2): EM Asia, EM Latin America",
            "- Metals (2): Gold, Silver",
            "- Defensive bond (1, SEGA.L), Cash proxy (1, IBTS.L), Baseline B&H (1, IWDA.L)",
            "",
            "## Backtest period",
            f"- {cfg['start']} to 2026-06-15 (~6.7 years). This is SHORT and dominated",
            "  by a post-2020 bull market in global equities, with only one brief",
            "  drawdown (2022) as a real stress test. Results should be read as a",
            "  plausibility check, not a guarantee of edge across regimes.",
            "",
            "## Headline finding",
            f"- Strategy C (full) returned CAGR {stats_c['cagr']*100:.2f}% / Sharpe "
            f"{stats_c['sharpe']:.2f} / MaxDD {stats_c['max_dd']*100:.2f}% -- it beats",
            f"  Static 60/40 (Sharpe {stats_b['sharpe']:.2f}) and the naive momentum",
            f"  baseline (Sharpe {stats_cnv['sharpe']:.2f}) on risk-adjusted terms, but",
            f"  trails Buy & Hold IWDA (Sharpe {stats_a['sharpe']:.2f}) and the no-tilts",
            f"  variant (Sharpe {stats_d['sharpe']:.2f}) -- the sector/factor tilts did",
            "  not pay off over this short, equity-bull-dominated sample.",
        ] + sweep_lines, fontsize=10.5)

        # ---- Configuration page ----
        text_page(pdf, "Strategy C -- Current Configuration", [
            "## Config (etf_momentum_backtest.py CONFIG)",
            f"- Lookback: {cfg['lookback_days']} days  |  Composite (3/6/12m): {cfg['composite']}",
            f"- Absolute momentum gate: {cfg['abs_benchmark']}",
            f"- Hold N: {cfg['hold_n']}  |  Weighting: {cfg['weighting']} ({cfg['vol_window']}d vol window)",
            f"- Max per block: {cfg['max_per_block']}  (enabled: {cfg['use_max_per_block']})",
            f"- Rebalance: {cfg['rebal']}",
            f"- Costs: {cfg['cost_per_side']*100:.2f}% per side (commission + spread + slippage),"
            f" with PHAG.L override at {cfg['cost_per_side_overrides'].get('PHAG.L', 0)*100:.2f}%",
            "- TER drag applied daily per holding (0.07%-0.74% annualized by ETF)",
            "",
            "## Headline results (2019-10 to 2026-06)",
            f"{'':30s}{'CAGR':>8s}{'Sharpe':>9s}{'AnnVol':>9s}{'MaxDD':>9s}{'%Def/Cash':>11s}{'TotalCost':>11s}",
        ] + [
            f"{name:30s}{stats['cagr']*100:7.2f}%{stats['sharpe']:9.2f}"
            f"{stats['ann_vol']*100:8.2f}%{stats['max_dd']*100:8.2f}%{dc*100:10.1f}%"
            f"{(log['cost'].sum()/cfg['starting_capital']*100 if log is not None and not log.empty else 0.0):10.2f}%"
            for name, (eq, stats, log, dc) in series.items()
        ], fontsize=10.5)

        # ---- Equity curve plot ----
        fig, ax = plt.subplots(figsize=(11, 7))
        for name, (eq, stats, log, dc) in series.items():
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
        years = sorted(set(eq_c.index.year))
        rows = []
        for y in years:
            row = {"Year": y}
            for name, (eq, stats, log, dc) in series.items():
                grp = eq[eq.index.year == y]
                if len(grp) >= 2:
                    row[name] = f"{(grp.iloc[-1] / grp.iloc[0] - 1) * 100:.1f}%"
                else:
                    row[name] = "-"
            rows.append(row)
        table_df = pd.DataFrame(rows)
        # shorten column headers for the table
        short_names = {
            "Strategy C (full)": "Strategy C",
            "(a) Buy & Hold IWDA": "B&H IWDA",
            "(b) Static 60/40": "60/40",
            "(c) Naive relative momentum": "Naive",
            "(d) No sector/factor tilts": "No tilts",
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

        # ---- Sweep results (already-generated PNGs) ----
        image_page(pdf, os.path.join(OUT_DIR, "sharpe_distribution.png"))
        image_page(pdf, os.path.join(OUT_DIR, "dimension_effects.png"))

        # ---- Caveats / next steps ----
        text_page(pdf, "Honest Caveats & Next Steps", [
            "## Sample period",
            "- ~6.7 years (2019-10 to 2026-06) is short for a momentum/rotation",
            "  strategy. It includes only one real drawdown (2022 inflation/rate",
            "  shock) and is otherwise dominated by a strong global equity bull",
            "  market -- this favors Buy & Hold and penalizes defensive rotation.",
            "",
            "## Universe substitutions / data caveats (documented in",
            "## etf_momentum_backtest.py header)",
            "- DFNS.L (Defense sector) was DROPPED from the menu: data only from",
            "  2023-03-31, a severe outlier vs. the rest of the menu (~2014-2018),",
            "  and would have been a permanent no-op for ~95% of the backtest.",
            "- ^OMX (Nordic region) is an INDEX, not a tradable ETF -- used as an",
            "  untradeable proxy because no UCITS ETF with usable history was found.",
            "- EQQQ.L (Invesco EQQQ Nasdaq-100) is used as a substitute for the",
            "  'Growth' factor -- no clean MSCI World Growth-factor UCITS ETF exists",
            "  on yfinance.",
            "- IBTS.L (iShares USD Treasury 1-3yr) is used as the cash proxy -- the",
            "  truer 0-1yr proxy (IB01.L) only has data from 2019 and would force a",
            "  later backtest start date.",
            "",
            "## Implementation gaps",
            "- vol_target (per-asset risk-contribution cap) is NOT implemented --",
            "  CONFIG['vol_target'] is a TODO placeholder.",
            "",
            "## Validation status",
            "- All results above (including the 72-combo sweep) are SINGLE",
            "  full-sample runs. The sweep dimensions were chosen in advance (per",
            "  spec) and show a real plateau rather than one lucky peak, which is",
            "  reassuring -- but the chosen default CONFIG was still evaluated on",
            "  the full sample. A held-out / walk-forward split (e.g. train on an",
            "  earlier window, test on a later one) has NOT been done yet and is",
            "  the natural next step before relying on this strategy live.",
        ], fontsize=11)

    print(f"Wrote {REPORT_PATH}")


if __name__ == "__main__":
    main()
