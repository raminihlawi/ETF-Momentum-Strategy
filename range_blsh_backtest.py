"""
Strategy B — Range / BLSH (buy low in a range), per STRATEGY_SPEC.md section 2.

A long-only mean-reversion strategy: identify an established trading range
(flat slope, low R^2, tested support, established floor), wait for a
support-rejection trigger bar, buy the next open, and target the range
ceiling with a hard stop below the floor.

Two variants are run:
  - TRIGGER strategy: full B.3 entry trigger (support touch + bull
    rejection bar).
  - NO-TRIGGER baseline: buy any range-low candidate (B.1+B.2) without the
    B.3 trigger, same stop/target/sizing -- to test whether the trigger
    actually improves reliability.

Timing convention (no look-ahead), matching backtest_engine.py:
  - Signals computed at the CLOSE of day d.
  - Entries fill at the OPEN of day d+1 (or, for ENTRY_MODE=stop_above_signal,
    only if day d+1's high takes out day d's high -- fill at that level).
  - Stop / target are checked against day d+1's Low/High.
  - "Close < floor" (range failure) and the time stop are detected at a
    day's close and executed at the next day's open.

HONEST CAVEATS
- Survivorship bias: universe is today's index membership (PROJECT_SPEC.md).
- "Tested support" (local-minima counting) is computed with a plain Python
  loop per ticker -- correct but not fast; fine for a ~6 year / ~100-ticker
  universe.
- This is a first validation pass: one full-sample run plus the no-trigger
  baseline and the range-failure-rate diagnostic. The B.7 parameter sweep is
  in range_blsh_sweep.py.

Requires: pip install pandas numpy
Data:     reads from stockholm_ohlc.sqlite3 (build/update with build_price_db.py)
Run:      python range_blsh_backtest.py
"""

import math

import numpy as np
import pandas as pd

import price_db
import backtest_engine as engine


# ============================ CONFIG ============================
CONFIG = {
    # --- universe & period ---
    "segments": ["Large", "Mid", "Small"],
    "benchmark": "^OMX",
    "start": "2020-01-01",
    "end": None,

    # --- range identification (B.1) ---
    "range_window": 50,
    "max_abs_slope": 0.25,        # |annualized log-price regression slope|
    "max_r2": 0.35,               # R^2 of that regression (choppy = low R^2)
    "min_width_atr": 4.0,         # (ceiling - floor) >= this * ATR(20)
    "atr_period": 20,
    "support_established_bars": 6,
    "support_band_atr": 0.75,
    "min_touches": 2,

    # --- low-in-range (B.2) ---
    "bottom_frac": 0.30,

    # --- entry trigger (B.3) ---
    "entry_mode": "next_open",    # "next_open" | "stop_above_signal"

    # --- stop / target / time stop (B.4, B.5) ---
    "stop_buffer_atr": 0.5,
    "max_hold_bars": 30,

    # --- sizing (B.6) ---
    "risk_per_trade": 0.0075,     # 0.75% of equity risked per trade
    "max_positions": 20,

    # --- liquidity ---
    "min_turnover_sek": 20_000_000,
    "turnover_window": 20,

    # --- frictions & capital ---
    "starting_capital": 100_000.0,
    "commission_pct": 0.0005,
    "slippage_pct": 0.0010,

    "min_history_days": 320,
}


# ============================ DATA ============================
def load_data(tickers, start, end, cfg):
    data = {}
    conn = price_db.get_connection()
    try:
        for t in tickers:
            df = price_db.load_prices(t, start=start, end=end, conn=conn)
            if df is None or df.empty or len(df) < cfg["min_history_days"]:
                continue
            data[t] = df.dropna()
    finally:
        conn.close()
    return data


# ============================ INDICATORS ============================
def rolling_slope_r2(logc, window):
    """Per-bar linear regression of log-price on time (x=0..window-1).
    Returns (annualized slope, R^2)."""
    x = np.arange(window, dtype=float)
    x_mean = x.mean()
    x_var = ((x - x_mean) ** 2).sum()

    def _calc(y):
        if np.isnan(y).any():
            return np.nan, np.nan
        y_mean = y.mean()
        y_var = ((y - y_mean) ** 2).sum()
        cov = ((x - x_mean) * (y - y_mean)).sum()
        slope = cov / x_var if x_var > 0 else 0.0
        if x_var == 0 or y_var == 0:
            r2 = 0.0
        else:
            r = cov / np.sqrt(x_var * y_var)
            r2 = r * r
        return slope, r2

    slopes = np.full(len(logc), np.nan)
    r2s = np.full(len(logc), np.nan)
    vals = logc.values
    for i in range(window - 1, len(vals)):
        s, r2 = _calc(vals[i - window + 1: i + 1])
        slopes[i] = s
        r2s[i] = r2
    return pd.Series(slopes * 252, index=logc.index), pd.Series(r2s, index=logc.index)


def rolling_touches(low, floor, atr, window, support_band_atr):
    """Count of local-minima bars within the trailing window whose Low is
    within `support_band_atr` * ATR of that window's floor."""
    low_v, floor_v, atr_v = low.values, floor.values, atr.values
    n = len(low_v)
    is_local_min = np.zeros(n, dtype=bool)
    is_local_min[1:-1] = (low_v[1:-1] < low_v[:-2]) & (low_v[1:-1] < low_v[2:])

    out = np.full(n, np.nan)
    for i in range(window - 1, n):
        if np.isnan(floor_v[i]) or np.isnan(atr_v[i]):
            continue
        thresh = floor_v[i] + support_band_atr * atr_v[i]
        lo = i - window + 1
        window_lows = low_v[lo:i + 1]
        window_min = is_local_min[lo:i + 1]
        out[i] = np.sum(window_min & (window_lows <= thresh))
    return pd.Series(out, index=low.index)


def add_indicators(df, cfg):
    high, low, close, openp, vol = df["High"], df["Low"], df["Close"], df["Open"], df["Volume"]
    prev_close = close.shift(1)
    w = cfg["range_window"]

    tr = pd.concat([
        (high - low), (high - prev_close).abs(), (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    df["ATR"] = tr.rolling(cfg["atr_period"]).mean()

    df["floor"] = low.rolling(w).min()
    df["ceiling"] = high.rolling(w).max()
    df["width"] = df["ceiling"] - df["floor"]

    logc = np.log(close)
    slope_ann, r2 = rolling_slope_r2(logc, w)
    df["slope_ann"] = slope_ann
    df["r2"] = r2

    # bars since the window's minimum low occurred (0 = the current bar)
    floor_age = low.rolling(w).apply(lambda x: len(x) - 1 - np.argmin(x.values), raw=False)
    df["floor_age"] = floor_age

    df["touches"] = rolling_touches(low, df["floor"], df["ATR"], w, cfg["support_band_atr"])

    df["turnover"] = (close * vol).rolling(cfg["turnover_window"]).median()

    # ---- B.1 range conditions ----
    flat = df["slope_ann"].abs() < cfg["max_abs_slope"]
    choppy = df["r2"] < cfg["max_r2"]
    width_ok = df["width"] >= cfg["min_width_atr"] * df["ATR"]
    established = (df["floor_age"] >= cfg["support_established_bars"]) & (close > df["floor"])
    touches_ok = df["touches"] >= cfg["min_touches"]
    df["range_ok"] = flat & choppy & width_ok & established & touches_ok

    # ---- B.2 low in range ----
    range_pos = (close - df["floor"]) / df["width"].replace(0, np.nan)
    df["range_pos"] = range_pos
    df["low_in_range"] = (range_pos <= cfg["bottom_frac"]) & ((close - df["floor"]) <= df["ATR"])

    # ---- B.3 entry trigger ----
    support_band = df["floor"] + cfg["support_band_atr"] * df["ATR"]
    touched_support = low <= support_band
    touched_recent = touched_support | touched_support.shift(1).fillna(False)
    bull_bar = close > openp
    bar_range = (high - low).replace(0, np.nan)
    closes_upper_half = ((close - low) / bar_range) >= 0.5

    candidate = df["range_ok"] & df["low_in_range"]
    df["baseline_signal"] = candidate.fillna(False)
    df["entry_signal"] = (candidate & touched_recent & bull_bar & closes_upper_half).fillna(False)

    return df


# ============================ BACKTEST LOOP ============================
def run_backtest(data, bench, cfg, signal_col="entry_signal"):
    cash = cfg["starting_capital"]
    positions = {}     # ticker -> dict
    pending = []        # entries to attempt at today's open
    soft_exits = {}     # ticker -> reason, to execute at today's open
    equity_curve = []
    trades = []

    sl = cfg["slippage_pct"]

    for d in bench.index:
        # ---- 1. queued soft exits (range failure / time stop) at today's open ----
        for t in list(soft_exits.keys()):
            df = data[t]
            if d not in df.index or t not in positions:
                soft_exits.pop(t, None)
                continue
            row = df.loc[d]
            pos = positions[t]
            fill = row["Open"] * (1 - sl)
            proceeds = pos["shares"] * fill
            proceeds -= proceeds * cfg["commission_pct"]
            cash += proceeds
            pnl = (fill - pos["entry"]) * pos["shares"]
            trades.append({"ticker": t, "entry": pos["entry"], "exit": fill,
                            "shares": pos["shares"], "pnl": pnl,
                            "ret": fill / pos["entry"] - 1.0,
                            "entry_date": pos["entry_date"], "exit_date": d,
                            "exit_reason": soft_exits[t]})
            del positions[t]
            del soft_exits[t]

        # ---- 2. stop / target exits checked against today's low/high ----
        for t in list(positions.keys()):
            df = data[t]
            if d not in df.index:
                continue
            row = df.loc[d]
            pos = positions[t]
            exit_price, reason = None, None
            if row["Low"] <= pos["stop"]:
                exit_price = min(row["Open"], pos["stop"]) * (1 - sl)
                reason = "stop"
            elif row["High"] >= pos["target"]:
                exit_price = max(row["Open"], pos["target"]) * (1 - sl)
                reason = "target"
            if exit_price is not None:
                proceeds = pos["shares"] * exit_price
                proceeds -= proceeds * cfg["commission_pct"]
                cash += proceeds
                pnl = (exit_price - pos["entry"]) * pos["shares"]
                trades.append({"ticker": t, "entry": pos["entry"], "exit": exit_price,
                                "shares": pos["shares"], "pnl": pnl,
                                "ret": exit_price / pos["entry"] - 1.0,
                                "entry_date": pos["entry_date"], "exit_date": d,
                                "exit_reason": reason})
                del positions[t]

        # ---- 3. fill pending entries at today's open ----
        def equity_now():
            held = 0.0
            for t, p in positions.items():
                df = data[t]
                held += p["shares"] * (df.loc[d, "Open"] if d in df.index else p["entry"])
            return cash + held

        for order in pending:
            t = order["ticker"]
            if t in positions or len(positions) >= cfg["max_positions"]:
                continue
            df = data[t]
            if d not in df.index:
                continue
            row = df.loc[d]

            if cfg["entry_mode"] == "stop_above_signal":
                if row["High"] < order["signal_high"]:
                    continue  # not triggered today; order expires (1-day validity)
                entry = max(row["Open"], order["signal_high"]) * (1 + sl)
            else:
                entry = row["Open"] * (1 + sl)

            risk_per_share = entry - order["stop"]
            if risk_per_share <= 0 or math.isnan(risk_per_share):
                continue

            eq = equity_now()
            shares = math.floor((eq * cfg["risk_per_trade"]) / risk_per_share)
            if shares <= 0:
                continue

            cost = shares * entry
            cost_with_fee = cost * (1 + cfg["commission_pct"])
            if cost_with_fee > cash:
                shares = math.floor(cash / (entry * (1 + cfg["commission_pct"])))
                if shares <= 0:
                    continue
                cost = shares * entry
                cost_with_fee = cost * (1 + cfg["commission_pct"])

            cash -= cost_with_fee
            positions[t] = {"shares": shares, "entry": entry, "stop": order["stop"],
                             "target": order["target"], "floor": order["floor"],
                             "entry_date": d, "bars_held": 0}
        pending = []

        # ---- 4. new signals -> queue for tomorrow's entry ----
        candidates = []
        for t, df in data.items():
            if t in positions or d not in df.index:
                continue
            row = df.loc[d]
            if (bool(row.get(signal_col, False)) and
                    row["turnover"] >= cfg["min_turnover_sek"] and
                    not np.isnan(row["ATR"]) and row["ATR"] > 0):
                stop = min(row["Low"], row["floor"]) - cfg["stop_buffer_atr"] * row["ATR"]
                target = row["ceiling"]
                if stop > 0 and target > stop:
                    candidates.append((row["range_pos"], t, stop, target, row["floor"], row["High"]))
        candidates.sort(key=lambda x: x[0])  # closer to the floor first
        slots = cfg["max_positions"] - len(positions)
        for _, t, stop, target, floor, sig_high in candidates[:max(slots, 0)]:
            pending.append({"ticker": t, "stop": stop, "target": target,
                             "floor": floor, "signal_high": sig_high})

        # ---- 5. update open positions: bars held, queue soft exits for tomorrow ----
        for t, pos in positions.items():
            df = data[t]
            if d not in df.index:
                continue
            row = df.loc[d]
            pos["bars_held"] += 1
            if row["Close"] < pos["floor"]:
                soft_exits[t] = "range_fail"
            elif pos["bars_held"] >= cfg["max_hold_bars"]:
                soft_exits[t] = "time_stop"

        # ---- 6. mark to market ----
        held = 0.0
        for t, p in positions.items():
            df = data[t]
            held += p["shares"] * (df.loc[d, "Close"] if d in df.index else p["entry"])
        equity_curve.append((d, cash + held))

    eq = pd.Series({d: v for d, v in equity_curve}).sort_index()
    return eq, pd.DataFrame(trades)


def range_failure_rate(trades):
    if trades.empty:
        return float("nan")
    return (trades["exit_reason"] == "range_fail").mean()


# ============================ MAIN ============================
def main():
    cfg = CONFIG
    print("Loading benchmark...")
    bench = price_db.load_prices(cfg["benchmark"], start=cfg["start"], end=cfg["end"]).dropna()

    print("Loading universe...")
    universe = price_db.load_universe(cfg["segments"])
    tickers = [t for t, _, seg in universe if seg != "Index"]
    data = load_data(tickers, cfg["start"], cfg["end"], cfg)
    print(f"  {len(data)} tickers loaded.")
    if not data:
        raise SystemExit("No usable data.")

    print("Computing indicators (this loops per-ticker for the support-touch count)...")
    for t in data:
        data[t] = add_indicators(data[t], cfg)

    print("Running TRIGGER strategy (B.1-B.6)...")
    eq_trig, trades_trig = run_backtest(data, bench, cfg, signal_col="entry_signal")
    stats_trig = engine.perf_stats(eq_trig, "STRATEGY B: Range/BLSH (with trigger)")
    engine.trade_stats(trades_trig)
    rfr_trig = range_failure_rate(trades_trig)
    print(f"  Range-failure rate: {rfr_trig*100:.1f}%" if not np.isnan(rfr_trig) else "  No trades.")

    print("\nRunning NO-TRIGGER baseline (buy any range-low candidate)...")
    eq_base, trades_base = run_backtest(data, bench, cfg, signal_col="baseline_signal")
    stats_base = engine.perf_stats(eq_base, "BASELINE: Range-low, no trigger")
    engine.trade_stats(trades_base)
    rfr_base = range_failure_rate(trades_base)
    print(f"  Range-failure rate: {rfr_base*100:.1f}%" if not np.isnan(rfr_base) else "  No trades.")

    bh = engine.buy_and_hold(bench, cfg["starting_capital"]).reindex(eq_trig.index).ffill()
    engine.perf_stats(bh, f"BASELINE: Buy & Hold {cfg['benchmark']}")

    print("\n=== VERDICT ===")
    print(f"  Trigger strategy CAGR {stats_trig['cagr']*100:.2f}% / Sharpe {stats_trig['sharpe']:.2f} "
          f"vs no-trigger CAGR {stats_base['cagr']*100:.2f}% / Sharpe {stats_base['sharpe']:.2f}")
    print("  A positive expectancy after costs, AND the trigger beating the")
    print("  no-trigger baseline, AND a contained range-failure rate are all")
    print("  needed before this is considered 'relatively reliable' per spec.")


if __name__ == "__main__":
    main()
