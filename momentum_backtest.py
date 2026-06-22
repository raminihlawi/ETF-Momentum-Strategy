"""
Strategy A — Robust Composite Momentum (monthly-rebalanced portfolio).

Implements `files/STRATEGY_SPEC.md` section 1:
  - Composite momentum score: average of cross-sectional percentile ranks of
    3 / 6 / 12 month total return.
  - Quality filter: exclude the bottom 20% by 90-day log-price R^2.
  - Regime gate: benchmark close > 200-day SMA -> hold the book, else cash.
  - Selection: top-N by composite score, with banded (hysteresis) rebalancing
    -- a held name is sold only once it drops out of the top 20%.
  - Weighting: inverse-volatility (126-day daily-return stdev), normalized.
  - Rebalanced monthly (last trading day -> executed at next open).

Two baselines are run alongside:
  (a) benchmark buy & hold.
  (b) a "naive" equal-weight top-10 composite momentum WITHOUT the regime
      gate, quality filter, inverse-vol weighting or banding -- to show
      whether the robustness elements actually earn their keep.

HONEST CAVEATS
- Survivorship bias: universe is today's index membership, not point-in-time
  constituents (see PROJECT_SPEC.md).
- Local price history only goes back to ~2020, so the 200-day regime SMA and
  12-month momentum lookback are NaN (regime gate effectively OFF) for the
  first year -> the strategy is in cash until late in year 1. Results before
  ~2021 should be read with that in mind.
- This is the FIRST validation pass: a single full-period run plus a per-year
  breakdown and a regime-off diagnostic. The parameter robustness sweep and
  proper walk-forward windowing called for in STRATEGY_SPEC.md section 3 are
  follow-up work, not done here.

Requires: pip install pandas numpy
Data:     reads from stockholm_ohlc.sqlite3 (build/update with build_price_db.py)
Run:      python momentum_backtest.py
"""

import numpy as np
import pandas as pd

import price_db
import backtest_engine as engine


# ============================ CONFIG ============================
CONFIG = {
    # --- universe & period ---
    "segments": ["Large", "Mid", "Small"],
    "benchmark": "^OMX",
    "start": "2009-01-01",        # ^OMX (OMX Stockholm 30) only has data from 2008-11-20
    "end": None,                  # None = up to latest data in the DB

    # --- composite momentum ---
    # 18/12/6-month horizons + the academic "12-1" convention (skip the most
    # recent month, to avoid short-term reversal) -- this combination tested
    # best for Strategy A: see sweep_results/skip_comparison.png (Sharpe 0.75
    # vs 0.58 for the original 3/6/12, skip=0 default).
    "horizons": {"ret_18m": 378, "ret_12m": 252, "ret_6m": 126},
    "skip_recent_days": 21,

    # --- quality filter ---
    "use_quality_filter": True,
    "r2_window": 90,
    "quality_cutoff_pct": 0.20,   # exclude bottom 20% by R^2

    # --- optional skew filter (not applied by default) ---
    "skew_filter": False,

    # --- regime gate ---
    "use_regime_gate": True,
    "regime_sma": 200,

    # --- selection & weighting ---
    "top_n": 10,
    "use_banding": True,
    "band_exit_pct": 0.20,        # held names sold once they drop out of top 20%
    "weighting": "inv_vol",       # "inv_vol" | "equal"
    "vol_window": 126,

    # --- liquidity ---
    "min_turnover_sek": 20_000_000,
    "turnover_window": 20,

    # --- rebalancing ---
    "rebal": "monthly",

    # --- frictions & capital ---
    "starting_capital": 100_000.0,
    "cost_per_side": 0.0015,      # 0.15% commission + slippage, per side

    # --- minimum history required to include a ticker ---
    "min_history_days": 320,
}


# ============================ DATA ============================
def load_data(tickers, start, end):
    data = {}
    conn = price_db.get_connection()
    try:
        for t in tickers:
            df = price_db.load_prices(t, start=start, end=end, conn=conn)
            if df is None or df.empty or len(df) < CONFIG["min_history_days"]:
                continue
            data[t] = df.dropna()
    finally:
        conn.close()
    return data


# ============================ INDICATORS ============================
def rolling_r2(logc, window):
    """R^2 of a simple linear regression of log-price on time, over a
    trailing window. For a single regressor, R^2 == correlation^2."""
    x = np.arange(window, dtype=float)
    x_mean = x.mean()
    x_var = ((x - x_mean) ** 2).sum()

    def _r2(y):
        if np.isnan(y).any():
            return np.nan
        y_mean = y.mean()
        y_var = ((y - y_mean) ** 2).sum()
        if x_var == 0 or y_var == 0:
            return 0.0
        cov = ((x - x_mean) * (y - y_mean)).sum()
        r = cov / np.sqrt(x_var * y_var)
        return r * r

    return logc.rolling(window).apply(_r2, raw=True)


def add_indicators(df, cfg):
    close, vol = df["Close"], df["Volume"]
    logc = np.log(close)

    for name, h in cfg["horizons"].items():
        sk = cfg["skip_recent_days"]
        df[name] = close.shift(sk) / close.shift(sk + h) - 1.0

    df["r2_90"] = rolling_r2(logc, cfg["r2_window"])

    daily_ret = close.pct_change()
    df["vol_126"] = daily_ret.rolling(cfg["vol_window"]).std()

    if cfg["skew_filter"]:
        df["skew_126"] = daily_ret.rolling(126).skew()

    df["turnover"] = (close * vol).rolling(cfg["turnover_window"]).median()
    return df


def month_end_dates(index):
    s = pd.Series(index, index=index)
    return pd.DatetimeIndex(s.groupby([index.year, index.month]).last().values)


# ============================ SELECTION ============================
def compute_target_weights(snapshot, current_holdings, cfg, regime_ok):
    """`snapshot`: DataFrame indexed by ticker with one column per entry in
    cfg["horizons"], plus r2_90, vol_126, turnover (all as of the signal date)."""
    if cfg["use_regime_gate"] and not regime_ok:
        return {}

    horizon_cols = list(cfg["horizons"].keys())
    df = snapshot.dropna(subset=horizon_cols + ["vol_126"])
    df = df[df["turnover"] >= cfg["min_turnover_sek"]]
    if df.empty:
        return {}

    pct_cols = []
    for col in horizon_cols:
        df[col + "_pct"] = df[col].rank(pct=True)
        pct_cols.append(col + "_pct")
    df["composite"] = df[pct_cols].mean(axis=1)

    if cfg["use_quality_filter"]:
        df = df.dropna(subset=["r2_90"])
        if df.empty:
            return {}
        df["r2_pct"] = df["r2_90"].rank(pct=True)
        df = df[df["r2_pct"] >= cfg["quality_cutoff_pct"]]
        if df.empty:
            return {}

    df["score_pct"] = df["composite"].rank(pct=True)

    held_keep = []
    if cfg["use_banding"]:
        held_keep = [t for t in current_holdings
                      if t in df.index and df.loc[t, "score_pct"] >= (1 - cfg["band_exit_pct"])]

    n_need = cfg["top_n"] - len(held_keep)
    top10_thresh = 1 - 0.10
    candidates = df[(~df.index.isin(held_keep)) & (df["score_pct"] >= top10_thresh)]
    candidates = candidates.sort_values("composite", ascending=False)
    new_picks = list(candidates.index[:max(n_need, 0)])

    selected = held_keep + new_picks
    if not selected:
        selected = list(df.sort_values("composite", ascending=False).index[:cfg["top_n"]])

    if cfg["weighting"] == "inv_vol":
        inv = 1.0 / df.loc[selected, "vol_126"]
        weights = inv / inv.sum()
    else:
        weights = pd.Series(1.0 / len(selected), index=selected)

    return weights.to_dict()


# ============================ BACKTEST LOOP ============================
def run_backtest(data, bench, regime_on, rebal_dates, cfg):
    cash = cfg["starting_capital"]
    shares = {}
    equity_curve = []
    rebal_log = []
    pending = None
    rebal_set = set(rebal_dates)

    for d in bench.index:
        # ---- execute pending rebalance at today's open ----
        if pending is not None:
            value = cash
            open_px = {}
            for t in shares:
                df = data[t]
                if d in df.index:
                    open_px[t] = df.loc[d, "Open"]
                else:
                    open_px[t] = df["Close"].reindex(bench.index).ffill().loc[d]
                value += shares[t] * open_px[t]
            for t in pending:
                if t not in open_px:
                    df = data[t]
                    if d in df.index:
                        open_px[t] = df.loc[d, "Open"]
                    else:
                        open_px[t] = np.nan

            turnover_value = 0.0
            new_shares = {}
            for t, w in pending.items():
                px = open_px.get(t)
                if px is None or np.isnan(px) or px <= 0:
                    continue
                target_val = value * w
                cur_val = shares.get(t, 0.0) * px
                turnover_value += abs(target_val - cur_val)
                new_shares[t] = target_val / px
            for t in shares:
                if t not in pending:
                    turnover_value += shares[t] * open_px[t]

            cost = turnover_value * cfg["cost_per_side"]
            invested = sum(new_shares[t] * open_px[t] for t in new_shares)
            cash = value - invested - cost
            shares = new_shares
            rebal_log.append((d, len(shares), cost))
            pending = None

        # ---- mark to market at close ----
        held = 0.0
        for t, sh in shares.items():
            df = data[t]
            if d in df.index:
                held += sh * df.loc[d, "Close"]
            else:
                held += sh * df["Close"].reindex(bench.index).ffill().loc[d]
        equity_curve.append((d, cash + held))

        # ---- compute signal at close of a rebalance date ----
        if d in rebal_set:
            rows = {}
            for t, df in data.items():
                if d not in df.index:
                    continue
                row = df.loc[d]
                entry = {"r2_90": row["r2_90"], "vol_126": row["vol_126"],
                         "turnover": row["turnover"]}
                for col in cfg["horizons"]:
                    entry[col] = row[col]
                rows[t] = entry
            snapshot = pd.DataFrame(rows).T
            regime_ok = bool(regime_on.get(d, False))
            pending = compute_target_weights(snapshot, list(shares.keys()), cfg, regime_ok)

    eq = pd.Series({d: v for d, v in equity_curve}).sort_index()
    return eq, pd.DataFrame(rebal_log, columns=["date", "n_holdings", "cost"])


# ============================ DIAGNOSTICS ============================
def regime_off_diagnostic(equity, regime_on, label):
    rets = equity.pct_change().dropna()
    on_mask = regime_on.reindex(rets.index).fillna(False)
    off_rets = rets[~on_mask]
    if off_rets.empty:
        print(f"  {label}: no regime-OFF days in this sample.")
        return
    cum_off = (1 + off_rets).prod() - 1
    print(f"  {label}: regime-OFF days = {len(off_rets)}, "
          f"cumulative return during OFF = {cum_off*100:6.2f}%")


def per_year_stats(equity, label):
    print(f"\n  --- {label}: per-year ---")
    for year, grp in equity.groupby(equity.index.year):
        if len(grp) < 2:
            continue
        ret = grp.iloc[-1] / grp.iloc[0] - 1
        print(f"    {year}: {ret*100:7.2f}%")


# ============================ MAIN ============================
def main():
    cfg = CONFIG
    print("Loading benchmark...")
    bench = price_db.load_prices(cfg["benchmark"], start=cfg["start"], end=cfg["end"]).dropna()

    print("Loading universe...")
    universe = price_db.load_universe(cfg["segments"])
    tickers = [t for t, _, seg in universe if seg != "Index"]
    data = load_data(tickers, cfg["start"], cfg["end"])
    print(f"  {len(data)} tickers loaded.")
    if not data:
        raise SystemExit("No usable data.")

    for t in data:
        data[t] = add_indicators(data[t], cfg)

    regime_on = bench["Close"] > bench["Close"].rolling(cfg["regime_sma"]).mean()
    rebal_dates = month_end_dates(bench.index)
    # only rebalance once 12m momentum + R^2 + vol windows can be populated
    min_start = bench.index[max(cfg["horizons"].values()) + cfg["skip_recent_days"]]
    rebal_dates = rebal_dates[rebal_dates >= min_start]

    print("Running Strategy A (full robustness elements)...")
    eq_a, log_a = run_backtest(data, bench, regime_on, rebal_dates, cfg)
    stats_a = engine.perf_stats(eq_a, "STRATEGY A: Composite Momentum (full)")
    print(f"  Rebalances: {len(log_a)}, total cost paid: "
          f"{log_a['cost'].sum():,.0f} ({log_a['cost'].sum()/cfg['starting_capital']*100:.2f}% of starting capital)")
    per_year_stats(eq_a, "Strategy A")

    print("\nRunning naive baseline (no regime gate / quality / inv-vol / banding)...")
    naive_cfg = dict(cfg)
    naive_cfg.update(use_regime_gate=False, use_quality_filter=False,
                      use_banding=False, weighting="equal")
    eq_b, log_b = run_backtest(data, bench, regime_on, rebal_dates, naive_cfg)
    stats_b = engine.perf_stats(eq_b, "BASELINE: Naive equal-weight top-10 momentum")
    print(f"  Rebalances: {len(log_b)}, total cost paid: "
          f"{log_b['cost'].sum():,.0f} ({log_b['cost'].sum()/cfg['starting_capital']*100:.2f}% of starting capital)")
    per_year_stats(eq_b, "Naive baseline")

    bh = engine.buy_and_hold(bench, cfg["starting_capital"]).reindex(eq_a.index).ffill()
    stats_bh = engine.perf_stats(bh, f"BASELINE: Buy & Hold {cfg['benchmark']}")
    per_year_stats(bh, "Buy & hold")

    print("\n=== REGIME-OFF DIAGNOSTIC ===")
    regime_off_diagnostic(eq_a, regime_on, "Strategy A")
    regime_off_diagnostic(eq_b, regime_on, "Naive baseline")
    regime_off_diagnostic(bh, regime_on, "Buy & hold")

    print("\n=== VERDICT ===")
    for name, s in [("Strategy A", stats_a), ("Naive baseline", stats_b)]:
        beat_bh_cagr = s["cagr"] > stats_bh["cagr"]
        beat_bh_sharpe = (s["sharpe"] > stats_bh["sharpe"]
                          if not np.isnan(s["sharpe"]) and not np.isnan(stats_bh["sharpe"]) else False)
        beat_bh_dd = s["max_dd"] > stats_bh["max_dd"]
        print(f"  {name}: beat B&H CAGR? {'YES' if beat_bh_cagr else 'NO'}  "
              f"beat B&H Sharpe? {'YES' if beat_bh_sharpe else 'NO'}  "
              f"shallower DD? {'YES' if beat_bh_dd else 'NO'}")
    print("\n  This is a single full-sample run with no held-out period and no")
    print("  parameter sweep -- it tells you whether the premise is even alive,")
    print("  not whether it survives validation. Treat accordingly, and remember")
    print("  survivorship bias inflates all of these numbers somewhat.")


if __name__ == "__main__":
    main()
