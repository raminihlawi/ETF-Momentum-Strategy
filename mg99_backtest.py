"""
MG99 strategy implementation and head-to-head comparison with FITP
(frog_in_the_pan, 252d, regime ON).

MG99 rules (from ETF Strategy app spec):
  - Score    : 12m return * R² (ret_252 * r2_252)
  - Eligible : score > 0 only
  - Selection: top-3, max 1 per block category (region/sector/factor/em/metal)
  - Weighting: equal (1/3 each, or 1/n if fewer than 3 pass)
  - Rebalance: monthly (same as FITP for fair comparison)
  - Regime   : IWDA.L Close < SMA-200 → 100% safe haven (SEGA.L)
  - Stop-loss: ATR(22) trailing stop, multiplier 2.5
               peak_price updated to highest High since entry
               stop = peak_price - ATR(22) * 2.5
               triggered when Close < stop (sell at close of that day)
  - Universe : all risk-role tickers from etf_universe.csv
               (incl. regions, sectors, factors, EM, metals)

FITP rules (our best config):
  - Score    : sign(ret_252) * (n_up - n_down) / 252 (frog_in_the_pan)
  - Selection: top-1 in factor sleeve + top-1 in sector sleeve
  - Weighting: 50%/50%
  - Rebalance: monthly
  - Regime   : IWDA.L ret_252 <= IBTS.L ret_252 → 100% cash (IBTS.L)
  - Stop-loss: none

Both: 0.15% per side transaction costs, TER-adjusted prices.

Outputs:
  - Printed stats table
  - mg99_vs_fitp_results/equity_curve.png
"""

import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import backtest_engine as engine
import etf_momentum_backtest as eb
import marketfighter_replica as mf
import marketfighter_sweep2 as mf2

OUT_DIR = "mg99_vs_fitp_results"
ATR_WINDOW   = 22
ATR_MULT     = 2.5
SAFE_HAVEN   = "SEGA.L"      # defensive govt bond


# ============================ ATR ============================
def add_atr(df, window=ATR_WINDOW):
    h, l, c = df["High"], df["Low"], df["Close"]
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    df[f"atr{window}"] = tr.rolling(window).mean()
    return df


def add_sma200(df):
    df["sma200"] = df["Close"].rolling(200).mean()
    return df


# ============================ MG99 BACKTEST ============================
def run_mg99(data, raw_data, universe_df, all_dates, rebal_dates, cfg):
    """MG99 strategy: r2_adjusted scoring, top-3 max-1-per-block, SMA200
    regime filter, ATR(22) trailing stop, monthly rebalance, equal weight."""
    blocks  = dict(zip(universe_df["ticker"], universe_df["block"]))
    roles   = dict(zip(universe_df["ticker"], universe_df["role"]))
    risk_tickers = [t for t, r in roles.items()
                    if r == "risk" and t in data and t != "^OMX"]

    cash_bal  = cfg["starting_capital"]
    shares    = {}
    peak_px   = {}
    entry_d   = {}
    equity_curve = []
    rebal_log = []
    pending   = None
    rebal_set = set(rebal_dates)

    for d in all_dates:
        # ---- 1. Execute pending rebalance AT OPEN (signal from prior close) ----
        if pending is not None:
            value = cash_bal
            open_px = {}
            for t in set(list(shares.keys()) + list(pending.keys())):
                df_t = data[t]
                if d in df_t.index:
                    open_px[t] = df_t.loc[d, "Open"]
                else:
                    open_px[t] = df_t["Close"].reindex(all_dates).ffill().loc[d]
            for t in shares:
                value += shares[t] * open_px.get(t, 0.0)

            new_shares = {}
            for t, w in pending.items():
                px = open_px.get(t)
                if px and not np.isnan(px) and px > 0:
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
            # reset peak tracking for freshly entered positions
            for t in new_shares:
                if shares.get(t, 0.0) == 0.0:
                    peak_px[t] = open_px.get(t, 0.0)
            shares = new_shares
            rebal_log.append((d, "rebal", cost))
            pending = None

        # ---- 2. ATR stop-loss check AT CLOSE (after open execution) ----
        stop_sells = {}
        for t, sh in list(shares.items()):
            if t == SAFE_HAVEN:
                continue
            df_t = data[t]
            atr_col = f"atr{ATR_WINDOW}"
            if d not in df_t.index or pd.isna(df_t.loc[d, atr_col]):
                continue
            curr_high  = df_t.loc[d, "High"]
            curr_close = df_t.loc[d, "Close"]
            atr_val    = df_t.loc[d, atr_col]
            peak_px[t] = max(peak_px.get(t, curr_high), curr_high)
            stop_level = peak_px[t] - atr_val * ATR_MULT
            if curr_close < stop_level:
                stop_sells[t] = curr_close  # sell at today's close

        for t, px in stop_sells.items():
            proceeds = shares[t] * px
            rate = cfg["cost_per_side_overrides"].get(t, cfg["cost_per_side"])
            cost = proceeds * rate
            cash_bal += proceeds - cost
            del shares[t]
            peak_px.pop(t, None)
            rebal_log.append((d, f"stop_{t}", cost))

        # ---- 3. Mark to market at close ----
        held = 0.0
        for t, sh in shares.items():
            df_t = data[t]
            if d in df_t.index:
                px = df_t.loc[d, "Close"]
            else:
                px = df_t["Close"].reindex(all_dates).ffill().loc[d]
            held += sh * px
        equity_curve.append((d, cash_bal + held))

        # ---- 4. Rebalance signal at month-end close ----
        if d in rebal_set:
            # regime: IWDA.L close vs SMA200
            iwda_df = data[eb.BASELINE_TICKER]
            bear = False
            if d in iwda_df.index and not pd.isna(iwda_df.loc[d, "sma200"]):
                bear = iwda_df.loc[d, "Close"] < iwda_df.loc[d, "sma200"]

            if bear:
                pending = {SAFE_HAVEN: 1.0}
                continue

            # score = ret_lb * r2_lb, filter score > 0
            rows = {}
            for t in risk_tickers:
                df_t = data[t]
                if d not in df_t.index:
                    continue
                row = df_t.loc[d]
                ret = row.get("ret_lb", np.nan)
                r2  = row.get("r2_lb",  np.nan)
                if np.isnan(ret) or np.isnan(r2):
                    continue
                score = ret * r2
                if score > 0:
                    rows[t] = {"score": score, "block": blocks.get(t, "")}
            if not rows:
                pending = {}
                continue

            scored = pd.DataFrame(rows).T.sort_values("score", ascending=False)
            selected = []
            used_blocks = {}
            for t, row in scored.iterrows():
                if len(selected) >= 3:
                    break
                blk = row["block"]
                if used_blocks.get(blk, 0) >= 1:
                    continue
                selected.append(t)
                used_blocks[blk] = used_blocks.get(blk, 0) + 1

            if not selected:
                pending = {}
                continue
            w = 1.0 / len(selected)
            pending = {t: w for t in selected}

    eq = pd.Series({d: v for d, v in equity_curve}).sort_index()
    log_df = pd.DataFrame(rebal_log, columns=["date", "type", "cost"])
    return eq, log_df


# ============================ FITP BACKTEST ============================
def run_fitp(data, all_dates, rebal_dates, cfg):
    """FITP = frog_in_the_pan, 252d, regime ON (IWDA vs IBTS cash proxy)."""
    cfg_fitp = dict(cfg, lookback_days=252, composite=True)
    eq, log, _, _ = mf2.run_backtest(data, all_dates, rebal_dates,
                                      cfg_fitp, metric="frog_in_the_pan",
                                      use_regime_filter=True)
    return eq, log


# ============================ MAIN ============================
def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    cfg = dict(mf.CONFIG)
    universe_df = pd.read_csv(cfg["universe_csv"])
    all_tickers = list(universe_df["ticker"])

    print("Loading price data...")
    raw_data = eb.load_data(all_tickers, start="2005-01-01", end=cfg["end"], cfg=cfg)
    ter_data = eb.build_ter_adjusted_data(raw_data, cfg)

    print("Computing indicators...")
    cfg_lb = dict(cfg, lookback_days=252, composite=True)
    data = {}
    for t, df in ter_data.items():
        d = eb.add_indicators(df.copy(), cfg_lb)
        d = mf.add_secret_sauce_indicators(d, cfg_lb)
        d = add_atr(d)
        d = add_sma200(d)
        data[t] = d.loc[d.index >= pd.Timestamp(cfg["start"])]

    all_dates = data[eb.BASELINE_TICKER].index
    rebal_dates = eb.month_end_dates(all_dates)
    # warmup: need 252d for r2/ret, 200d for SMA200, 22d for ATR
    warmup = max(252, 200, ATR_WINDOW)
    rebal_dates = rebal_dates[rebal_dates >= all_dates[warmup]]

    print(f"  Backtest: {all_dates[0].date()} -> {all_dates[-1].date()}, "
          f"{len(rebal_dates)} rebalances\n")

    print("Running MG99...")
    eq_mg99, log_mg99 = run_mg99(data, raw_data, universe_df, all_dates, rebal_dates, cfg)
    stats_mg99 = engine.perf_stats(eq_mg99, label=None, print_report=False)

    print("Running FITP (frog_in_the_pan, 252d, regime ON)...")
    eq_fitp, log_fitp = run_fitp(data, all_dates, rebal_dates, cfg)
    stats_fitp = engine.perf_stats(eq_fitp, label=None, print_report=False)

    print("Running baseline Buy & Hold IWDA...")
    eq_bh = engine.buy_and_hold(
        raw_data[eb.BASELINE_TICKER].loc[
            raw_data[eb.BASELINE_TICKER].index >= pd.Timestamp(cfg["start"])],
        cfg["starting_capital"]).reindex(all_dates).ffill()
    stats_bh = engine.perf_stats(eq_bh, label=None, print_report=False)

    # ---- results table ----
    cost_mg99 = log_mg99["cost"].sum()
    cost_fitp = log_fitp["cost"].sum() if hasattr(log_fitp, "cost") else log_fitp["cost"].sum()

    print("\n" + "=" * 90)
    print(f"{'Strategy':<38} {'CAGR':>7} {'Sharpe':>7} {'AnnVol':>7} "
          f"{'MaxDD':>8} {'TotalCost':>10}")
    print("-" * 90)
    for name, stats, cost in [
        ("MG99 (r2*ret, SMA200, ATR stop)", stats_mg99, cost_mg99),
        ("FITP (frog_in_pan, 252d, ON)",    stats_fitp, cost_fitp),
        ("Buy & Hold IWDA",                 stats_bh,   0.0),
    ]:
        print(f"{name:<38} {stats['cagr']*100:6.2f}% {stats['sharpe']:7.2f} "
              f"{stats['ann_vol']*100:6.2f}% {stats['max_dd']*100:7.2f}% "
              f"{cost/cfg['starting_capital']*100:9.2f}%")
    print("=" * 90)

    # ---- per-year table ----
    print("\nPer-year returns:")
    print(f"{'Year':<6} {'MG99':>8} {'FITP':>8} {'B&H IWDA':>10}")
    for yr in sorted(set(eq_mg99.index.year)):
        def yr_ret(eq):
            g = eq[eq.index.year == yr]
            return (g.iloc[-1]/g.iloc[0]-1)*100 if len(g) >= 2 else float("nan")
        print(f"{yr:<6} {yr_ret(eq_mg99):7.1f}% {yr_ret(eq_fitp):7.1f}% {yr_ret(eq_bh):9.1f}%")

    # ---- equity curve plot ----
    fig, ax = plt.subplots(figsize=(12, 6))
    for label, eq, ls, lw in [
        ("MG99 (r2*ret, SMA200, ATR stop)", eq_mg99, "-",  1.8),
        ("FITP (frog_in_pan, 252d, ON)",    eq_fitp, "-",  1.8),
        ("Buy & Hold IWDA",                 eq_bh,   "--", 1.5),
    ]:
        ax.plot(eq.index, eq / eq.iloc[0], label=label, lw=lw, ls=ls)
    ax.set_yscale("log")
    ax.set_title("MG99 vs FITP vs Buy & Hold IWDA — growth of 1 (log scale, 2019-10 to 2026-06)")
    ax.set_ylabel("Equity (normalized, log scale)")
    ax.legend(fontsize=10)
    ax.grid(alpha=0.3, which="both")
    fig.tight_layout()
    path = os.path.join(OUT_DIR, "equity_curve.png")
    fig.savefig(path, dpi=130)
    plt.close(fig)
    print(f"\nWrote {path}")


if __name__ == "__main__":
    main()
