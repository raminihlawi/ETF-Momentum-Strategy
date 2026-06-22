#!/usr/bin/env python3
"""
Thematic Overlay Sweep
======================
Baseline: D1-accel (50% factor top-1 + 50% sector top-1, accel scoring)
Test:     40% factor top-1 + 40% sector top-1 + 20% fixed thematic ETF

Each thematic ETF is tested in isolation. Results compared against baseline.
Run: python3 sweep_thematic.py [--quick]
"""

import sys
import logging
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ── Parameters ───────────────────────────────────────────────────────
START    = "2019-10-01"
DL_FROM  = "2004-01-01"
SEL_LB   = 84
REG_LB   = 84
COST     = 0.0015
CAPITAL  = 100_000
ACCEL_LB = 84
ACCEL_WIN = 15
EMA_SPAN  = 5

REGIME_T   = "IWDA.L"
REGIME_CMP = "IBTS.L"
CASH_T     = "CASH"

CACHE_PATH = Path(__file__).parent / "dashboard/backend/_price_cache.pkl"

# ── Universes ────────────────────────────────────────────────────────
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

SECTOR_SLEEVE = [
    ("IT",          "QDVE.DE", 0.15),
    ("ENERGY",      "QDVF.DE", 0.15),
    ("HEALTHCARE",  "QDVG.DE", 0.15),
    ("CONS DISC",   "QDVK.DE", 0.15),
    ("INDUSTRIALS", "2B7C.DE", 0.15),
    ("CONS STAP",   "2B7D.DE", 0.15),
    ("MATERIALS",   "2B7B.DE", 0.15),
]

THEMATIC = [
    ("Cybersecurity",     "L0CK.DE", 0.75),  # Xtrackers Cybersecurity UCITS ETF  (Xetra, fr. 2019)
    ("AI & Robotik",      "WTAI.DE", 0.40),  # WisdomTree AI & Robotics UCITS ETF (Xetra, fr. 2019)
    ("Uran",              "URNU.DE", 0.35),  # Sprott Uranium Miners UCITS ETF     (Xetra, fr. 2022)
    ("Ren Energi",        "IQQH.DE", 0.65),  # iShares Global Clean Energy UCITS   (Xetra, fr. 2019)
    ("Global Infra",      "IQQP.DE", 0.40),  # iShares Global Infrastructure UCITS (Xetra, fr. 2019)
    ("Vatten",            "CGW",     0.50),  # Invesco Water Resources ETF          (US,    fr. 2019)
    ("Batterimetaller",   "BATE.DE", 0.49),  # WisdomTree Battery Solutions UCITS  (Xetra, fr. 2019)
    ("EV & Autonomt",     "ECAR.L",  0.40),  # iShares Electric Vehicles UCITS ETF (London,fr. 2019)
    ("Global Lyx",        "GLUX.DE", 0.59),  # Amundi S&P Global Luxury UCITS ETF  (Xetra, fr. 2019)
    ("CTA/Trendföljning", "DBMF",    0.75),  # iMGP DBi Managed Futures ETF        (US,    fr. 2019)
]

TER_MAP = {
    **{t: ter for _, t, ter in FACTOR_SLEEVE},
    **{t: ter for _, t, ter in SECTOR_SLEEVE},
    **{t: ter for _, t, ter in THEMATIC},
    "IWDA.L": 0.20,
    "IBTS.L": 0.10,
}


# ── Price helpers ────────────────────────────────────────────────────
def fetch_prices(use_cache: bool = False) -> dict:
    needed = (
        [t for _, t, _ in FACTOR_SLEEVE]
        + [t for _, t, _ in SECTOR_SLEEVE]
        + [t for _, t, _ in THEMATIC]
        + [REGIME_T, REGIME_CMP]
    )
    if use_cache and CACHE_PATH.exists():
        try:
            cached = pd.read_pickle(CACHE_PATH)
            if isinstance(cached, dict) and "close" in cached:
                missing = [t for t in needed if t not in cached["close"].columns]
                if not missing:
                    log.info("Using cached prices")
                    return cached
                log.info(f"Cache missing: {missing} — re-downloading")
        except Exception:
            pass

    log.info(f"Downloading {len(needed)} tickers from {DL_FROM}...")
    raw = yf.download(needed, start=DL_FROM, progress=False, auto_adjust=True, threads=True)
    if isinstance(raw.columns, pd.MultiIndex):
        close, high, low = raw["Close"], raw["High"], raw["Low"]
    else:
        t0 = needed[0]
        close = raw[["Close"]].rename(columns={"Close": t0})
        high  = raw[["High"]].rename(columns={"High": t0})
        low   = raw[["Low"]].rename(columns={"Low": t0})

    close, high, low = close.ffill(), high.ffill(), low.ffill()
    result = {"close": close, "high": high, "low": low}
    pd.to_pickle(result, CACHE_PATH)
    return result


def apply_ter(prices: pd.DataFrame) -> pd.DataFrame:
    result = prices.copy().astype(float)
    for col in result.columns:
        ter = TER_MAP.get(col, 0.0)
        if ter > 0:
            drag = (1 - ter / 100) ** (1 / 252)
            result[col] *= drag ** np.arange(len(result))
    return result


def compute_smooth(prices_high, prices_low, prices_close, ema_span: int,
                   extra_tickers: list = None) -> pd.DataFrame:
    tickers = ([t for _, t, _ in FACTOR_SLEEVE]
               + [t for _, t, _ in SECTOR_SLEEVE]
               + (extra_tickers or []))
    cols = [t for t in tickers if t in prices_high.columns and t in prices_low.columns]
    median = (prices_high[cols] + prices_low[cols]) / 2
    for t in tickers:
        if t not in cols and t in prices_close.columns:
            median[t] = prices_close[t]
    return apply_ter(median).ewm(span=ema_span, adjust=False).mean()


def _backtest_alloc(prices_adj, smooth, thematic_universe):
    """Lightweight pass — returns only the thematic picks per rebalance date."""
    f_tickers = [t for _, t, _ in FACTOR_SLEEVE]
    s_tickers = [t for _, t, _ in SECTOR_SLEEVE]
    th_tickers = [t for _, t, _ in thematic_universe]
    all_idx   = prices_adj.index
    rebal_set = month_end_dates(all_idx)
    pos_map   = {d: i for i, d in enumerate(all_idx)}
    warmup    = max(REG_LB, ACCEL_LB, 2 * ACCEL_WIN)
    sim_dates = all_idx[all_idx >= pd.Timestamp(START)]
    min_date  = all_idx[warmup]
    log = []

    def ret_lb(ticker, d, lb):
        if ticker == CASH_T: return 0.0
        pos = pos_map.get(d, -1)
        if pos < lb or ticker not in prices_adj.columns: return np.nan
        p0 = float(prices_adj.iloc[pos - lb][ticker])
        p1 = float(prices_adj.iloc[pos][ticker])
        return (p1 / p0 - 1) if p0 > 0 else np.nan

    def score_accel(ticker, d):
        if ticker == CASH_T: return 0.0
        pos = pos_map.get(d, -1)
        min_pos = max(ACCEL_LB, 2 * ACCEL_WIN)
        if pos < min_pos or ticker not in smooth.columns: return np.nan
        try:
            p_now = float(smooth.iloc[pos][ticker])
            p_lb  = float(smooth.iloc[pos - ACCEL_LB][ticker])
            p_w   = float(smooth.iloc[pos - ACCEL_WIN][ticker])
            p_2w  = float(smooth.iloc[pos - 2 * ACCEL_WIN][ticker])
        except Exception: return np.nan
        if any(v <= 0 for v in [p_now, p_lb, p_w, p_2w]): return np.nan
        return (p_now / p_lb - 1) + (p_now / p_w - 1) - (p_w / p_2w - 1)

    def top1(tickers):
        sc = {t: score_accel(t, d) for t in tickers}
        sc = {t: v for t, v in sc.items() if not np.isnan(v)}
        return sorted(sc, key=sc.__getitem__, reverse=True)[:1]

    for d in sim_dates:
        if d not in rebal_set or d < min_date: continue
        r_mkt = ret_lb(REGIME_T,   d, REG_LB)
        r_cmp = ret_lb(REGIME_CMP, d, REG_LB)
        if not np.isnan(r_mkt) and not np.isnan(r_cmp) and r_mkt <= r_cmp:
            log.append({"date": d.strftime("%Y-%m-%d"), "holdings": {CASH_T: 1.0}})
            continue
        th_picks = top1(th_tickers)
        holdings = {t: 0.20 for t in th_picks}
        log.append({"date": d.strftime("%Y-%m-%d"), "holdings": holdings})

    return log


def month_end_dates(idx: pd.DatetimeIndex) -> set:
    s = pd.Series(idx, index=idx)
    return set(s.groupby(s.dt.to_period("M")).apply(lambda g: g.index[-1]).values)


# ── Backtest ─────────────────────────────────────────────────────────
def backtest(prices_adj: pd.DataFrame,
             smooth: pd.DataFrame,
             thematic_ticker: str = None,   # None = pure D1-accel; "ROTATE" = rotating sleeve
             thematic_w: float = 0.20,
             thematic_universe: list = None) -> dict:
    """
    thematic_ticker=None  → 50/50 factor/sector (D1-accel baseline)
    thematic_ticker=X     → 40/40/20 factor/sector/thematic
    """
    f_tickers = [t for _, t, _ in FACTOR_SLEEVE]
    s_tickers = [t for _, t, _ in SECTOR_SLEEVE]

    rotating  = thematic_ticker == "ROTATE"
    has_theme = bool(thematic_ticker) and not rotating
    sleeve_w  = (1 - thematic_w) / 2 if (has_theme or rotating) else 0.5
    th_tickers = [t for _, t, _ in (thematic_universe or [])]

    all_idx   = prices_adj.index
    rebal_set = month_end_dates(all_idx)
    pos_map   = {d: i for i, d in enumerate(all_idx)}
    warmup    = max(REG_LB, ACCEL_LB, 2 * ACCEL_WIN)
    sim_dates = all_idx[all_idx >= pd.Timestamp(START)]
    min_date  = all_idx[warmup]

    cash_bal = float(CAPITAL)
    shares   = {}
    equity   = []
    pending  = None
    total_traded = 0.0
    trade_count  = 0

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

    def score_accel(ticker, d):
        if ticker == CASH_T:
            return 0.0
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
        return (p_now / p_lb - 1) + (p_now / p_w - 1) - (p_w / p_2w - 1)

    for d in sim_dates:
        if pending is not None:
            all_t = set(shares) | set(pending)
            px    = {t: price_at(t, d) for t in all_t}
            value = cash_bal + sum(shares.get(t, 0.0) * px.get(t, 0.0) for t in shares)

            new_sh = {}
            for t, w in pending.items():
                p = px.get(t, 0.0)
                if p > 0:
                    new_sh[t] = value * w / p

            real_t = {t for t in all_t if t != CASH_T}
            for t in real_t:
                delta = abs(new_sh.get(t, 0.0) * px.get(t, 0.0)
                            - shares.get(t, 0.0) * px.get(t, 0.0))
                if delta > 1.0:
                    total_traded += delta / 2
                    trade_count  += 1

            cost = sum(
                abs(new_sh.get(t, 0.0) * px.get(t, 0.0)
                    - shares.get(t, 0.0) * px.get(t, 0.0)) * COST
                for t in real_t
            )
            cash_bal = value - sum(new_sh[t] * px[t] for t in new_sh) - cost
            shares   = new_sh
            pending  = None

        held = sum(sh * price_at(t, d) for t, sh in shares.items())
        equity.append({"date": d.strftime("%Y-%m-%d"), "value": round(cash_bal + held, 2)})

        if d not in rebal_set or d < min_date:
            continue

        # Regime gate
        r_mkt = ret_lb(REGIME_T,   d, REG_LB)
        r_cmp = ret_lb(REGIME_CMP, d, REG_LB)
        if not np.isnan(r_mkt) and not np.isnan(r_cmp) and r_mkt <= r_cmp:
            pending = {CASH_T: 1.0}
            continue

        # Selection
        def top1(tickers):
            sc = {t: score_accel(t, d) for t in tickers}
            sc = {t: v for t, v in sc.items() if not np.isnan(v)}
            return sorted(sc, key=sc.__getitem__, reverse=True)[:1]

        f_picks = top1(f_tickers)
        s_picks = top1(s_tickers)
        if not f_picks and not s_picks:
            continue

        w = {}
        for t in f_picks:
            w[t] = w.get(t, 0.0) + sleeve_w
        for t in s_picks:
            w[t] = w.get(t, 0.0) + sleeve_w

        # Thematic sleeve
        if rotating and th_tickers:
            # Rotate: pick top-1 thematic by accel score
            th_picks = top1(th_tickers)
            for t in th_picks:
                w[t] = w.get(t, 0.0) + thematic_w
        elif has_theme and thematic_ticker in prices_adj.columns:
            # Fixed: always hold the same thematic ETF
            if d in prices_adj.index and not np.isnan(prices_adj.loc[d, thematic_ticker]):
                w[thematic_ticker] = w.get(thematic_ticker, 0.0) + thematic_w

        # Normalise if thematic unavailable or weights don't sum to 1
        total_w = sum(w.values())
        if total_w > 0:
            w = {t: v / total_w for t, v in w.items()}

        pending = w

    # Stats
    dates  = pd.to_datetime([e["date"] for e in equity])
    values = np.array([e["value"] for e in equity], dtype=float)
    rets   = np.diff(values) / values[:-1]
    n_yrs  = (dates[-1] - dates[0]).days / 365.25
    cagr   = (values[-1] / values[0]) ** (1 / n_yrs) - 1 if n_yrs > 0 else 0.0
    sharpe = np.mean(rets) * 252 / (np.std(rets, ddof=1) * np.sqrt(252))

    mo  = pd.Series(values, index=dates).resample("ME").last().values
    mop = np.maximum.accumulate(mo)
    mdd = float(((mo - mop) / mop).min()) if len(mo) > 1 else 0.0

    avg_nav  = float(np.mean(values))
    turnover = total_traded / avg_nav / n_yrs * 100 if n_yrs > 0 else 0.0

    return {
        "cagr":         round(cagr * 100, 2),
        "sharpe":       round(sharpe, 2),
        "max_dd_mo":    round(mdd * 100, 2),
        "turnover_pct": round(turnover, 1),
        "trade_count":  trade_count,
        "n_years":      round(n_yrs, 2),
    }


# ── Main ─────────────────────────────────────────────────────────────
def main():
    use_cache = "--quick" in sys.argv

    prices_dict = fetch_prices(use_cache=use_cache)
    prices_raw  = prices_dict["close"]
    prices_high = prices_dict.get("high", prices_raw)
    prices_low  = prices_dict.get("low",  prices_raw)

    strat_cols = (
        [t for _, t, _ in FACTOR_SLEEVE]
        + [t for _, t, _ in SECTOR_SLEEVE]
        + [REGIME_T, REGIME_CMP]
    )
    prices_adj = prices_raw.copy()
    adj_cols   = [t for t in strat_cols if t in prices_raw.columns]
    prices_adj[adj_cols] = apply_ter(prices_raw[adj_cols])

    th_tickers = [t for _, t, _ in THEMATIC]
    smooth = compute_smooth(prices_high, prices_low, prices_raw, EMA_SPAN,
                            extra_tickers=th_tickers)

    # Apply TER to thematic tickers in prices_adj too
    th_cols = [t for t in th_tickers if t in prices_raw.columns]
    prices_adj[th_cols] = apply_ter(prices_raw[th_cols])

    log.info("Running D1-accel baseline (50/50)...")
    r_base = backtest(prices_adj, smooth)

    log.info("Running D1-accel + WTAI.DE fixed 20% (prev. best fixed)...")
    r_wtai = backtest(prices_adj, smooth, thematic_ticker="WTAI.DE")

    log.info("Running D1-accel + rotating thematic sleeve (top-1 of 10, 20%)...")
    r_rot  = backtest(prices_adj, smooth, thematic_ticker="ROTATE",
                      thematic_universe=THEMATIC)

    # ── Output ────────────────────────────────────────────────────
    n_yrs = r_base["n_years"]
    print()
    print("=" * 100)
    print("TEMATISK ROTATION SWEEP")
    print("Baseline:    50% faktor top-1  +  50% sektor top-1  (D1-accel)")
    print("Fast WTAI:   40% faktor  +  40% sektor  +  20% WTAI.DE (fast)")
    print("Roterande:   40% faktor  +  40% sektor  +  20% tematisk top-1 (accel-ranking, 10 ETF:er)")
    print(f"Accel: EMA({EMA_SPAN}), lb={ACCEL_LB}d, win={ACCEL_WIN}d  |  Regimfilter: IWDA.L vs IBTS.L 84d")
    print(f"Period: {START} – idag  ({n_yrs:.1f} år)  |  Kostnad: {COST*10000:.0f} bps/sida")
    print("=" * 100)
    print()

    rows = [
        ("D1-accel baseline (50/50)",          "—",        r_base),
        ("+ WTAI.DE fast 20%",                 "WTAI.DE",  r_wtai),
        ("+ Roterande tematisk top-1 (20%)",   "10 ETF:er",r_rot),
    ]

    hdr = (f"| {'Konfiguration':<38} | {'Ticker':<10} | {'CAGR':>7} | {'Sharpe':>6} "
           f"| {'MaxDD mo':>8} | {'TO/år':>7} | {'Trades':>6} | {'ΔSharpe':>8} | {'ΔCAGR':>7} |")
    sep  = f"|{'-'*40}|{'-'*12}|{'-'*9}|{'-'*8}|{'-'*10}|{'-'*9}|{'-'*8}|{'-'*10}|{'-'*9}|"
    print(hdr)
    print(sep)

    for label, ticker, r in rows:
        dsh   = r["sharpe"] - r_base["sharpe"]
        dcagr = r["cagr"]   - r_base["cagr"]
        flag  = " ▲" if dsh > 0.03 else (" ▼" if dsh < -0.03 else "  ")
        d_str = f"{dsh:>+7.2f}{flag}" if label != rows[0][0] else f"{'—':>9}"
        c_str = f"{dcagr:>+6.1f}%"    if label != rows[0][0] else f"{'—':>7}"
        print(f"| {label:<38} | {ticker:<10} | {r['cagr']:>6.1f}% "
              f"| {r['sharpe']:>6.2f} | {r['max_dd_mo']:>7.1f}% | {r['turnover_pct']:>6.1f}% "
              f"| {r['trade_count']:>6d} | {d_str} | {c_str} |")

    print()

    # Which thematic ETF gets picked most often in the rotating sleeve?
    # Re-run to collect allocation log
    log.info("Collecting rotation log for thematic sleeve analysis...")
    alloc_log = _backtest_alloc(prices_adj, smooth, thematic_universe=THEMATIC)
    th_counts = {}
    for entry in alloc_log:
        for t, w in entry["holdings"].items():
            if t in th_tickers and w > 0.01:
                th_counts[t] = th_counts.get(t, 0) + 1

    if th_counts:
        total_months = sum(th_counts.values())
        lbl_map = {t: lbl for lbl, t, _ in THEMATIC}
        print("Tematisk sleeve — fördelning av månadsval (antal månader):")
        for t, cnt in sorted(th_counts.items(), key=lambda x: -x[1]):
            print(f"  {lbl_map.get(t, t):<22} {t:<10}  {cnt:>3} månader  ({cnt/total_months*100:.0f}%)")
    print()


if __name__ == "__main__":
    main()
