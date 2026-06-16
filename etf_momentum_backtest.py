"""
Strategy C — Multi-Asset ETF Dual-Momentum Rotation ("Marketfighter" menu).

Implements ETF_MOMENTUM_SPEC_2.md sections 2-7:
  - Ranking: trailing LOOKBACK total return (or 3/6/12m composite percentile
    rank if COMPOSITE=True).
  - Absolute momentum gate: a risk asset is eligible only if its LOOKBACK
    return beats the cash proxy's (or > 0 if ABS_BENCHMARK == "zero").
  - Global macro regime gate (use_global_regime_gate, default True): a
    portfolio-level overlay on top of the per-asset gate above. If IWDA.L's
    trailing LOOKBACK return <= IBTS.L's (cash proxy), the WHOLE portfolio is
    forced into the cash proxy at that rebalance, bypassing individual-asset
    relative-momentum ranking entirely. Intended to reduce whipsaw drawdowns
    during broad market downtrends, where individual assets can keep hovering
    just above/below their own cash hurdle while the market overall is weak.
  - Selection: top HOLD_N eligible assets, inverse-vol (126d) weighted,
    subject to MAX_PER_BLOCK caps (sectors, factors, regions+EM combined).
  - Unfilled slots -> defensive govt bond (if it passes the abs-momentum
    gate) -> else cash proxy (0% return, idle).
  - Monthly rebalance: signal at month-end CLOSE, executed at the next
    session's OPEN (no look-ahead), following momentum_backtest.py's pattern.
  - Costs: COST_PER_SIDE per side (with a per-ticker override for the
    silver ETC, which has wider spreads), plus a daily TER drag per holding.

Universe: etf_universe.csv (26 tickers: 4 regions, 9 sectors, 5 factors,
2 EM, 2 metals, 1 defensive bond, 1 cash proxy, 1 baseline B&H).
Data: etf_ohlc.sqlite3 (built by build_etf_price_db.py).

HONEST CAVEATS
  - DFNS.L (Defense) was dropped from the menu: it only had data from
    2023-03-31, a severe outlier vs. the rest of the menu (~2014-2018),
    and would have been a permanent no-op (never eligible) for ~95% of
    the backtest history anyway.
  - The backtest START date is set to the latest first-available-date
    across all risk + defensive + cash tickers (excluding the DFNS outlier)
    plus ~1y (252 trading days) warmup for the 12m lookback. That is
    IUCM.L (Communication Sector, first=2018-09-17) -> start ~2019-10-01.
  - Nordic region uses ^OMX (an index, not a tradable ETF) as a proxy --
    flagged in etf_universe.csv.
  - "Growth" factor (Block 3) has no clean MSCI World Growth-factor UCITS
    ETF on yfinance; EQQQ.L (Invesco EQQQ Nasdaq-100 UCITS) is used as a
    growth-style substitute -- flagged in etf_universe.csv.
  - Cash proxy uses IBTS.L (iShares $ Treasury 1-3yr UCITS), since the
    truer 0-1yr proxy (IB01.L) only has data from 2019 and would force a
    much later start date -- flagged in etf_universe.csv.

Requires: pip install pandas numpy
Run:      python etf_momentum_backtest.py
"""

import numpy as np
import pandas as pd

import price_db
import backtest_engine as engine


# ============================ CONFIG ============================
CONFIG = {
    "db_path": "etf_ohlc.sqlite3",
    "universe_csv": "etf_universe.csv",

    "start": "2019-10-01",
    "end": None,

    # --- ranking ---
    "lookback_days": 252,
    "composite": False,            # if True: avg percentile rank of 3/6/12m returns
    "composite_horizons": {"ret_3m": 63, "ret_6m": 126, "ret_12m": 252},

    # --- absolute momentum gate ---
    "abs_benchmark": "cash_proxy",  # "cash_proxy" | "zero"

    # --- global macro regime gate (portfolio-level overlay) ---
    # When True: if IWDA.L's trailing LOOKBACK return <= IBTS.L's (cash proxy),
    # force the WHOLE portfolio into the cash proxy at this rebalance,
    # bypassing individual-asset relative-momentum ranking entirely. When
    # False: fall back to the original per-asset absolute-momentum gate only.
    "use_global_regime_gate": True,

    # --- selection & weighting ---
    "hold_n": 4,
    "weighting": "inv_vol",         # "inv_vol" | "equal"
    "vol_window": 126,
    "vol_target": None,             # TODO: per-asset risk-contribution cap (not implemented)

    # MAX_PER_BLOCK: cap how many of hold_n slots may come from a block-group.
    # block-groups map several CSV `block` values -> a single cap.
    "max_per_block": {
        "sector": 2,                # Block 2 (10 GICS sectors + Defense)
        "factor": 2,                # Block 3 (5 factors)
        "region_em": 2,             # Block 1 (regions) + Block 4 (EM) combined
    },
    "use_max_per_block": True,

    # --- rebalancing ---
    "rebal": "monthly",             # "monthly" | "quarterly"
    "band": False,                  # hysteresis (not implemented; default off)

    # --- costs ---
    "cost_per_side": 0.0015,        # 0.15% commission + spread + slippage, default
    "cost_per_side_overrides": {
        "PHAG.L": 0.0030,           # silver ETC: wider spreads
    },

    # --- TER drag (annualized, subtracted daily from each holding's return) ---
    # Documented assumptions:
    #   - broad regional equity (Block 1): ~0.07% (IWDA/CSPX/IMEU/CPXJ-class)
    #   - sector / factor / EM (Blocks 2-4): ~0.20-0.40%
    #   - gold/silver ETC (Block 5): ~0.12-0.25%
    #   - defensive govt bond / cash proxy: ~0.10-0.20%
    "ter": {
        "^OMX": 0.0000,    # index proxy, no fund fee (caveat: not actually tradable)
        "IMEU.L": 0.0012,
        "CSPX.L": 0.0007,
        "CPXJ.L": 0.0020,
        "IITU.L": 0.0015,
        "IUHC.L": 0.0015,
        "IUFS.L": 0.0015,
        "IUES.L": 0.0015,
        "IUIS.L": 0.0015,
        "IUCS.L": 0.0015,
        "IUCD.L": 0.0015,
        "IUUS.L": 0.0015,
        "IUMS.L": 0.0015,
        "IUCM.L": 0.0015,
        "IWVL.L": 0.0030,
        "IWQU.L": 0.0030,
        "IWMO.L": 0.0030,
        "EQQQ.L": 0.0030,
        "MVOL.L": 0.0030,
        "CEMA.L": 0.0040,
        "LTAM.L": 0.0074,
        "PHAU.L": 0.0015,
        "PHAG.L": 0.0049,
        "SEGA.L": 0.0010,
        "IBTS.L": 0.0007,
        "IWDA.L": 0.0020,
    },

    "starting_capital": 100_000.0,
}

DEFENSIVE_TICKER = "SEGA.L"
CASH_TICKER = "IBTS.L"
BASELINE_TICKER = "IWDA.L"

# Map CSV `block` -> block-group key used by max_per_block
BLOCK_GROUP = {
    "region": "region_em",
    "em": "region_em",
    "sector": "sector",
    "factor": "factor",
    "metal": None,          # no cap
}


# ============================ DATA ============================
def load_data(tickers, start, end, cfg):
    data = {}
    conn = price_db.get_connection(cfg["db_path"])
    try:
        for t in tickers:
            df = price_db.load_prices(t, start=start, end=end, conn=conn)
            if df is None or df.empty:
                continue
            data[t] = df
    finally:
        conn.close()
    return data


def add_indicators(df, cfg):
    close = df["Close"]
    lb = cfg["lookback_days"]

    df["ret_lb"] = close / close.shift(lb) - 1.0

    if cfg["composite"]:
        for name, h in cfg["composite_horizons"].items():
            df[name] = close / close.shift(h) - 1.0

    daily_ret = close.pct_change()
    df["vol"] = daily_ret.rolling(cfg["vol_window"]).std()
    return df


def month_end_dates(index):
    s = pd.Series(index, index=index)
    return pd.DatetimeIndex(s.groupby([index.year, index.month]).last().values)


def quarter_end_dates(index):
    s = pd.Series(index, index=index)
    return pd.DatetimeIndex(s.groupby([index.year, (index.quarter)]).last().values)


# ============================ SELECTION ============================
def score_assets(snapshot, cfg):
    """Return a Series of scores (higher = better) indexed by ticker."""
    if cfg["composite"]:
        cols = list(cfg["composite_horizons"].keys())
        df = snapshot.dropna(subset=cols)
        if df.empty:
            return pd.Series(dtype=float)
        for c in cols:
            df[c + "_pct"] = df[c].rank(pct=True)
        return df[[c + "_pct" for c in cols]].mean(axis=1)
    else:
        return snapshot["ret_lb"].dropna()


def select_portfolio(snapshot, risk_tickers, blocks, cfg, use_abs_filter=True,
                      exclude_blocks=None):
    """
    snapshot: DataFrame indexed by ticker, columns include ret_lb / composite
              horizon cols, vol.
    risk_tickers: list of candidate risk-asset tickers (subset of universe).
    blocks: dict ticker -> CSV `block` value.
    Returns dict ticker -> weight (sums to 1, or empty if everything fails
    to cash -- caller handles defensive/cash fallback).
    """
    exclude_blocks = exclude_blocks or set()
    candidates = [t for t in risk_tickers if blocks.get(t) not in exclude_blocks]

    scores = score_assets(snapshot.loc[snapshot.index.isin(candidates)], cfg)
    if scores.empty:
        return {}, []

    ranked = scores.sort_values(ascending=False)

    # absolute momentum gate
    if use_abs_filter:
        if cfg["abs_benchmark"] == "zero":
            hurdle = 0.0
        else:
            cash_ret = snapshot.loc[CASH_TICKER, "ret_lb"] if CASH_TICKER in snapshot.index else np.nan
            hurdle = cash_ret if not np.isnan(cash_ret) else 0.0
        eligible_mask = snapshot.loc[ranked.index, "ret_lb"] > hurdle
        eligible = list(ranked.index[eligible_mask.values])
    else:
        eligible = list(ranked.index)

    # apply block caps while filling hold_n slots
    hold_n = cfg["hold_n"]
    selected = []
    block_counts = {}
    for t in eligible:
        if len(selected) >= hold_n:
            break
        grp = BLOCK_GROUP.get(blocks.get(t))
        if cfg["use_max_per_block"] and grp is not None:
            cap = cfg["max_per_block"].get(grp, hold_n)
            if block_counts.get(grp, 0) >= cap:
                continue
            block_counts[grp] = block_counts.get(grp, 0) + 1
        selected.append(t)

    if not selected:
        return {}, []

    # inverse-vol weighting
    if cfg["weighting"] == "inv_vol":
        vols = snapshot.loc[selected, "vol"].replace(0, np.nan)
        inv = 1.0 / vols
        if inv.isna().any():
            inv = inv.fillna(inv.mean())
        weights = inv / inv.sum()
    else:
        weights = pd.Series(1.0 / len(selected), index=selected)

    n_filled = len(selected)
    return weights.to_dict(), [n_filled, hold_n]


def fill_unfilled(weights, n_filled, hold_n, snapshot, cfg):
    """Allocate (hold_n - n_filled) slots to defensive bond, else cash.
    Returns final weights dict (sums to 1) and a flag for what got used."""
    remaining = hold_n - n_filled
    if remaining <= 0:
        return weights, "none"

    frac = remaining / hold_n
    # check defensive bond eligibility (abs momentum gate)
    defensive_ok = False
    if DEFENSIVE_TICKER in snapshot.index:
        if cfg["abs_benchmark"] == "zero":
            hurdle = 0.0
        else:
            hurdle = snapshot.loc[CASH_TICKER, "ret_lb"] if CASH_TICKER in snapshot.index else 0.0
        def_ret = snapshot.loc[DEFENSIVE_TICKER, "ret_lb"]
        defensive_ok = (not np.isnan(def_ret)) and (not np.isnan(hurdle)) and (def_ret > hurdle)

    # scale existing weights down to (1 - frac)
    scaled = {t: w * (1 - frac) for t, w in weights.items()}

    if defensive_ok:
        scaled[DEFENSIVE_TICKER] = scaled.get(DEFENSIVE_TICKER, 0.0) + frac
        used = "defensive"
    else:
        # cash: simply don't allocate (idle cash, 0% return)
        used = "cash"

    return scaled, used


# ============================ BACKTEST LOOP ============================
def run_backtest(data, blocks, all_dates, rebal_dates, cfg, mode="full"):
    """
    mode: "full"      - Strategy C, full universe, abs-momentum filter on
          "naive"     - no abs-momentum filter (always fill hold_n from top risk)
          "no_tilts"  - exclude sector + factor blocks from rotation universe
    Returns: equity series, rebalance log, defensive/cash time fraction.
    """
    cash_bal = cfg["starting_capital"]
    shares = {}
    equity_curve = []
    rebal_log = []
    pending = None
    rebal_set = set(rebal_dates)
    risk_blocks_all = {"region", "sector", "factor", "em", "metal"}

    if mode == "no_tilts":
        exclude_blocks = {"sector", "factor"}
    else:
        exclude_blocks = set()

    use_abs_filter = (mode != "naive")

    defensive_cash_days = 0
    total_days = 0

    for d in all_dates:
        # ---- execute pending rebalance at today's open ----
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
                    turnover_value += shares[t] * open_px.get(t, 0.0)

            # per-ticker cost overrides
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

        # ---- mark to market at close (apply TER drag) ----
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
        # fraction of NAV in defensive/cash today
        nav_today = cash_bal + held
        if nav_today > 0:
            def_val = shares.get(DEFENSIVE_TICKER, 0.0) * data[DEFENSIVE_TICKER]["Close"].reindex(all_dates).ffill().loc[d] if DEFENSIVE_TICKER in shares else 0.0
            risk_val = held - def_val
            cash_frac = cash_bal / nav_today
            if (def_val / nav_today) + cash_frac > 0.5:
                defensive_cash_days += 1

        # ---- compute signal at close of a rebalance date ----
        if d in rebal_set:
            rows = {}
            for t, df in data.items():
                if d not in df.index:
                    continue
                row = df.loc[d]
                if np.isnan(row.get("ret_lb", np.nan)):
                    continue
                entry = {"ret_lb": row["ret_lb"], "vol": row["vol"]}
                if cfg["composite"]:
                    for c in cfg["composite_horizons"]:
                        entry[c] = row.get(c, np.nan)
                rows[t] = entry
            if not rows:
                pending = {}
                continue
            snapshot = pd.DataFrame(rows).T

            # ---- global macro regime gate (portfolio-level override) ----
            if cfg.get("use_global_regime_gate", True):
                iwda_ret = snapshot.loc[BASELINE_TICKER, "ret_lb"] if BASELINE_TICKER in snapshot.index else np.nan
                cash_ret = snapshot.loc[CASH_TICKER, "ret_lb"] if CASH_TICKER in snapshot.index else np.nan
                if not np.isnan(iwda_ret) and not np.isnan(cash_ret) and iwda_ret <= cash_ret:
                    pending = {CASH_TICKER: 1.0}
                    continue

            risk_tickers = [t for t, b in blocks.items() if b in risk_blocks_all and t in snapshot.index]

            weights, fill_info = select_portfolio(
                snapshot, risk_tickers, blocks, cfg,
                use_abs_filter=use_abs_filter, exclude_blocks=exclude_blocks)

            if fill_info:
                n_filled, hold_n = fill_info
                weights, _used = fill_unfilled(weights, n_filled, hold_n, snapshot, cfg)
            # if weights empty -> all cash (pending = {})

            pending = weights

    # apply TER drag to the equity curve post-hoc is not accurate per-holding;
    # instead apply it inline below by adjusting daily returns of the equity
    # curve using realized holdings -- recompute via a second pass.
    eq = pd.Series({d: v for d, v in equity_curve}).sort_index()
    def_cash_frac = defensive_cash_days / total_days if total_days else 0.0
    return eq, pd.DataFrame(rebal_log, columns=["date", "n_holdings", "cost"]), def_cash_frac


# ============================ TER-ADJUSTED PRICE SERIES ============================
def build_ter_adjusted_data(data, cfg):
    """Return a copy of `data` where each ticker's Close/Open are scaled down
    by its daily TER drag, applied multiplicatively from the first valid date.
    This keeps the rest of the pipeline (which reads Close/Open) unchanged."""
    adj = {}
    for t, df in data.items():
        ter = cfg["ter"].get(t, 0.0020)  # default 0.20% if unlisted
        daily_drag = ter / 252.0
        n = len(df)
        factor = (1.0 - daily_drag) ** np.arange(n)
        df2 = df.copy()
        for col in ["Open", "High", "Low", "Close"]:
            df2[col] = df2[col].values * factor
        adj[t] = df2
    return adj


# ============================ MAIN ============================
def main():
    cfg = CONFIG
    universe_df = pd.read_csv(cfg["universe_csv"])
    blocks = dict(zip(universe_df["ticker"], universe_df["block"]))
    roles = dict(zip(universe_df["ticker"], universe_df["role"]))

    all_tickers = list(universe_df["ticker"])

    print("Loading price data...")
    raw_data = load_data(all_tickers, start="2005-01-01", end=cfg["end"], cfg=cfg)
    print(f"  {len(raw_data)} tickers loaded.")

    print("Applying TER drag...")
    data = build_ter_adjusted_data(raw_data, cfg)

    print("Computing indicators...")
    for t in data:
        data[t] = add_indicators(data[t], cfg)

    # restrict to backtest window
    for t in data:
        data[t] = data[t].loc[data[t].index >= pd.Timestamp(cfg["start"])]
        if cfg["end"]:
            data[t] = data[t].loc[data[t].index <= pd.Timestamp(cfg["end"])]

    # all_dates = union of trading days across the universe (use baseline as calendar)
    bench_dates = data[BASELINE_TICKER].index
    all_dates = bench_dates

    if cfg["rebal"] == "monthly":
        rebal_dates = month_end_dates(all_dates)
    else:
        rebal_dates = quarter_end_dates(all_dates)
    # need lookback warmup
    min_lb = cfg["lookback_days"]
    if len(all_dates) > min_lb:
        min_start = all_dates[min_lb]
        rebal_dates = rebal_dates[rebal_dates >= min_start]

    print(f"\nBacktest window: {all_dates[0].date()} -> {all_dates[-1].date()}")
    print(f"Rebalances: {len(rebal_dates)}")

    results = {}

    print("\nRunning Strategy C (full)...")
    eq_c, log_c, dc_c = run_backtest(data, blocks, all_dates, rebal_dates, cfg, mode="full")
    results["Strategy C (full)"] = (eq_c, log_c, dc_c)

    print("Running baseline (a) Buy & Hold IWDA...")
    bh = engine.buy_and_hold(raw_data[BASELINE_TICKER].loc[raw_data[BASELINE_TICKER].index >= pd.Timestamp(cfg["start"])],
                              cfg["starting_capital"]).reindex(all_dates).ffill()
    results["(a) Buy & Hold IWDA"] = (bh, None, 0.0)

    print("Running baseline (b) Static 60/40...")
    eq_6040, log_6040 = run_static_alloc(data, all_dates, rebal_dates, cfg,
                                          weights={BASELINE_TICKER: 0.6, DEFENSIVE_TICKER: 0.4})
    results["(b) Static 60/40"] = (eq_6040, log_6040, 0.0)

    print("Running baseline (c) Naive relative momentum (no abs-mom filter)...")
    eq_naive, log_naive, dc_naive = run_backtest(data, blocks, all_dates, rebal_dates, cfg, mode="naive")
    results["(c) Naive relative momentum"] = (eq_naive, log_naive, dc_naive)

    print("Running baseline (d) Full strategy WITHOUT sector+factor tilts...")
    eq_notilt, log_notilt, dc_notilt = run_backtest(data, blocks, all_dates, rebal_dates, cfg, mode="no_tilts")
    results["(d) No sector/factor tilts"] = (eq_notilt, log_notilt, dc_notilt)

    # ---- print results table ----
    print("\n" + "=" * 100)
    print(f"{'Strategy':<32}{'CAGR':>8}{'Sharpe':>8}{'AnnVol':>8}{'MaxDD':>8}{'%Def/Cash':>10}{'TotalCost':>12}")
    print("-" * 100)
    for name, (eq, log, dc) in results.items():
        stats = engine.perf_stats(eq, label=None, print_report=False)
        total_cost = log["cost"].sum() if log is not None and not log.empty else 0.0
        cost_pct = total_cost / cfg["starting_capital"] * 100
        print(f"{name:<32}{stats['cagr']*100:7.2f}%{stats['sharpe']:8.2f}"
              f"{stats['ann_vol']*100:7.2f}%{stats['max_dd']*100:7.2f}%{dc*100:9.1f}%{cost_pct:11.2f}%")
    print("=" * 100)

    print("\nDetailed reports:")
    for name, (eq, log, dc) in results.items():
        engine.perf_stats(eq, label=name)


def run_static_alloc(data, all_dates, rebal_dates, cfg, weights):
    """Simple static-weight portfolio, rebalanced monthly, with costs/TER
    already baked into `data` (TER-adjusted) and cost_per_side on rebalances."""
    cash_bal = cfg["starting_capital"]
    shares = {}
    equity_curve = []
    rebal_log = []
    pending_first = True
    rebal_set = set(rebal_dates)

    for d in all_dates:
        do_rebal = pending_first or d in rebal_set
        if do_rebal:
            value = cash_bal
            open_px = {}
            for t in weights:
                df = data[t]
                if d in df.index:
                    open_px[t] = df.loc[d, "Open"]
                else:
                    open_px[t] = df["Close"].reindex(all_dates).ffill().loc[d]
                value += shares.get(t, 0.0) * open_px[t]

            turnover_value = 0.0
            new_shares = {}
            for t, w in weights.items():
                px = open_px[t]
                target_val = value * w
                cur_val = shares.get(t, 0.0) * px
                turnover_value += abs(target_val - cur_val)
                new_shares[t] = target_val / px

            cost = turnover_value * cfg["cost_per_side"]
            invested = sum(new_shares[t] * open_px[t] for t in new_shares)
            cash_bal = value - invested - cost
            shares = new_shares
            rebal_log.append((d, cost))
            pending_first = False

        held = 0.0
        for t, sh in shares.items():
            df = data[t]
            if d in df.index:
                px = df.loc[d, "Close"]
            else:
                px = df["Close"].reindex(all_dates).ffill().loc[d]
            held += sh * px
        equity_curve.append((d, cash_bal + held))

    eq = pd.Series({d: v for d, v in equity_curve}).sort_index()
    return eq, pd.DataFrame(rebal_log, columns=["date", "cost"])


if __name__ == "__main__":
    main()
