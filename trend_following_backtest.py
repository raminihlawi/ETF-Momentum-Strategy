"""
Mechanical long-only trend-following backtest — an equity basket.

This is a fully RULE-BASED strategy. No discretion, no chart reading, no LLM.
It embodies the only things that are reasonably well documented to work:

  1. Trade only WITH the trend (price above its own 200-day average).
  2. Trade only when the broad market regime is risk-on (index above its 200-day).
  3. Enter on an unambiguous momentum trigger (a 50-day breakout).
  4. CUT LOSERS fast with a hard initial stop (entry - 3*ATR).
  5. LET WINNERS RUN with a ratcheting chandelier trailing stop.
  6. Spread risk across MANY positions (breadth), ranked by momentum.
  7. Risk an EQUAL fraction of capital per trade (volatility-based sizing).
  8. Bake in COSTS, because an edge built on small margins dies on friction.

The purpose of this file is to be your HONEST BASELINE. Any fancier system
(Al Brooks discretion, an LLM scanner, etc.) has to beat THIS, net of costs,
out of sample, before its extra complexity is justified.

-------------------------------------------------------------------------
HONEST CAVEATS — read these before trusting any number this prints:

* SURVIVORSHIP BIAS is the big one. If you feed it today's index members,
  you exclude every company that was delisted/went bankrupt, which inflates
  results badly. For a real test you need a point-in-time (survivorship-bias-
  free) constituent list. Treat results on a hand-picked ticker list as
  optimistic by an unknown, possibly large, margin.
* Data quality: yfinance is free and imperfect (bad ticks, gaps, adjustment
  quirks). auto_adjust=True handles splits/dividends but isn't flawless.
* Costs here are estimates. Real spreads on illiquid names are worse.
* Stops are checked against the daily LOW; a gap through your stop fills at
  the open. Intraday slippage on real fills can be worse than modeled.
* This is a backtest. Past performance is not predictive. Paper-trade first.
-------------------------------------------------------------------------

Requires: pip install pandas numpy
Data:     reads from stockholm_ohlc.sqlite3 (build/update with build_price_db.py)
Run:      python trend_following_backtest.py
"""

import pandas as pd

import price_db
import backtest_engine as engine


# ============================ CONFIG ============================
CONFIG = {
    # --- universe & period ---
    # Universe is loaded from the local price DB (stockholm_ohlc.sqlite3).
    # NOTE: this reflects TODAY's index membership, not point-in-time
    # constituents as of `start` -> survivorship bias still applies.
    "segments": ["Large", "Mid", "Small"],
    "benchmark": "^OMX",          # regime filter + buy & hold baseline
    "start": "2020-01-01",
    "end":   None,                # None = up to the latest data in the DB

    # --- signal parameters ---
    "trend_sma": 200,            # per-stock trend filter
    "regime_sma": 200,           # benchmark regime filter
    "breakout_lookback": 50,     # Donchian entry channel (N-day high)
    "atr_period": 20,            # ATR for stops & sizing
    "stop_atr_mult": 3.0,        # stop distance in ATRs (initial + chandelier)
    "momentum_lookback": 100,    # used only to rank when slots are scarce

    # --- portfolio & risk ---
    "starting_capital": 100_000.0,
    "risk_per_trade": 0.0075,    # 0.75% of equity risked per position
    "max_positions": 20,

    # --- frictions ---
    "commission_pct": 0.0005,    # 0.05% per side
    "slippage_pct":   0.0010,    # 0.10% per side
}


# ============================ DATA ============================
def load_data(tickers, start, end):
    """Load daily OHLC for each ticker from the local price DB into a dict of DataFrames."""
    data = {}
    conn = price_db.get_connection()
    try:
        for t in tickers:
            df = price_db.load_prices(t, start=start, end=end, conn=conn)
            if df is None or df.empty or len(df) < 250:
                print(f"  ! {t}: insufficient data, skipped")
                continue
            data[t] = df.dropna()
    finally:
        conn.close()
    return data


# ============================ INDICATORS ============================
def add_indicators(df, cfg):
    """Attach the columns the strategy reads. All are shift-safe (no look-ahead)."""
    high, low, close = df["High"], df["Low"], df["Close"]
    prev_close = close.shift(1)

    # True Range -> ATR (simple rolling mean; transparent)
    tr = pd.concat([
        (high - low),
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    df["ATR"] = tr.rolling(cfg["atr_period"]).mean()

    # Trend filter
    df["SMA"] = close.rolling(cfg["trend_sma"]).mean()
    df["trend_ok"] = close > df["SMA"]

    # Donchian entry channel: highest HIGH of the PRIOR N days (excludes today).
    # A breakout is today's CLOSE exceeding that level -> known at today's close.
    df["donchian_high"] = high.rolling(cfg["breakout_lookback"]).max().shift(1)

    # Momentum for ranking when slots are scarce
    df["momentum"] = close / close.shift(cfg["momentum_lookback"]) - 1.0

    # Entry trigger: trend filter + Donchian breakout (known at today's close)
    df["entry_signal"] = (df["trend_ok"] &
                           (close > df["donchian_high"]) &
                           df["donchian_high"].notna())
    return df



# ============================ MAIN ============================
def main():
    cfg = CONFIG
    print("Loading benchmark...")
    bench = price_db.load_prices(cfg["benchmark"], start=cfg["start"], end=cfg["end"])
    bench = bench.dropna()

    print("Loading universe...")
    universe = price_db.load_universe(cfg["segments"])
    tickers = [t for t, _, seg in universe if seg != "Index"]
    data = load_data(tickers, cfg["start"], cfg["end"])
    print(f"  {len(data)} tickers loaded.")
    if not data:
        raise SystemExit("No usable data.")

    for t in data:
        data[t] = add_indicators(data[t], cfg)

    print("Running backtest...")
    equity, trades = engine.run_backtest(data, bench, cfg)

    strat = engine.perf_stats(equity, "TREND-FOLLOWING STRATEGY")
    engine.trade_stats(trades)

    bh = engine.buy_and_hold(bench, cfg["starting_capital"]).reindex(equity.index).ffill()
    base = engine.perf_stats(bh, f"BASELINE: Buy & Hold {cfg['benchmark']}")

    print("\n=== VERDICT ===")
    beat_cagr = strat["cagr"] > base["cagr"]
    beat_dd = strat["max_dd"] > base["max_dd"]  # less negative = shallower
    print(f"  Beat baseline CAGR?     {'YES' if beat_cagr else 'NO'}")
    print(f"  Shallower drawdown?     {'YES' if beat_dd else 'NO'}")
    print("  If it doesn't clearly beat buy & hold on a RISK-ADJUSTED basis,")
    print("  the complexity isn't earning its keep. And remember: survivorship")
    print("  bias means the real edge is smaller than whatever you see above.")


if __name__ == "__main__":
    main()
