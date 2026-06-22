"""
Phase 1 validation harness — does the pullback screen surface tradeable
setups that beat the baselines on out-of-sample data, after costs?

THE PROXY
The human's H2/H3 read can't be backtested directly. We use a MECHANICAL
PROXY: enter when a stock is in the screener's pullback zone (uptrend,
pulled back toward EMA20, room to run) AND today's close breaks above the
prior day's high (a crude stand-in for a Brooks H2 trigger bar). This almost
certainly UNDERESTIMATES a skilled discretionary entry, but it tests the
premise: are these "pullback zone" names actually good places to be long?

EXIT
Initial stop = entry - stop_atr_mult * ATR, then a ratcheting ATR chandelier
trail (reuses backtest_engine, same mechanics as trend_following_backtest.py).

REPORTS (per PROJECT_SPEC.md Phase 1)
  1. Full-period backtest (in-sample) vs two baselines: index buy & hold,
     and the existing trend-following backtest.
  2. A single held-out window, evaluated once.
  3. Walk-forward: rolling windows through time, default params.
  4. Parameter robustness sweep over the screen's key thresholds, reporting
     the full distribution (the "plateau"), not just the best config.

HONEST NOTES
  - Universe = today's Large/Mid/Small Cap list (price_db) -> survivorship
    bias still applies; see PROJECT_SPEC.md.
  - Costs are modeled (commission + slippage) but are estimates.
  - This sweeps a SMALL, theory-motivated grid decided in advance, and
    reports the whole distribution -- not an optimizer hunting for a peak.

Requires: pip install pandas numpy
Run:      python validate_pullback_strategy.py
"""

import itertools
import numpy as np
import pandas as pd

import price_db
import backtest_engine as engine


# ============================ CONFIG ============================
CONFIG = {
    "segments": ["Large", "Mid", "Small"],
    "benchmark": "^OMX",
    "full_start": "2020-01-01",
    "full_end": None,            # None = up to the latest data in the DB

    # Held-out final window, evaluated exactly once.
    "held_out_start": "2025-01-01",

    # Walk-forward windows (in-sample period only, before held_out_start).
    "wf_train_years": 2,
    "wf_test_months": 6,

    # --- indicator params (fixed, not swept) ---
    "ema_fast": 20,
    "ema_mid": 50,
    "sma_slow": 200,
    "atr_period": 20,
    "momentum_window": 90,
    "swing_high_lookback": 40,

    # --- default screen thresholds (center of the sweep grid) ---
    "min_pullback_atr": 0.5,
    "max_dist_above_ema20_atr": 1.5,
    "max_dist_below_ema20_atr": 0.75,
    "min_room_R": 1.5,
    "notional_stop_atr": 2.0,     # used for room-to-resistance calc

    # --- exit / portfolio (shared engine) ---
    "stop_atr_mult": 2.0,         # initial stop + chandelier trail, in ATRs
    "regime_sma": 200,
    "require_regime_on": True,
    "starting_capital": 100_000.0,
    "risk_per_trade": 0.0075,
    "max_positions": 20,
    "commission_pct": 0.0005,
    "slippage_pct": 0.0010,

    # --- robustness sweep grid (decided in advance, theory-motivated) ---
    "sweep_grid": {
        "min_pullback_atr": [0.25, 0.5, 0.75, 1.0],
        "max_dist_above_ema20_atr": [1.0, 1.5, 2.0],
        "min_room_R": [1.0, 1.5, 2.0],
    },
}


# ============================ INDICATORS ============================
def momentum_r2_series(close, window):
    """Rolling Clenow momentum (annualized exp-slope * R^2). No look-ahead:
    value at day d uses only closes up to and including d."""
    log_close = np.log(close.values)
    x = np.arange(window)
    x_mean = x.mean()
    x_var = ((x - x_mean) ** 2).sum()
    out = np.full(len(close), np.nan)
    for i in range(window - 1, len(close)):
        y = log_close[i - window + 1: i + 1]
        if np.any(~np.isfinite(y)):
            continue
        slope = ((x - x_mean) * (y - y.mean())).sum() / x_var
        intercept = y.mean() - slope * x_mean
        fit = slope * x + intercept
        ss_res = ((y - fit) ** 2).sum()
        ss_tot = ((y - y.mean()) ** 2).sum()
        r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0
        out[i] = (np.exp(slope * 252) - 1) * r2
    return pd.Series(out, index=close.index)


def compute_base_indicators(df, cfg):
    """Indicator columns that do NOT depend on the swept thresholds."""
    high, low, close = df["High"], df["Low"], df["Close"]
    prev_close = close.shift(1)
    tr = pd.concat([(high - low), (high - prev_close).abs(),
                    (low - prev_close).abs()], axis=1).max(axis=1)
    df["ATR"] = tr.rolling(cfg["atr_period"]).mean()

    df["EMA20"] = close.ewm(span=cfg["ema_fast"], adjust=False).mean()
    df["EMA50"] = close.ewm(span=cfg["ema_mid"], adjust=False).mean()
    df["SMA200"] = close.rolling(cfg["sma_slow"]).mean()
    df["EMA50_rising"] = df["EMA50"] > df["EMA50"].shift(21)

    # Recent swing high known at the close of day d (no look-ahead).
    df["recent_high"] = high.rolling(cfg["swing_high_lookback"]).max()
    df["prev_high"] = high.shift(1)

    df["momentum"] = momentum_r2_series(close, cfg["momentum_window"])

    df["uptrend"] = ((close > df["SMA200"]) & (df["EMA20"] > df["EMA50"]) &
                     df["EMA50_rising"] & (close > df["EMA50"]))
    df["pullback_atr"] = (df["recent_high"] - close) / df["ATR"]
    df["dist_ema20_atr"] = (close - df["EMA20"]) / df["ATR"]
    df["room_R"] = (df["recent_high"] - close) / (cfg["notional_stop_atr"] * df["ATR"])
    return df


def apply_threshold_signal(df, cfg):
    """Compute entry_signal for given threshold params. Cheap: no rolling ops."""
    close = df["Close"]
    pulled_back = df["pullback_atr"] >= cfg["min_pullback_atr"]
    near_value = ((df["dist_ema20_atr"] <= cfg["max_dist_above_ema20_atr"]) &
                   (df["dist_ema20_atr"] >= -cfg["max_dist_below_ema20_atr"]))
    has_room = df["room_R"] >= cfg["min_room_R"]
    pullback_zone = df["uptrend"] & pulled_back & near_value & has_room
    trigger = close > df["prev_high"]
    df["entry_signal"] = (pullback_zone & trigger).fillna(False)
    return df


# ============================ DATA LOADING ============================
def load_all(cfg):
    universe = price_db.load_universe(cfg["segments"])
    tickers = [t for t, _, seg in universe if seg != "Index"]
    bench = price_db.load_prices(cfg["benchmark"], start=cfg["full_start"], end=cfg["full_end"]).dropna()

    data = {}
    conn = price_db.get_connection()
    try:
        for t in tickers:
            df = price_db.load_prices(t, start=cfg["full_start"], end=cfg["full_end"], conn=conn)
            if df is None or len(df) < cfg["sma_slow"] + cfg["momentum_window"]:
                continue
            data[t] = compute_base_indicators(df.dropna(), cfg)
    finally:
        conn.close()
    return data, bench


# ============================ WINDOWED BACKTEST ============================
def run_window(data, bench, cfg, regime_on, start=None, end=None):
    """Run the pullback strategy (current cfg thresholds) over [start, end].

    `regime_on` is precomputed over the FULL benchmark history so the 200-day
    rolling average has enough lookback even when the window itself is short
    (e.g. a 6-month walk-forward test slice)."""
    windowed = {}
    for t, df in data.items():
        d = apply_threshold_signal(df.copy(), cfg)
        if start:
            d = d[d.index >= start]
        if end:
            d = d[d.index <= end]
        if d.empty:
            continue
        windowed[t] = d

    b = bench
    if start:
        b = b[b.index >= start]
    if end:
        b = b[b.index <= end]
    if b.empty or not windowed:
        return None, None

    return engine.run_backtest(windowed, b, cfg, regime_on=regime_on)


def report(equity, trades, bench, cfg, label):
    if equity is None or len(equity) < 2:
        print(f"\n=== {label} ===\n  (no data in this window)")
        return None
    strat = engine.perf_stats(equity, label)
    tstats = engine.trade_stats(trades)
    exposure = trades_exposure(trades, equity)
    print(f"  Trade count       : {tstats['n_trades']}")
    print(f"  Exposure          : {exposure*100:6.2f}%  (avg fraction of days with >=1 open position)")
    return {**strat, **tstats, "exposure": exposure}


def trades_exposure(trades, equity):
    if trades.empty:
        return 0.0
    days = equity.index
    open_days = pd.Series(False, index=days)
    for _, tr in trades.iterrows():
        mask = (days >= tr["entry_date"]) & (days <= tr["exit_date"])
        open_days |= mask
    return open_days.mean()


# ============================ WALK-FORWARD ============================
def walk_forward_windows(cfg, in_sample_end):
    start = pd.Timestamp(cfg["full_start"])
    end = pd.Timestamp(in_sample_end)
    train_delta = pd.DateOffset(years=cfg["wf_train_years"])
    test_delta = pd.DateOffset(months=cfg["wf_test_months"])

    windows = []
    train_start = start
    while True:
        train_end = train_start + train_delta
        test_end = train_end + test_delta
        if test_end > end:
            break
        windows.append((train_end, test_end))  # only the test window is run
        train_start = train_start + test_delta
    return windows


# ============================ SWEEP ============================
def run_sweep(data, bench, cfg, regime_on, start, end):
    grid = cfg["sweep_grid"]
    keys = list(grid.keys())
    rows = []
    for combo in itertools.product(*grid.values()):
        sweep_cfg = dict(cfg)
        sweep_cfg.update(dict(zip(keys, combo)))
        equity, trades = run_window(data, bench, sweep_cfg, regime_on, start=start, end=end)
        if equity is None or len(equity) < 2:
            continue
        strat = engine.perf_stats(equity, print_report=False)
        tstats = engine.trade_stats(trades, print_report=False)
        row = dict(zip(keys, combo))
        row.update({"cagr": strat["cagr"], "sharpe": strat["sharpe"],
                     "max_dd": strat["max_dd"], "n_trades": tstats["n_trades"],
                     "win_rate": tstats["win_rate"], "profit_factor": tstats["profit_factor"]})
        rows.append(row)
    return pd.DataFrame(rows)


# ============================ MAIN ============================
def main():
    cfg = CONFIG
    print("Loading data from price DB...")
    data, bench = load_all(cfg)
    print(f"  {len(data)} tickers loaded.")

    regime_on = (bench["Close"] > bench["Close"].rolling(cfg["regime_sma"]).mean())

    in_sample_end = pd.Timestamp(cfg["held_out_start"]) - pd.Timedelta(days=1)

    # ---------------------------------------------------------------
    print("\n" + "=" * 78)
    print("1) IN-SAMPLE FULL PERIOD vs BASELINES (default thresholds)")
    print("=" * 78)
    eq, tr = run_window(data, bench, cfg, regime_on, start=cfg["full_start"], end=in_sample_end)
    strat = report(eq, tr, bench, cfg, "PULLBACK STRATEGY (in-sample)")

    bench_is = bench[(bench.index >= cfg["full_start"]) & (bench.index <= in_sample_end)]
    bh = engine.buy_and_hold(bench_is, cfg["starting_capital"])
    base_bh = engine.perf_stats(bh, f"BASELINE: Buy & Hold {cfg['benchmark']} (in-sample)")

    print("\n  -- Baseline B (trend-following) --")
    print("  Run trend_following_backtest.py separately over the same period")
    print("  for the second baseline; see PROJECT_SPEC.md Phase 1.")

    # ---------------------------------------------------------------
    print("\n" + "=" * 78)
    print(f"2) HELD-OUT WINDOW (>= {cfg['held_out_start']}) -- evaluated once")
    print("=" * 78)
    eq_ho, tr_ho = run_window(data, bench, cfg, regime_on, start=cfg["held_out_start"], end=cfg["full_end"])
    strat_ho = report(eq_ho, tr_ho, bench, cfg, "PULLBACK STRATEGY (held-out)")

    bench_ho = bench[bench.index >= cfg["held_out_start"]]
    if not bench_ho.empty:
        bh_ho = engine.buy_and_hold(bench_ho, cfg["starting_capital"])
        engine.perf_stats(bh_ho, f"BASELINE: Buy & Hold {cfg['benchmark']} (held-out)")

    # ---------------------------------------------------------------
    print("\n" + "=" * 78)
    print("3) WALK-FORWARD (rolling test windows, default thresholds)")
    print(f"   train={cfg['wf_train_years']}y, test={cfg['wf_test_months']}m, "
          f"in-sample period ends {in_sample_end.date()}")
    print("=" * 78)
    windows = walk_forward_windows(cfg, in_sample_end)
    if not windows:
        print("  Not enough in-sample history for the configured window sizes.")
    for test_start, test_end in windows:
        eq_w, tr_w = run_window(data, bench, cfg, regime_on, start=test_start, end=test_end)
        label = f"WF test {test_start.date()} -> {test_end.date()}"
        if eq_w is None or len(eq_w) < 2:
            print(f"\n=== {label} ===\n  (no data)")
            continue
        strat_w = engine.perf_stats(eq_w, print_report=False)
        tstats_w = engine.trade_stats(tr_w, print_report=False)
        print(f"\n{label}")
        print(f"  CAGR {strat_w['cagr']*100:6.2f}%  Sharpe {strat_w['sharpe']:5.2f}  "
              f"MaxDD {strat_w['max_dd']*100:6.2f}%  Trades {tstats_w['n_trades']:4d}  "
              f"WinRate {tstats_w['win_rate']*100 if tstats_w['n_trades'] else float('nan'):5.1f}%")

    # ---------------------------------------------------------------
    print("\n" + "=" * 78)
    print("4) PARAMETER ROBUSTNESS SWEEP (in-sample period)")
    grid = cfg["sweep_grid"]
    n_combos = 1
    for v in grid.values():
        n_combos *= len(v)
    print(f"   grid: {grid}  ({n_combos} combinations)")
    print("=" * 78)
    sweep_df = run_sweep(data, bench, cfg, regime_on, cfg["full_start"], in_sample_end)
    if sweep_df.empty:
        print("  No combination produced trades.")
    else:
        pd.set_option("display.width", 160)
        print(sweep_df.sort_values("sharpe", ascending=False).to_string(index=False))
        print("\n  Distribution of Sharpe across the grid:")
        print(f"    min={sweep_df['sharpe'].min():.2f}  "
              f"median={sweep_df['sharpe'].median():.2f}  "
              f"max={sweep_df['sharpe'].max():.2f}")
        print("\n  A real edge looks like a PLATEAU (many neighboring configs with")
        print("  similar Sharpe), not a single spike surrounded by poor results.")

    # ---------------------------------------------------------------
    print("\n" + "=" * 78)
    print("VERDICT")
    print("=" * 78)
    if strat and base_bh:
        beat_is = strat["cagr"] > base_bh["cagr"]
        print(f"  In-sample: beat buy & hold CAGR?  {'YES' if beat_is else 'NO'}  "
              f"({strat['cagr']*100:.2f}% vs {base_bh['cagr']*100:.2f}%)")
    if strat_ho:
        print(f"  Held-out trade count: {strat_ho['n_trades']}  "
              f"Sharpe: {strat_ho['sharpe']:.2f}  CAGR: {strat_ho['cagr']*100:.2f}%")
    print("  Compare these numbers against trend_following_backtest.py's output")
    print("  for baseline (b). If the pullback proxy doesn't clearly beat both")
    print("  baselines risk-adjusted, after costs, on the held-out window, the")
    print("  premise isn't validated yet -- and that's a real, useful result.")


if __name__ == "__main__":
    main()
