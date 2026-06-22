"""
Pullback-in-uptrend screener — surfaces momentum names set up for a
discretionary Al Brooks H2/H3 entry.

PHILOSOPHY
This is the mechanical half of a hybrid workflow. It does ONE thing well:
deterministically rank the universe and surface stocks that are
  (a) in an established uptrend,
  (b) currently pulling back toward value (the EMA20 zone), and
  (c) have room to run.
It does NOT decide entries. It emits a watchlist with the context a price-
action trader needs. YOU read the chart and decide whether an H2/H3 trigger
bar actually prints. The edge lives in your discretion; the screener just
makes sure the names you look at are structurally sound.

WHY PULLBACK, NOT BREAKOUT
Brooks prefers buying pullbacks in a trend over chasing breakouts: better
risk/reward, fewer failed entries. So this screen looks for healthy uptrends
that are dipping to a logical support area, not stocks at new highs.

HONEST NOTES
- Survivorship bias still applies: a hand-picked ticker list flatters results.
- This screen is tunable — the thresholds below encode ONE reading of what a
  pre-H2 setup looks like. Adjust them to your taste; they are not gospel.
- You can't backtest the full thing (the H2/H3 read is yours). You can sanity-
  check that the screen surfaces tradeable setups, but the entry is discretionary.

Requires: pip install pandas numpy
Data:     reads from stockholm_ohlc.sqlite3 (build/update with build_price_db.py)
Run:      python pullback_screener.py
"""

import numpy as np
import pandas as pd

import price_db


# ============================ CONFIG ============================
CONFIG = {
    # Universe is loaded from the local price DB (stockholm_ohlc.sqlite3).
    # Restrict to one or more segments, or set to None for the whole universe.
    "segments": ["Large", "Mid", "Small"],
    "benchmark": "^OMX",
    "lookback_days": 400,        # history window used for indicators

    # --- indicator params ---
    "ema_fast": 20,              # Brooks' key MA — the pullback target
    "ema_mid": 50,
    "sma_slow": 200,
    "atr_period": 20,
    "momentum_window": 90,       # R^2 regression window (Clenow-style ranking)
    "swing_high_lookback": 40,   # window to locate the recent swing high

    # --- pullback definition (tune to taste) ---
    "min_pullback_atr": 0.5,     # must be at least this far below recent high
    "max_dist_above_ema20_atr": 1.5,   # close not too far above EMA20...
    "max_dist_below_ema20_atr": 0.75,  # ...nor dipped too far below it
    "notional_stop_atr": 2.0,    # for computing reward-to-resistance in R

    "require_regime_on": True,   # no candidates when index below its 200MA
    "min_room_R": 1.5,           # need at least this much room to recent high
}


# ============================ DATA ============================
def load_data(tickers, lookback_days, benchmark):
    all_t = list(dict.fromkeys(tickers + [benchmark]))
    data = {}
    conn = price_db.get_connection()
    try:
        for t in all_t:
            df = price_db.load_prices(t, conn=conn)
            if df is None or df.empty or len(df) < 220:
                continue
            data[t] = df.tail(lookback_days)
    finally:
        conn.close()
    return data


# ============================ INDICATORS ============================
def momentum_r2(close, window):
    """Annualized exp-regression slope * R^2 (Clenow). Rewards fast AND clean."""
    y = np.log(close.tail(window).values)
    if len(y) < window or np.any(~np.isfinite(y)):
        return np.nan
    x = np.arange(len(y))
    slope, intercept = np.polyfit(x, y, 1)
    fit = slope * x + intercept
    ss_res = np.sum((y - fit) ** 2)
    ss_tot = np.sum((y - y.mean()) ** 2)
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0
    annual = np.exp(slope * 252) - 1
    return annual * r2


def latest_metrics(df, cfg):
    high, low, close = df["High"], df["Low"], df["Close"]
    prev_close = close.shift(1)
    tr = pd.concat([(high - low), (high - prev_close).abs(),
                    (low - prev_close).abs()], axis=1).max(axis=1)
    atr = tr.rolling(cfg["atr_period"]).mean()

    ema20 = close.ewm(span=cfg["ema_fast"], adjust=False).mean()
    ema50 = close.ewm(span=cfg["ema_mid"], adjust=False).mean()
    sma200 = close.rolling(cfg["sma_slow"]).mean()

    if len(df) < cfg["sma_slow"] + 5 or pd.isna(sma200.iloc[-1]) or atr.iloc[-1] <= 0:
        return None

    c = close.iloc[-1]
    a = atr.iloc[-1]
    recent_high = high.tail(cfg["swing_high_lookback"]).max()
    high_252 = high.tail(252).max() if len(df) >= 252 else recent_high
    # bars since the recent swing high (pullback age)
    hh_idx = high.tail(cfg["swing_high_lookback"]).values.argmax()
    bars_since_high = cfg["swing_high_lookback"] - 1 - hh_idx

    # reward to recent high, in R, with a notional 2*ATR stop
    risk = cfg["notional_stop_atr"] * a
    room_R = (recent_high - c) / risk if risk > 0 else np.nan

    return {
        "close": c, "atr": a,
        "ema20": ema20.iloc[-1], "ema50": ema50.iloc[-1], "sma200": sma200.iloc[-1],
        "ema50_rising": ema50.iloc[-1] > ema50.iloc[-21],
        "recent_high": recent_high, "high_252": high_252,
        "pullback_atr": (recent_high - c) / a,
        "dist_ema20_atr": (c - ema20.iloc[-1]) / a,
        "bars_since_high": int(bars_since_high),
        "room_R": room_R,
        "pct_above_200": (c / sma200.iloc[-1] - 1) * 100,
        "near_1yr_high": (high_252 - recent_high) / a < 1.0,  # little overhead
        "momentum": momentum_r2(close, cfg["momentum_window"]),
    }


# ============================ SCREEN ============================
def passes(m, cfg):
    # 1) established uptrend
    uptrend = (m["close"] > m["sma200"] and m["ema20"] > m["ema50"]
               and m["ema50_rising"])
    # 2) healthy pullback toward the EMA20 zone, trend intact
    pulled_back = m["pullback_atr"] >= cfg["min_pullback_atr"]
    trend_intact = m["close"] > m["ema50"]
    near_value = (m["dist_ema20_atr"] <= cfg["max_dist_above_ema20_atr"]
                  and m["dist_ema20_atr"] >= -cfg["max_dist_below_ema20_atr"])
    # 3) room to run
    has_room = m["room_R"] >= cfg["min_room_R"]
    return uptrend and pulled_back and trend_intact and near_value and has_room


def main():
    cfg = CONFIG
    print("Loading from local price DB...")
    universe = price_db.load_universe(cfg["segments"])
    tickers = [t for t, _, seg in universe if seg != "Index"]
    data = load_data(tickers, cfg["lookback_days"], cfg["benchmark"])
    bench = data.get(cfg["benchmark"])

    regime_on = True
    if bench is not None:
        b = bench["Close"]
        regime_on = b.iloc[-1] > b.rolling(cfg["sma_slow"]).mean().iloc[-1]
    print(f"Regime: index {'RISK-ON' if regime_on else 'RISK-OFF'}")

    if cfg["require_regime_on"] and not regime_on:
        print("\nIndex below its 200-day average — standing aside. No candidates.")
        return

    rows = []
    for t, df in data.items():
        if t == cfg["benchmark"]:
            continue
        m = latest_metrics(df, cfg)
        if m and not np.isnan(m["momentum"]) and passes(m, cfg):
            rows.append((t, m))

    rows.sort(key=lambda r: r[1]["momentum"], reverse=True)

    print(f"\n{'='*78}\nPULLBACK WATCHLIST — {len(rows)} candidates set up for a possible H2/H3")
    print(f"(ranked by trend quality; YOU confirm the trigger bar)\n{'='*78}")
    if not rows:
        print("Nothing qualifies today. That's a valid answer — patience.")
        return

    hdr = (f"{'Tkr':<8}{'MomR²':>7}{'>200MA':>8}{'PB(atr)':>9}"
           f"{'ΔEMA20':>8}{'PBage':>7}{'Room(R)':>9}{'ATR':>9}  Notes")
    print(hdr)
    print("-" * 78)
    for t, m in rows:
        notes = "near 1yr-high" if m["near_1yr_high"] else ""
        if m["dist_ema20_atr"] < 0:
            notes = (notes + " | below EMA20").strip(" |")
        print(f"{t:<8}{m['momentum']*100:>6.1f}%{m['pct_above_200']:>7.1f}%"
              f"{m['pullback_atr']:>9.2f}{m['dist_ema20_atr']:>8.2f}"
              f"{m['bars_since_high']:>7d}{m['room_R']:>9.2f}{m['atr']:>9.2f}  {notes}")

    print("\nReading the columns:")
    print("  MomR²   = Clenow trend quality (speed × straightness); higher = cleaner trend")
    print("  PB(atr) = how far below the recent high, in ATRs (the pullback depth)")
    print("  ΔEMA20  = distance from the 20-EMA in ATRs; ~0 means sitting on value (prime H2)")
    print("  PBage   = bars since the swing high (how mature the pullback is)")
    print("  Room(R) = reward to the recent high vs a notional 2-ATR stop")
    print("\nThis is a watchlist, not a signal. Pull up each chart and wait for the H2/H3.")


if __name__ == "__main__":
    main()
