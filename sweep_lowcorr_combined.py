#!/usr/bin/env python3
"""
Low-Corr Combined Sweep
=======================
Permanent low-corr sector sleeve (Energy, Utilities, Cons.Staples,
Communications, Healthcare — no GLD, no IT/Industrials/Materials/Cons.Disc.)

Three metrics compared:
  1. raw          — 84d TER-adjusted return (new baseline)
  2. composite    — 50% 21d + 50% 84d return
  3. accel_ema3   — EMA(3) smoothed H+L/2, ROC(84d) + Accel(20d half-windows)

Tracks exact turnover and transaction counts.
Run from repo root:
    python3 sweep_lowcorr_combined.py [--quick]
"""

import sys
import logging
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ── Parameters ────────────────────────────────────────────────────────
START    = "2019-10-01"
DL_FROM  = "2004-01-01"
SEL_LB   = 84        # raw momentum lookback
REG_LB   = 84        # regime gate lookback
COST     = 0.0015    # 15 bps per side
CAPITAL  = 100_000

# Accelerated momentum params for this test (ema=3, win=20)
ACCEL_EMA    = 3
ACCEL_LB     = 84
ACCEL_WIN    = 20

REGIME_T  = "IWDA.L"
REGIME_CMP = "IBTS.L"
CASH_T    = "CASH"

CACHE_PATH = Path(__file__).parent / "dashboard/backend/_price_cache.pkl"

# ── Universes ─────────────────────────────────────────────────────────
FACTOR_SLEEVE = [
    ("USA MOM",   "QDVA.DE", 0.20),
    ("USA QUAL",  "QDVB.DE", 0.20),
    ("USA VAL",   "QDVI.DE", 0.20),
    ("USA SMALL", "SXRG.DE", 0.18),
    ("EUR MOM",   "CEMR.DE", 0.25),
    ("EUR QUAL",  "CEMQ.DE", 0.25),
    ("EUR VAL",   "CEMS.DE", 0.25),
    ("EUR SMALL", "XXSC.DE", 0.30),
]

# Original Low-Corr + IT (QDVE.DE)
LC_SECTOR_SLEEVE = [
    ("ENERGY",     "QDVF.DE", 0.15),
    ("HEALTHCARE", "QDVG.DE", 0.15),
    ("CONS STAP",  "2B7D.DE", 0.15),
    ("UTILITIES",  "QDVH.DE", 0.15),
    ("COMMS",      "XLC",     0.10),
    ("IT",         "QDVE.DE", 0.15),
]

TER_MAP = {
    **{t: ter for _, t, ter in FACTOR_SLEEVE},
    **{t: ter for _, t, ter in LC_SECTOR_SLEEVE},
    "IWDA.L": 0.20,
    "IBTS.L": 0.10,
}


# ── Price helpers ─────────────────────────────────────────────────────
def fetch_prices(use_cache: bool = False) -> dict:
    all_tickers = (
        [t for _, t, _ in FACTOR_SLEEVE]
        + [t for _, t, _ in LC_SECTOR_SLEEVE]
        + [REGIME_T, REGIME_CMP]
    )
    if use_cache and CACHE_PATH.exists():
        try:
            cached = pd.read_pickle(CACHE_PATH)
            if isinstance(cached, dict) and "close" in cached:
                # Verify all needed tickers present
                missing = [t for t in all_tickers if t not in cached["close"].columns]
                if not missing:
                    log.info("Using cached OHLC prices")
                    return cached
                log.info(f"Cache missing tickers: {missing} — re-downloading")
        except Exception:
            pass

    log.info(f"Downloading {len(all_tickers)} tickers...")
    raw = yf.download(all_tickers, start=DL_FROM, progress=False,
                      auto_adjust=True, threads=True)
    if isinstance(raw.columns, pd.MultiIndex):
        close = raw["Close"]
        high  = raw["High"]
        low   = raw["Low"]
    else:
        t0    = all_tickers[0]
        close = raw[["Close"]].rename(columns={"Close": t0})
        high  = raw[["High"]].rename(columns={"High": t0})
        low   = raw[["Low"]].rename(columns={"Low": t0})

    close, high, low = close.ffill(), high.ffill(), low.ffill()
    return {"close": close, "high": high, "low": low}


def apply_ter(prices: pd.DataFrame) -> pd.DataFrame:
    result = prices.copy().astype(float)
    for col in result.columns:
        ter_pct = TER_MAP.get(col, 0.0)
        if ter_pct > 0:
            daily_drag = (1 - ter_pct / 100) ** (1 / 252)
            result[col] *= daily_drag ** np.arange(len(result))
    return result


def compute_smooth(prices_high, prices_low, prices_close, ema_span: int) -> pd.DataFrame:
    strat_tickers = (
        [t for _, t, _ in FACTOR_SLEEVE]
        + [t for _, t, _ in LC_SECTOR_SLEEVE]
    )
    cols = [t for t in strat_tickers
            if t in prices_high.columns and t in prices_low.columns]
    median = (prices_high[cols] + prices_low[cols]) / 2
    for t in strat_tickers:
        if t not in cols and t in prices_close.columns:
            median[t] = prices_close[t]
    return apply_ter(median).ewm(span=ema_span, adjust=False).mean()


def month_end_dates(idx: pd.DatetimeIndex) -> set:
    s = pd.Series(idx, index=idx)
    ends = s.groupby(s.dt.to_period("M")).apply(lambda g: g.index[-1])
    return set(ends.values)


# ── Backtest with turnover tracking ───────────────────────────────────
def backtest(prices_adj: pd.DataFrame,
             factor_t: list,   # [(label, ticker), ...]
             sector_t: list,
             metric: str,
             smooth: pd.DataFrame = None) -> dict:
    """
    Returns dict with equity_curve, alloc_log, stats, and turnover metrics.
    """
    f_tickers = [t for _, t in factor_t]
    s_tickers = [t for _, t in sector_t]

    all_idx   = prices_adj.index
    rebal_set = month_end_dates(all_idx)
    pos_map   = {d: i for i, d in enumerate(all_idx)}

    warmup    = max(REG_LB, SEL_LB, 84)  # enough for all metrics
    sim_dates = all_idx[all_idx >= pd.Timestamp(START)]
    min_date  = all_idx[warmup] if len(all_idx) > warmup else all_idx[-1]

    cash_bal = float(CAPITAL)
    shares   = {}
    equity   = []
    alloc    = []
    pending  = None

    # Turnover tracking
    total_traded      = 0.0   # total $ traded (one-side: sells OR buys)
    rebal_events      = 0     # rebalances where ≥1 position changed
    trade_count       = 0     # count of individual ticker-level trades (changes)

    def price_at(ticker, d):
        if ticker == CASH_T:
            return 1.0
        if ticker in prices_adj.columns and d in prices_adj.index:
            v = prices_adj.loc[d, ticker]
            return float(v) if not np.isnan(v) else 0.0
        return 0.0

    def ret_lb(ticker, d, lb):
        if ticker == CASH_T:
            return 0.0
        pos = pos_map.get(d, -1)
        if pos < lb or ticker not in prices_adj.columns:
            return np.nan
        p0 = float(prices_adj.iloc[pos - lb][ticker])
        p1 = float(prices_adj.iloc[pos][ticker])
        return (p1 / p0 - 1) if p0 > 0 else np.nan

    def score(ticker, d):
        if ticker == CASH_T:
            return 0.0
        if metric == "composite":
            pos = pos_map.get(d, -1)
            if pos < 84 or ticker not in prices_adj.columns:
                return np.nan
            p_now = float(prices_adj.iloc[pos][ticker])
            p_21  = float(prices_adj.iloc[pos - 21][ticker])
            p_84  = float(prices_adj.iloc[pos - 84][ticker])
            if p_21 <= 0 or p_84 <= 0:
                return np.nan
            return 0.5 * (p_now / p_21 - 1) + 0.5 * (p_now / p_84 - 1)
        if metric == "accel":
            if smooth is None:
                return np.nan
            pos = pos_map.get(d, -1)
            min_pos = max(ACCEL_LB, 2 * ACCEL_WIN)
            if pos < min_pos or ticker not in smooth.columns:
                return np.nan
            try:
                p_now = float(smooth.iloc[pos][ticker])
                p_lb  = float(smooth.iloc[pos - ACCEL_LB][ticker])
                p_w   = float(smooth.iloc[pos - ACCEL_WIN][ticker])
                p_2w  = float(smooth.iloc[pos - 2 * ACCEL_WIN][ticker])
            except Exception:
                return np.nan
            if any(v <= 0 for v in [p_now, p_lb, p_w, p_2w]):
                return np.nan
            roc   = p_now / p_lb - 1
            accel = (p_now / p_w - 1) - (p_w / p_2w - 1)
            return roc + accel
        # raw
        return ret_lb(ticker, d, SEL_LB)

    for d in sim_dates:
        # ── Execute pending rebalance ────────────────────────────
        if pending is not None:
            all_t = set(shares) | set(pending)
            px    = {t: price_at(t, d) for t in all_t}

            value   = cash_bal + sum(shares.get(t, 0.0) * px.get(t, 0.0) for t in shares)
            new_sh  = {}
            for t, w in pending.items():
                p = px.get(t, 0.0)
                if p > 0:
                    new_sh[t] = (value * w) / p

            real_t  = {t for t in all_t if t != CASH_T}

            # Compute traded value per ticker (one-side: value change)
            this_traded = 0.0
            for t in real_t:
                old_val = shares.get(t, 0.0) * px.get(t, 0.0)
                new_val = new_sh.get(t, 0.0) * px.get(t, 0.0)
                delta   = abs(new_val - old_val)
                if delta > 1.0:   # ignore rounding noise (< $1)
                    this_traded += delta
                    trade_count += 1

            # Cost on gross traded (both sides), our delta already is half-round-trip
            # actual cost: COST per side, so each $1 change = $1 sell + $1 buy = 2×COST
            cost = sum(
                abs(new_sh.get(t, 0.0) * px.get(t, 0.0)
                    - shares.get(t, 0.0) * px.get(t, 0.0)) * COST
                for t in real_t
            )

            if this_traded > 0:
                rebal_events += 1
                total_traded += this_traded / 2  # one-side: count sells OR buys

            cash_bal = value - sum(new_sh[t] * px[t] for t in new_sh) - cost
            shares   = new_sh
            pending  = None

        # ── Mark to market ───────────────────────────────────────
        held  = sum(sh * price_at(t, d) for t, sh in shares.items())
        nav   = cash_bal + held
        equity.append({"date": d.strftime("%Y-%m-%d"), "value": round(nav, 2)})

        if d not in rebal_set or d < min_date:
            continue

        # ── Regime gate ──────────────────────────────────────────
        r_mkt = ret_lb(REGIME_T,   d, REG_LB)
        r_cmp = ret_lb(REGIME_CMP, d, REG_LB)
        if not np.isnan(r_mkt) and not np.isnan(r_cmp) and r_mkt <= r_cmp:
            pending = {CASH_T: 1.0}
            alloc.append({"date": d.strftime("%Y-%m-%d"), "holdings": {CASH_T: 1.0}})
            continue

        # ── Selection ────────────────────────────────────────────
        def top1(tickers):
            sc = {t: score(t, d) for t in tickers}
            sc = {t: v for t, v in sc.items() if not np.isnan(v)}
            return sorted(sc, key=sc.__getitem__, reverse=True)[:1]

        f_picks = top1(f_tickers)
        s_picks = top1(s_tickers)
        if not f_picks and not s_picks:
            continue

        w = {}
        for t in f_picks:
            w[t] = w.get(t, 0.0) + 0.5 / max(len(f_picks), 1)
        for t in s_picks:
            w[t] = w.get(t, 0.0) + 0.5 / max(len(s_picks), 1)

        pending = w
        alloc.append({"date": d.strftime("%Y-%m-%d"),
                      "holdings": {k: round(v, 4) for k, v in w.items()}})

    # ── Compute performance stats ────────────────────────────────
    dates  = pd.to_datetime([e["date"] for e in equity])
    values = np.array([e["value"] for e in equity], dtype=float)

    rets    = np.diff(values) / values[:-1]
    n_yrs   = (dates[-1] - dates[0]).days / 365.25
    cagr    = (values[-1] / values[0]) ** (1 / n_yrs) - 1 if n_yrs > 0 else 0.0
    ann_ret = np.mean(rets) * 252
    ann_vol = np.std(rets, ddof=1) * np.sqrt(252)
    sharpe  = ann_ret / ann_vol if ann_vol > 0 else 0.0

    mo_ends   = pd.Series(values, index=dates).resample("ME").last().values
    mo_peak   = np.maximum.accumulate(mo_ends)
    max_dd_mo = float(((mo_ends - mo_peak) / mo_peak).min()) if len(mo_ends) > 1 else 0.0

    avg_nav  = float(np.mean(values))
    # One-side annual turnover % = total_traded_one_side / (avg_nav * n_years) * 100
    turnover_pct = (total_traded / avg_nav / n_yrs * 100) if n_yrs > 0 else 0.0

    return {
        "cagr":           round(cagr * 100, 2),
        "sharpe":         round(sharpe, 2),
        "max_dd_mo":      round(max_dd_mo * 100, 2),
        "turnover_pct":   round(turnover_pct, 1),
        "rebal_events":   rebal_events,
        "trade_count":    trade_count,
        "n_years":        round(n_yrs, 2),
    }


# ── Main ─────────────────────────────────────────────────────────────
def main():
    use_cache = "--quick" in sys.argv

    prices_dict = fetch_prices(use_cache=use_cache)
    prices_raw  = prices_dict["close"]
    prices_high = prices_dict.get("high", prices_raw)
    prices_low  = prices_dict.get("low",  prices_raw)

    # Apply TER to strategy tickers
    strat_tickers = (
        [t for _, t, _ in FACTOR_SLEEVE]
        + [t for _, t, _ in LC_SECTOR_SLEEVE]
        + [REGIME_T, REGIME_CMP]
    )
    prices_adj = prices_raw.copy()
    strat_cols = [t for t in strat_tickers if t in prices_raw.columns]
    prices_adj[strat_cols] = apply_ter(prices_raw[strat_cols])

    # EMA(3) smoothed median prices for accel metric
    smooth_ema3 = compute_smooth(prices_high, prices_low, prices_raw, ema_span=ACCEL_EMA)

    factor_t = [(lbl, t) for lbl, t, _ in FACTOR_SLEEVE]
    sector_t = [(lbl, t) for lbl, t, _ in LC_SECTOR_SLEEVE]

    # Build smooth series for each unique ema span needed
    smooth_cache = {}
    def get_smooth(ema_span):
        if ema_span not in smooth_cache:
            smooth_cache[ema_span] = compute_smooth(prices_high, prices_low, prices_raw, ema_span)
        return smooth_cache[ema_span]

    configs = [
        ("LC-raw", "5-Sek Low-Corr Raw (lb=84) — ZPD5.DE baseline", "raw", None, None, None),
    ]

    results = {}
    for key, label, metric, smooth, ema, win in configs:
        log.info(f"Running {key}...")
        # Temporarily override module-level ACCEL params for this run
        global ACCEL_WIN, ACCEL_LB
        if win is not None:
            ACCEL_WIN = win
        results[key] = {"label": label, **backtest(prices_adj, factor_t, sector_t, metric, smooth)}
    ACCEL_WIN = 20   # restore

    # ── Print results ────────────────────────────────────────────
    n_years = results["LC-raw"]["n_years"]
    print()
    print("=" * 95)
    print("LOW-CORR + IT — original Low-Corr-universum utökat med QDVE.DE (IT)")
    print("Sector universe: Energy · Healthcare · Cons.Stap · QDVH.DE · XLC · IT (QDVE.DE)")
    print(f"Period: {START} – today  ({n_years:.1f} years)  |  Cost: {COST*10000:.0f} bps/side")
    print("=" * 95)
    print()

    hdr = ("| Konfiguration | CAGR (%) | Sharpe | Max DD (mo, %) "
           "| Turnover/år (%) | Antal transaktioner |")
    sep = "|---|---:|---:|---:|---:|---:|"
    print(hdr)
    print(sep)

    for key, _, _, _, _, _ in configs:
        r = results[key]
        print(f"| {r['label']:<45} | {r['cagr']:>5.1f} | {r['sharpe']:>5.2f} "
              f"| {r['max_dd_mo']:>6.1f} | {r['turnover_pct']:>7.1f} "
              f"| {r['trade_count']:>4d} |")

    print()
    print("Turnover: total omsatt volym (en sida) / genomsnittligt NAV / år × 100")
    print()

    # ── Narrative analysis ────────────────────────────────────────
    r = results["LC-raw"]

    print("─" * 95)
    print("KONTROLLTEST — ZPD5.DE: återställer 5-sektorskorgen strukturellt alfa?")
    print("─" * 95)
    print(f"\n  CAGR:        {r['cagr']:>5.1f}%")
    print(f"  Sharpe:      {r['sharpe']:>5.2f}")
    print(f"  Max DD (mo): {r['max_dd_mo']:>5.1f}%")
    print(f"  Turnover/år: {r['turnover_pct']:>5.1f}%")
    print(f"  Transakt.:   {r['trade_count']:>4d}  ({r['n_years']:.1f} år)")

    # Referensvärden från tidigare körningar
    REF_5SEK_QDVH = {"label": "5-sek m/ QDVH (Financials-korruption)", "sharpe": 0.87, "cagr": 11.2}
    REF_4SEK_RAW  = {"label": "4-sek rent universum",                   "sharpe": 0.97, "cagr": 12.5}
    REF_ORIG_LC   = {"label": "Orig. LC sweep B (QDVH+XLC, annan Utilities)", "sharpe": 1.30, "cagr": 18.2}

    print()
    print("  Jämförelse mot referenspunkter:")
    print(f"  {'Konfiguration':<45} {'Sharpe':>7} {'CAGR':>7}")
    print(f"  {'-'*45} {'-'*7} {'-'*7}")
    print(f"  {'>>> ZPD5.DE (detta test) <<<':<45} {r['sharpe']:>7.2f} {r['cagr']:>6.1f}%")
    for ref in [REF_4SEK_RAW, REF_5SEK_QDVH, REF_ORIG_LC]:
        print(f"  {ref['label']:<45} {ref['sharpe']:>7.2f} {ref['cagr']:>6.1f}%")

    print()
    if r["sharpe"] >= 1.20 and r["cagr"] >= 16.0:
        print("  BEKRÄFTAT: ZPD5.DE återställer alfa till Sweep B-nivå. "
              f"CAGR {r['cagr']:.1f}% / Sharpe {r['sharpe']:.2f} ≈ ursprungligt mål (~18% / 1.30).")
    elif r["sharpe"] > REF_4SEK_RAW["sharpe"]:
        print(f"  PARTIELLT: ZPD5.DE förbättrar 4-sektorskorgen "
              f"(Sharpe {r['sharpe']:.2f} > {REF_4SEK_RAW['sharpe']:.2f}) men når ej "
              f"ursprunglig Sweep B-nivå (1.30 / 18.2%).")
    else:
        print(f"  EJ BEKRÄFTAT: ZPD5.DE återställer inte alfa "
              f"(Sharpe {r['sharpe']:.2f} ≤ 4-sektors {REF_4SEK_RAW['sharpe']:.2f}).")
    print()


if __name__ == "__main__":
    main()
