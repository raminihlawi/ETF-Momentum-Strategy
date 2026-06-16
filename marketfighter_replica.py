"""
Strategy D — "Marketfighter" replica.

Replicates, as closely as the published description allows, the strategy
described in:
  https://www.marketfighter.com/p/my-investment-approach-that-outperformed

The article's own description (exact parameters are NOT published --
"proprietary"):
  - Two parallel sleeves, 50% each:
      (1) Factor rotation: hold the single factor ETF (from Value, Momentum,
          Quality, Size) with the best trailing momentum.
      (2) Sector rotation: hold the single sector ETF with the best trailing
          momentum.
  - Monthly rebalance ("at the turn of each month").
  - 12-month momentum mentioned as "for instance" (kept proprietary, exact
    lookback not given) -- we use 252 trading days (~12m), consistent with
    Strategy C's default and the article's own example.
  - A market-level absolute-momentum / regime filter moves the WHOLE
    portfolio to cash when the market itself is in a downtrend. The article
    states the live system was invested ~93% of the time -- we approximate
    this with the same cash_proxy-relative absolute-momentum gate used in
    Strategy C, applied to the baseline global-equity ETF (IWDA.L).
  - Author's claimed results (NOT independently reproducible -- different
    universe, region, period, and "proprietary" parameters):
      2000-2025: strategy CAGR 16.21% vs World Index 3.84% (World Index
        figure looks like a price-return, non-total-return number -- treat
        the comparison with suspicion).
      2016-2025: strategy CAGR 20.16% vs World Index 9.44%.
      Beat the index 25 of 26 years; worst relative year -1.18% (2012).
      2000-2020 backtested, 2021-2025 claimed as actual live trading.

HONEST CAVEATS
  - This is a REPLICA OF THE DESCRIBED MECHANISM, not the actual strategy --
    the exact tickers, lookback window, and regime-filter rule are not
    published. Differences here (universe = etf_universe.csv's 10 sector +
    6 factor ETFs incl. WSML.L as the Size proxy, 252d lookback, cash_proxy
    gate) are documented choices, not the author's.
  - Same short backtest window as Strategy C (~6.7 years, 2019-10 to
    2026-06), for the same data-availability reasons (see
    etf_momentum_backtest.py header). The article's headline numbers are
    over 2000-2025 / 2016-2025 -- a MUCH longer period we cannot replicate
    with this universe's data history. Any comparison to the article's
    16-20% CAGR claims is therefore not apples-to-apples.
  - "Size" factor uses WSML.L (iShares MSCI World Small Cap) as a proxy --
    not a pure "Size factor" index fund, but the closest available on
    yfinance.
  - No within-sleeve weighting beyond 100% concentration in the single
    top-ranked asset (as described) -- this is HIGH single-asset
    concentration risk per sleeve, by design of the replicated mechanism.

Requires: pip install pandas numpy
Run:      python marketfighter_replica.py
"""

import numpy as np
import pandas as pd

import backtest_engine as engine
import etf_momentum_backtest as eb


# ============================ CONFIG ============================
CONFIG = dict(eb.CONFIG)
CONFIG.update({
    "lookback_days": 252,           # "12 months for instance" per the article
    "abs_benchmark": "cash_proxy",  # regime filter gate, applied to IWDA.L
    "rebal": "monthly",
})

FACTOR_TICKERS = ["IWVL.L", "IWQU.L", "IWMO.L", "WSML.L"]   # Value, Quality, Momentum, Size
SECTOR_TICKERS = ["IITU.L", "IUHC.L", "IUFS.L", "IUES.L", "IUIS.L",
                  "IUCS.L", "IUCD.L", "IUUS.L", "IUMS.L", "IUCM.L"]


# ============================ "SECRET SAUCE" MOMENTUM METRICS ============================
def add_secret_sauce_indicators(df, cfg):
    """Add columns for the 4 alternative momentum-scoring definitions used by
    the marketfighter_sweep2.py parameter sweep, all computed relative to
    cfg["lookback_days"] (except sma200_dist, which is always a 200-day SMA):

      - ret_skip1   : "12-1" momentum -- trailing return from t-lookback to
                      t-21 (skips the most recent ~1 month of mean-reverting
                      noise).
      - r2_lb       : R^2 of a linear fit of Close vs. time over the trailing
                      `lookback` window (trend smoothness quality).
      - frog_lb     : "frog in the pan" / information discreteness --
                      sign(ret_lb) * (n_up_days - n_down_days) / n_total_days
                      over the trailing `lookback` window.
      - sma200_dist : (Close - SMA200) / SMA200 -- extension above/below the
                      200-day moving average.
    """
    close = df["Close"]
    lb = cfg["lookback_days"]
    daily_ret = close.pct_change()

    df["ret_skip1"] = close.shift(21) / close.shift(lb) - 1.0

    def _r2(arr):
        if np.any(np.isnan(arr)):
            return np.nan
        x = np.arange(len(arr))
        return np.corrcoef(x, arr)[0, 1] ** 2

    df["r2_lb"] = close.rolling(lb).apply(_r2, raw=True)

    sign_daily = np.sign(daily_ret)
    df["frog_lb"] = np.sign(df["ret_lb"]) * sign_daily.rolling(lb).sum() / lb

    sma200 = close.rolling(200).mean()
    df["sma200_dist"] = (close - sma200) / sma200

    return df


# ============================ SELECTION ============================
def best_of(snapshot, tickers):
    """Return the ticker with the highest ret_lb among `tickers` present in
    `snapshot` with a non-NaN ret_lb, or None."""
    cands = [t for t in tickers if t in snapshot.index and not np.isnan(snapshot.loc[t, "ret_lb"])]
    if not cands:
        return None
    rets = snapshot.loc[cands, "ret_lb"]
    return rets.idxmax()


def regime_ok(snapshot, cfg):
    """Market-level absolute-momentum gate, applied to the baseline global
    equity ETF (IWDA.L) vs the cash proxy (or zero)."""
    if eb.BASELINE_TICKER not in snapshot.index:
        return True
    mkt_ret = snapshot.loc[eb.BASELINE_TICKER, "ret_lb"]
    if np.isnan(mkt_ret):
        return True
    if cfg["abs_benchmark"] == "zero":
        hurdle = 0.0
    else:
        hurdle = snapshot.loc[eb.CASH_TICKER, "ret_lb"] if eb.CASH_TICKER in snapshot.index else 0.0
        if np.isnan(hurdle):
            hurdle = 0.0
    return mkt_ret > hurdle


def select_weights(snapshot, cfg):
    """50% best factor ETF + 50% best sector ETF, or 100% cash if the
    market-level regime filter is off."""
    if not regime_ok(snapshot, cfg):
        return {}, "cash"

    best_factor = best_of(snapshot, FACTOR_TICKERS)
    best_sector = best_of(snapshot, SECTOR_TICKERS)

    weights = {}
    if best_factor is not None:
        weights[best_factor] = weights.get(best_factor, 0.0) + 0.5
    if best_sector is not None:
        weights[best_sector] = weights.get(best_sector, 0.0) + 0.5

    if not weights:
        return {}, "cash"

    used = "invested" if sum(weights.values()) >= 0.999 else "partial"
    return weights, used


# ============================ BACKTEST LOOP ============================
def run_backtest(data, all_dates, rebal_dates, cfg):
    cash_bal = cfg["starting_capital"]
    shares = {}
    equity_curve = []
    rebal_log = []
    pending = None
    rebal_set = set(rebal_dates)

    defensive_cash_days = 0
    total_days = 0

    for d in all_dates:
        if pending is not None:
            value = cash_bal
            open_px = {}
            for t in set(list(shares.keys()) + list(pending.keys())):
                df = data[t]
                if d in df.index:
                    open_px[t] = df.loc[d, "Open"]
                else:
                    open_px[t] = df["Close"].reindex(all_dates).ffill().loc[d]
            for t in shares:
                value += shares[t] * open_px.get(t, 0.0)

            new_shares = {}
            for t, w in pending.items():
                px = open_px.get(t)
                if px is None or np.isnan(px) or px <= 0:
                    continue
                new_shares[t] = (value * w) / px

            cost = 0.0
            touched = set(list(shares.keys()) + list(new_shares.keys()))
            for t in touched:
                old_val = shares.get(t, 0.0) * open_px.get(t, 0.0)
                new_val = new_shares.get(t, 0.0) * open_px.get(t, 0.0)
                delta = abs(new_val - old_val)
                rate = cfg["cost_per_side_overrides"].get(t, cfg["cost_per_side"])
                cost += delta * rate

            invested = sum(new_shares[t] * open_px[t] for t in new_shares)
            cash_bal = value - invested - cost
            shares = new_shares
            rebal_log.append((d, len(shares), cost))
            pending = None

        held = 0.0
        for t, sh in shares.items():
            df = data[t]
            if d in df.index:
                px = df.loc[d, "Close"]
            else:
                px = df["Close"].reindex(all_dates).ffill().loc[d]
            held += sh * px
        equity_curve.append((d, cash_bal + held))

        total_days += 1
        nav_today = cash_bal + held
        if nav_today > 0 and (cash_bal / nav_today) > 0.5:
            defensive_cash_days += 1

        if d in rebal_set:
            rows = {}
            for t, df in data.items():
                if d not in df.index:
                    continue
                row = df.loc[d]
                if np.isnan(row.get("ret_lb", np.nan)):
                    continue
                rows[t] = {"ret_lb": row["ret_lb"], "vol": row["vol"]}
            if not rows:
                pending = {}
                continue
            snapshot = pd.DataFrame(rows).T
            weights, _used = select_weights(snapshot, cfg)
            pending = weights

    eq = pd.Series({d: v for d, v in equity_curve}).sort_index()
    cash_frac = defensive_cash_days / total_days if total_days else 0.0
    return eq, pd.DataFrame(rebal_log, columns=["date", "n_holdings", "cost"]), cash_frac


# ============================ MAIN ============================
def main():
    cfg = CONFIG
    universe_df = pd.read_csv(cfg["universe_csv"])
    all_tickers = list(universe_df["ticker"])

    print("Loading price data...")
    raw_data = eb.load_data(all_tickers, start="2005-01-01", end=cfg["end"], cfg=cfg)
    print(f"  {len(raw_data)} tickers loaded.")

    print("Applying TER drag...")
    data = eb.build_ter_adjusted_data(raw_data, cfg)

    print("Computing indicators...")
    for t in data:
        data[t] = eb.add_indicators(data[t], cfg)

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

    print(f"\nBacktest window: {all_dates[0].date()} -> {all_dates[-1].date()}")
    print(f"Rebalances: {len(rebal_dates)}")

    results = {}

    print("\nRunning Strategy D (Marketfighter replica)...")
    eq_d, log_d, cash_frac = run_backtest(data, all_dates, rebal_dates, cfg)
    results["Strategy D (Marketfighter replica)"] = (eq_d, log_d, cash_frac)

    print("Running baseline (a) Buy & Hold IWDA...")
    bh = engine.buy_and_hold(
        raw_data[eb.BASELINE_TICKER].loc[raw_data[eb.BASELINE_TICKER].index >= pd.Timestamp(cfg["start"])],
        cfg["starting_capital"]).reindex(all_dates).ffill()
    results["(a) Buy & Hold IWDA"] = (bh, None, 0.0)

    print("Running baseline (b) Static 60/40...")
    eq_6040, log_6040 = eb.run_static_alloc(
        data, all_dates, rebal_dates, cfg,
        weights={eb.BASELINE_TICKER: 0.6, eb.DEFENSIVE_TICKER: 0.4})
    results["(b) Static 60/40"] = (eq_6040, log_6040, 0.0)

    print("Running reference: Strategy C (full, from etf_momentum_backtest)...")
    blocks = dict(zip(universe_df["ticker"], universe_df["block"]))
    cfg_c = dict(eb.CONFIG)
    eq_c, log_c, dc_c = eb.run_backtest(data, blocks, all_dates, rebal_dates, cfg_c, mode="full")
    results["Strategy C (full, reference)"] = (eq_c, log_c, dc_c)

    print("\n" + "=" * 100)
    print(f"{'Strategy':<34}{'CAGR':>8}{'Sharpe':>8}{'AnnVol':>8}{'MaxDD':>8}{'%Cash':>8}{'TotalCost':>12}")
    print("-" * 100)
    for name, (eq, log, cf) in results.items():
        stats = engine.perf_stats(eq, label=None, print_report=False)
        total_cost = log["cost"].sum() if log is not None and not log.empty else 0.0
        cost_pct = total_cost / cfg["starting_capital"] * 100
        print(f"{name:<34}{stats['cagr']*100:7.2f}%{stats['sharpe']:8.2f}"
              f"{stats['ann_vol']*100:7.2f}%{stats['max_dd']*100:7.2f}%{cf*100:7.1f}%{cost_pct:11.2f}%")
    print("=" * 100)

    print("\nDetailed reports:")
    for name, (eq, log, cf) in results.items():
        engine.perf_stats(eq, label=name)

    # per-year returns for the replica
    print("\n--- Strategy D per-year returns ---")
    for year, grp in eq_d.groupby(eq_d.index.year):
        if len(grp) < 2:
            continue
        ret = grp.iloc[-1] / grp.iloc[0] - 1
        print(f"  {year}: {ret*100:7.2f}%")


if __name__ == "__main__":
    main()
