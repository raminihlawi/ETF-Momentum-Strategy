"""
Generate a PDF report summarizing the Strategy A (Composite Momentum) and
Strategy B (Range/BLSH) validation work: final config, equity curves,
per-year performance, and the parameter/horizon sweeps already run.

Re-runs the current momentum_backtest.py CONFIG (18/12/6 horizons,
skip_recent_days=21) to produce the headline equity curve and per-year
table, then assembles that together with the PNGs already written to
sweep_results/ by momentum_sweep.py, momentum_horizon_sweep.py,
momentum_skip_sweep.py and range_blsh_sweep.py.

Output: report.pdf

Run: python generate_report.py
"""

import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import numpy as np
import pandas as pd

import price_db
import backtest_engine as engine
import momentum_backtest as mb

OUT_DIR = "sweep_results"
REPORT_PATH = "report.pdf"


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
    cfg = mb.CONFIG
    print("Loading data and running the current Strategy A config...")
    bench = price_db.load_prices(cfg["benchmark"], start=cfg["start"], end=cfg["end"]).dropna()
    universe = price_db.load_universe(cfg["segments"])
    tickers = [t for t, _, seg in universe if seg != "Index"]
    raw_data = mb.load_data(tickers, cfg["start"], cfg["end"])

    data = {t: mb.add_indicators(df.copy(), cfg) for t, df in raw_data.items()}
    regime_on = bench["Close"] > bench["Close"].rolling(cfg["regime_sma"]).mean()
    rebal_dates = mb.month_end_dates(bench.index)
    min_start = bench.index[max(cfg["horizons"].values()) + cfg["skip_recent_days"]]
    rebal_dates = rebal_dates[rebal_dates >= min_start]

    eq_a, log_a = mb.run_backtest(data, bench, regime_on, rebal_dates, cfg)
    stats_a = engine.perf_stats(eq_a, label=None, print_report=False)

    naive_cfg = dict(cfg, use_regime_gate=False, use_quality_filter=False,
                      use_banding=False, weighting="equal")
    eq_b, log_b = mb.run_backtest(data, bench, regime_on, rebal_dates, naive_cfg)
    stats_b = engine.perf_stats(eq_b, label=None, print_report=False)

    bh = engine.buy_and_hold(bench, cfg["starting_capital"]).reindex(eq_a.index).ffill()
    stats_bh = engine.perf_stats(bh, label=None, print_report=False)

    with PdfPages(REPORT_PATH) as pdf:
        # ---- Title / executive summary ----
        text_page(pdf, "Stockholm Momentum & Range/BLSH Strategy Validation", [
            "Generated report -- Strategy A (Composite Momentum) and Strategy B (Range/BLSH)",
            "Universe: 303 Stockholm Large/Mid/Small Cap names (today's index membership),",
            "benchmark ^OMX. Data: 2009-01 to 2026-06 (limited by ^OMX history on yfinance).",
            "",
            "## Executive summary",
            "- Strategy A (Composite Momentum) has a real, modest, broad edge over",
            "  2009-2026: with horizons=18/12/6 months and skip_recent_days=21 (the",
            "  academic '12-1' convention), 87% of 54 pre-specified parameter combos",
            "  beat buy & hold on Sharpe (median 0.64 vs 0.55), and the 'full' config",
            "  (regime gate + quality filter + inverse-vol + banding) beats the naive",
            "  equal-weight baseline (0.74 vs 0.57).",
            "- Universe was expanded from 99 to 303 names (97 Large / 123 Mid / 83 Small)",
            "  to better match the ~400 actual Large/Mid/Small Cap names on Nasdaq",
            "  Stockholm -- the prior 99-name universe under-represented Small Cap",
            "  (17 names) where momentum effects are often strongest. The expanded",
            "  universe gives very similar headline numbers (Sharpe 0.74 vs 0.75,",
            "  87% vs 100% of combos beating B&H) -- the earlier results were not an",
            "  artifact of a too-narrow universe.",
            "- The original spec default (3/6/12 months, skip=0) only beat buy & hold",
            "  on 4% of combos when tested on 2020-2026 data -- almost all of the gap to",
            "  Borslabbet's published 31.9% CAGR / 1.25 Sharpe (2001-2021) traces to",
            "  sample period, not a bug: 2020-2026 is one of the worst stretches for",
            "  momentum on record, and transaction costs eat most of the raw edge.",
            "- Strategy B (Range/BLSH) does NOT work as specified: all 27 sweep combos",
            "  had negative Sharpe, ~46% range-failure rate, and the entry trigger made",
            "  things WORSE than a no-trigger baseline. Shelved -- it's also the most",
            "  discretionary piece of the workflow, so a purely mechanical backtest is",
            "  of limited value there anyway.",
            "- HONEST CAVEATS that apply throughout: today's index membership (survivor-",
            "  ship bias), single full-sample runs (no held-out/walk-forward split yet),",
            "  and skip_recent_days=21 + the 18/12/6 horizon set were CHOSEN based on",
            "  this same sample -- a held-out test of the final config is the natural",
            "  next step.",
        ], fontsize=11)

        # ---- Strategy A: current config ----
        text_page(pdf, "Strategy A -- Current Configuration", [
            "## Config (momentum_backtest.py CONFIG)",
            f"- Horizons: {cfg['horizons']}  (18/12/6 months)",
            f"- skip_recent_days: {cfg['skip_recent_days']}  (12-1 convention)",
            f"- Quality filter (R^2, {cfg['r2_window']}d): bottom {cfg['quality_cutoff_pct']*100:.0f}% excluded",
            f"- Regime gate: benchmark close > {cfg['regime_sma']}-day SMA",
            f"- Selection: top {cfg['top_n']}, banding exit below top {cfg['band_exit_pct']*100:.0f}%",
            f"- Weighting: {cfg['weighting']}  |  Rebalance: monthly",
            f"- Liquidity: median {cfg['turnover_window']}d turnover >= {cfg['min_turnover_sek']:,.0f} SEK",
            f"- Costs: {cfg['cost_per_side']*100:.2f}% per side (commission + slippage)",
            "",
            "## Headline results (2009-01 to 2026-06)",
            f"{'':22s}{'CAGR':>8s}{'Sharpe':>9s}{'AnnVol':>9s}{'MaxDD':>9s}",
            f"{'Strategy A (full)':22s}{stats_a['cagr']*100:7.2f}%{stats_a['sharpe']:9.2f}"
            f"{stats_a['ann_vol']*100:8.2f}%{stats_a['max_dd']*100:8.2f}%",
            f"{'Naive baseline':22s}{stats_b['cagr']*100:7.2f}%{stats_b['sharpe']:9.2f}"
            f"{stats_b['ann_vol']*100:8.2f}%{stats_b['max_dd']*100:8.2f}%",
            f"{'Buy & hold ^OMX':22s}{stats_bh['cagr']*100:7.2f}%{stats_bh['sharpe']:9.2f}"
            f"{stats_bh['ann_vol']*100:8.2f}%{stats_bh['max_dd']*100:8.2f}%",
            "",
            f"Strategy A: {len(log_a)} rebalances, total cost {log_a['cost'].sum():,.0f} SEK "
            f"({log_a['cost'].sum()/cfg['starting_capital']*100:.1f}% of starting capital)",
            f"Naive:      {len(log_b)} rebalances, total cost {log_b['cost'].sum():,.0f} SEK "
            f"({log_b['cost'].sum()/cfg['starting_capital']*100:.1f}% of starting capital)",
        ], fontsize=11)

        # ---- Equity curve plot ----
        fig, ax = plt.subplots(figsize=(11, 7))
        ax.plot(eq_a.index, eq_a / eq_a.iloc[0], label="Strategy A (full)", lw=1.5)
        ax.plot(eq_b.index, eq_b / eq_b.iloc[0], label="Naive baseline", lw=1.5)
        ax.plot(bh.index, bh / bh.iloc[0], label="Buy & hold ^OMX", lw=1.5, color="black", ls="--")
        ax.set_yscale("log")
        ax.set_title("Growth of 1 (log scale), 2009-2026")
        ax.set_ylabel("Equity (normalized, log scale)")
        ax.legend()
        ax.grid(alpha=0.3, which="both")
        fig.tight_layout()
        pdf.savefig(fig)
        plt.close(fig)

        # ---- Per-year table ----
        years = sorted(set(eq_a.index.year))
        rows = []
        for y in years:
            row = {"Year": y}
            for name, eq in [("Strategy A", eq_a), ("Naive", eq_b), ("Buy & Hold", bh)]:
                grp = eq[eq.index.year == y]
                if len(grp) >= 2:
                    row[name] = f"{(grp.iloc[-1] / grp.iloc[0] - 1) * 100:.1f}%"
                else:
                    row[name] = "-"
            rows.append(row)
        table_df = pd.DataFrame(rows)

        fig, ax = plt.subplots(figsize=(8.5, 11))
        ax.axis("off")
        ax.set_title("Per-year returns", fontsize=14, fontweight="bold", pad=20)
        tbl = ax.table(cellText=table_df.values, colLabels=table_df.columns,
                        loc="center", cellLoc="center")
        tbl.auto_set_font_size(False)
        tbl.set_fontsize(11)
        tbl.scale(1, 1.6)
        pdf.savefig(fig)
        plt.close(fig)

        # ---- Sweep results (already-generated PNGs) ----
        image_page(pdf, os.path.join(OUT_DIR, "sharpe_heatmaps.png"))
        image_page(pdf, os.path.join(OUT_DIR, "distributions.png"))
        image_page(pdf, os.path.join(OUT_DIR, "horizon_comparison.png"))
        image_page(pdf, os.path.join(OUT_DIR, "skip_comparison.png"))

        # ---- Strategy B summary ----
        rsr_path = os.path.join(OUT_DIR, "range_sweep_results.csv")
        rfr_text = []
        if os.path.exists(rsr_path):
            rdf = pd.read_csv(rsr_path)
            rfr_text = [
                "## Sweep summary (27 combos: range_window x max_r2 x bottom_frac)",
                f"- Sharpe range: {rdf['sharpe'].min():.2f} to {rdf['sharpe'].max():.2f} "
                f"(median {rdf['sharpe'].median():.2f}) -- ALL NEGATIVE",
                f"- Median range-failure rate: {rdf['range_failure_rate'].median()*100:.1f}%",
                f"- 0% of combos beat buy & hold (Sharpe {stats_bh['sharpe']:.2f})",
            ]
        text_page(pdf, "Strategy B (Range/BLSH) -- Summary", [
            "Long-only mean-reversion: buy near the floor of an established trading",
            "range on a support-rejection trigger, target the range ceiling, hard",
            "stop below the floor.",
            "",
        ] + rfr_text + [
            "",
            "## Verdict",
            "- The B.3 entry trigger (support touch + bull rejection bar) made results",
            "  WORSE than a no-trigger baseline (buy any range-low candidate), contrary",
            "  to the spec's hypothesis.",
            "- ~46% range-failure rate is too high for 'relatively reliable' mean",
            "  reversion -- ranges in this universe/period break down too often.",
            "- This is treated as a real, useful negative result (per",
            "  PROJECT_SPEC.md's validation discipline), not a failed test.",
            "- Decision: SHELVED for now. Live use of B was always meant to layer the",
            "  user's discretionary price-action read on top of the mechanical trigger,",
            "  so a purely mechanical backtest has limited value here regardless.",
        ], fontsize=11)

        image_page(pdf, os.path.join(OUT_DIR, "range_sharpe_heatmaps.png"))
        image_page(pdf, os.path.join(OUT_DIR, "range_distributions.png"))

        # ---- Next steps ----
        text_page(pdf, "Next Steps", [
            "## Per PROJECT_SPEC.md Phase 1 (validation harness)",
            "- Held-out / walk-forward split: skip_recent_days=21 and the 18/12/6",
            "  horizon set were chosen by testing on the full 2009-2026 sample. The",
            "  honest next step is to fix this config, then run train/test (e.g. train",
            "  2009-2021, test 2022-2026 once) and rolling walk-forward windows to",
            "  confirm the plateau survives out-of-sample.",
            "",
            "## Known limitations to keep in view",
            "- Survivorship bias: universe = today's 303 Large/Mid/Small Cap names, not",
            "  point-in-time constituents.",
            "- ^OMX history starts 2008-11-20 on yfinance -- can't extend back to",
            "  Borslabbet's 2001 start without a different benchmark source.",
            "- Transaction costs are a major drag (Strategy A: ~50-65k SEK cumulative",
            "  cost on 100k starting capital over 17.5 years, ~150 rebalances). Worth",
            "  testing quarterly rebalancing to see if it preserves Sharpe at lower cost.",
            "",
            "## Strategy B, if revisited",
            "- Check whether range_ok is firing on genuinely range-bound names, or",
            "  mostly catching brief consolidations inside larger downtrends.",
            "- Otherwise: leave as a discretionary screener only (range_low_screener.py /",
            "  reversal_pattern_screener.py), per PROJECT_SPEC.md's own framing that B's",
            "  live use layers discretion on top of the mechanical trigger.",
        ], fontsize=11)

    print(f"Wrote {REPORT_PATH}")


if __name__ == "__main__":
    main()
