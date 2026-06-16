#!/usr/bin/env python3
"""
Comprehensive sweep for:
  SWEEP A — Accelerated Momentum
    ACCEL_LOOKBACK × ACCEL_WINDOW × EMA_SPAN × D1/D2
    5 × 4 × 4 × 2 = 160 runs, normal universe

  SWEEP B — Low-Corr Basket
    metric (raw / composite / accel) × sel_lb (raw only) × D1/D2
    + universe variants: with/without GLD, sector subsets
    ~80 runs

All: symmetric 84/84 regime, 15bps/side.
Prints ranked tables; saves SWEEP_NEW.md.
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent / "dashboard" / "backend"))
import engine as eng

# ─────────────────────────────────────────────────────────────────────
# Sweep grids
# ─────────────────────────────────────────────────────────────────────
ACCEL_LOOKBACKS = [21, 42, 63, 84, 126]
ACCEL_WINDOWS   = [5, 10, 15, 20]
EMA_SPANS       = [3, 5, 10, 21]
RAW_SEL_LBS     = [21, 42, 63, 84, 126]

COST    = 0.0015
CAPITAL = 100_000.0
START   = "2019-10-01"
REG_LB  = 84
CASH    = "CASH"

# ─────────────────────────────────────────────────────────────────────
# Helpers (self-contained — don't rely on engine internals changing)
# ─────────────────────────────────────────────────────────────────────
def p_at(ticker, d, prices):
    if ticker == CASH: return 1.0
    if ticker in prices.columns and d in prices.index:
        v = prices.loc[d, ticker]
        return float(v) if not np.isnan(v) else 0.0
    return 0.0


def raw_ret(ticker, d, prices, pos_map, lb):
    if ticker == CASH: return 0.0
    pos = pos_map.get(d, -1)
    if pos < lb or ticker not in prices.columns: return np.nan
    p0 = float(prices.iloc[pos - lb][ticker])
    p1 = float(prices.iloc[pos][ticker])
    return p1 / p0 - 1 if p0 > 0 else np.nan


def composite_score(ticker, d, prices, pos_map):
    if ticker == CASH: return 0.0
    pos = pos_map.get(d, -1)
    if pos < 84 or ticker not in prices.columns: return np.nan
    p = float(prices.iloc[pos][ticker])
    p21 = float(prices.iloc[pos - 21][ticker])
    p84 = float(prices.iloc[pos - 84][ticker])
    if p21 <= 0 or p84 <= 0: return np.nan
    return 0.5 * (p / p21 - 1) + 0.5 * (p / p84 - 1)


def accel_score(ticker, d, smooth, pos_map, lb, win):
    if ticker == CASH: return 0.0
    pos = pos_map.get(d, -1)
    min_p = max(lb, 2 * win)
    if pos < min_p or ticker not in smooth.columns: return np.nan
    try:
        pn  = float(smooth.iloc[pos][ticker])
        plb = float(smooth.iloc[pos - lb][ticker])
        pw  = float(smooth.iloc[pos - win][ticker])
        p2w = float(smooth.iloc[pos - 2 * win][ticker])
    except Exception: return np.nan
    if any(v <= 0 for v in [pn, plb, pw, p2w]): return np.nan
    roc   = pn / plb - 1
    accel = (pn / pw - 1) - (pw / p2w - 1)
    return roc + accel


def top_n(tickers, score_fn, n):
    scores = {t: score_fn(t) for t in tickers}
    valid  = {t: v for t, v in scores.items() if not np.isnan(v)}
    return sorted(valid, key=valid.__getitem__, reverse=True)[:n]


def regime_ok(d, prices, pos_map, iwda, ibts):
    """True = stay invested (IWDA 84d return > IBTS 84d return)."""
    pos = pos_map.get(d, -1)
    if pos < REG_LB: return True
    for t in [iwda, ibts]:
        if t not in prices.columns: return True
    p0i = float(prices.iloc[pos - REG_LB][iwda])
    p1i = float(prices.iloc[pos][iwda])
    p0b = float(prices.iloc[pos - REG_LB][ibts])
    p1b = float(prices.iloc[pos][ibts])
    if any(v <= 0 for v in [p0i, p1i, p0b, p1b]): return True
    return (p1i / p0i - 1) > (p1b / p0b - 1)


def run_bt(prices, factor_t, sector_t, regime_t, ibts_t, cash_t,
           score_fn_f, score_fn_s, n_f, n_s, warmup):
    """Returns (equity_curve, avg_annual_turnover)."""
    all_idx   = prices.index
    rebal_set = eng.month_end_dates(all_idx)
    pos_map   = {d: i for i, d in enumerate(all_idx)}
    sim_dates = all_idx[all_idx >= pd.Timestamp(START)]
    min_date  = all_idx[warmup] if len(all_idx) > warmup else all_idx[-1]

    cash_bal  = float(CAPITAL)
    shares    = {}
    cur_w     = {}
    equity    = []
    pending   = None
    total_to  = 0.0
    n_reb     = 0

    for d in sim_dates:
        if pending is not None:
            all_t = set(shares) | set(pending)
            px    = {t: p_at(t, d, prices) for t in all_t}
            val   = cash_bal + sum(shares.get(t, 0.0) * px.get(t, 0.0) for t in shares)
            new_sh = {t: (val * w) / px[t] for t, w in pending.items() if px.get(t, 0.0) > 0}
            all_tw = set(cur_w) | set(pending)
            total_to += sum(abs(pending.get(t, 0.0) - cur_w.get(t, 0.0)) for t in all_tw)
            n_reb    += 1
            real_t    = {t for t in all_t if t != CASH}
            cost = sum(abs(new_sh.get(t, 0.0) * px.get(t, 0.0)
                           - shares.get(t, 0.0) * px.get(t, 0.0)) * COST
                       for t in real_t)
            cash_bal = val - sum(new_sh[t] * px[t] for t in new_sh) - cost
            shares   = new_sh
            cur_w    = dict(pending)
            pending  = None

        held = sum(sh * p_at(t, d, prices) for t, sh in shares.items())
        equity.append({"date": d.strftime("%Y-%m-%d"), "value": round(cash_bal + held, 2)})

        if d not in rebal_set or d < min_date: continue

        if not regime_ok(d, prices, pos_map, regime_t, ibts_t):
            pending = {cash_t: 1.0}
            continue

        f_picks = top_n(factor_t, lambda t: score_fn_f(t, d, pos_map), n_f)
        s_picks = top_n(sector_t, lambda t: score_fn_s(t, d, pos_map), n_s)
        if not f_picks and not s_picks: continue

        w = {}
        for t in f_picks: w[t] = w.get(t, 0.0) + 0.5 / len(f_picks)
        for t in s_picks: w[t] = w.get(t, 0.0) + 0.5 / len(s_picks)
        pending = w

    dates = pd.to_datetime([e["date"] for e in equity])
    n_yrs = (dates[-1] - dates[0]).days / 365.25 if len(dates) > 1 else 1.0
    return equity, round(total_to / n_yrs, 2) if n_yrs > 0 else 0.0


def stats(equity):
    if len(equity) < 20: return {}
    dates  = pd.to_datetime([e["date"] for e in equity])
    vals   = np.array([e["value"] for e in equity], dtype=float)
    rets   = np.diff(vals) / vals[:-1]
    n_yrs  = (dates[-1] - dates[0]).days / 365.25
    cagr   = (vals[-1] / vals[0]) ** (1 / n_yrs) - 1 if n_yrs > 0 else 0.0
    mu     = np.mean(rets) * 252
    sig    = np.std(rets, ddof=1) * np.sqrt(252)
    sharpe = mu / sig if sig > 0 else 0.0
    peak   = np.maximum.accumulate(vals)
    max_dd = float(((vals - peak) / peak).min())
    df     = pd.DataFrame({"v": vals}, index=dates)
    mo_v   = df.resample("ME").last()["v"].values
    mo_pk  = np.maximum.accumulate(mo_v)
    dd_mo  = float(((mo_v - mo_pk) / mo_pk).min()) if len(mo_v) > 1 else max_dd
    return {"cagr": cagr, "sharpe": sharpe, "max_dd": max_dd, "dd_mo": dd_mo,
            "vol": sig, "total": vals[-1] / vals[0] - 1}


def row_str(rank, label, s, to):
    return (f"{rank:>3}  {label:<38}  "
            f"{s['cagr']:>7.1%}  {s['sharpe']:>6.2f}  "
            f"{s['dd_mo']:>8.1%}  {s['max_dd']:>8.1%}  "
            f"{s['vol']:>6.1%}  {to:>6.1f}x")


def hdr():
    return (f"{'#':>3}  {'Label':<38}  "
            f"{'CAGR':>7}  {'Sharpe':>6}  "
            f"{'DD_mo':>8}  {'DD_d':>8}  "
            f"{'Vol':>6}  {'TO/yr':>6}")


# ─────────────────────────────────────────────────────────────────────
# Setup
# ─────────────────────────────────────────────────────────────────────
print("Loading config + prices…")
cfg = eng.load_config()
factor_t, sector_t, regime_t, ibts_t, cash_t, ter_map = eng.parse_config(cfg)

for v in eng.LOW_CORR_EXTRA.values():
    ter_map.setdefault(v["ticker"], v["ter_pct"])

lc_tickers = [v["ticker"] for v in eng.LOW_CORR_EXTRA.values()]
strategy_tickers = ([t for _, t in factor_t] + [t for _, t in sector_t]
                    + [regime_t, ibts_t] + lc_tickers)
prices_dict = eng.fetch_prices(list(dict.fromkeys(strategy_tickers)), use_cache=True)
prices_raw  = prices_dict["close"]
prices_high = prices_dict.get("high", prices_raw)
prices_low  = prices_dict.get("low",  prices_raw)

strategy_cols = [t for t in strategy_tickers if t in prices_raw.columns]
prices_adj    = prices_raw.copy()
prices_adj[strategy_cols] = eng.apply_ter(prices_raw[strategy_cols], ter_map)

f_tickers = [t for _, t in factor_t]
s_tickers = [t for _, t in sector_t]

# Low-corr universe
lc_sector_t = (
    [t for lbl, t in sector_t if lbl in eng.LOW_CORR_SECTOR_KEEP]
    + [v["ticker"] for lbl, v in eng.LOW_CORR_EXTRA.items() if lbl != "GOLD"]
    + [eng.LOW_CORR_EXTRA["GOLD"]["ticker"]]
)
lc_sector_no_gold = [t for t in lc_sector_t if t != eng.LOW_CORR_EXTRA["GOLD"]["ticker"]]
lc_factor_t = f_tickers + [eng.LOW_CORR_EXTRA["GOLD"]["ticker"]]

# Pre-build pos_map (shared for all runs)
pos_map_global = {d: i for i, d in enumerate(prices_adj.index)}

# ─────────────────────────────────────────────────────────────────────
# SWEEP A — Accelerated Momentum
# ─────────────────────────────────────────────────────────────────────
print("\n" + "=" * 80)
print("SWEEP A — Accelerated Momentum  (5 lb × 4 win × 4 ema × D1/D2 = 160 runs)")
print("=" * 80)

results_a = []
total_a = len(ACCEL_LOOKBACKS) * len(ACCEL_WINDOWS) * len(EMA_SPANS) * 2
run_n = 0

for ema in EMA_SPANS:
    # Precompute smooth prices for this EMA span
    cols = [c for c in strategy_cols if c in prices_high.columns and c in prices_low.columns]
    median = (prices_high[cols] + prices_low[cols]) / 2
    for c in strategy_cols:
        if c not in cols and c in prices_raw.columns:
            median[c] = prices_raw[c]
    median_adj = eng.apply_ter(median, ter_map)
    smooth = median_adj.ewm(span=ema, adjust=False).mean()

    for lb in ACCEL_LOOKBACKS:
        for win in ACCEL_WINDOWS:
            warmup = max(REG_LB, lb, 2 * win)
            for n_f, n_s, d_label in [(1, 1, "D1"), (2, 2, "D2")]:
                run_n += 1
                label = f"{d_label} | ema={ema:2d} lb={lb:3d} win={win:2d}"
                print(f"[{run_n:3d}/{total_a}] {label} … ", end="", flush=True)

                def sf(t, d, pm, _lb=lb, _win=win, _sm=smooth):
                    return accel_score(t, d, _sm, pm, _lb, _win)

                eq, to = run_bt(prices_adj, f_tickers, s_tickers,
                                regime_t, ibts_t, cash_t,
                                lambda t, d, pm: sf(t, d, pm),
                                lambda t, d, pm: sf(t, d, pm),
                                n_f, n_s, warmup)
                st = stats(eq)
                results_a.append({**st, "label": label, "to": to,
                                   "ema": ema, "lb": lb, "win": win, "picks": f"{n_f}/{n_s}"})
                print(f"CAGR {st['cagr']:.1%}  Sh {st['sharpe']:.2f}  DDmo {st['dd_mo']:.1%}")

df_a = pd.DataFrame(results_a).sort_values("sharpe", ascending=False).reset_index(drop=True)

print(f"\n{'─'*80}")
print("TOP-15 ACCEL (by Sharpe)")
print(f"{'─'*80}")
print(hdr())
print("─" * 80)
for i, r in df_a.head(15).iterrows():
    print(row_str(i + 1, r["label"], r, r["to"]))

# ─────────────────────────────────────────────────────────────────────
# SWEEP B — Low-Corr Basket
# ─────────────────────────────────────────────────────────────────────
print("\n" + "=" * 80)
print("SWEEP B — Low-Corr Basket  (metric × universe × D1/D2)")
print("=" * 80)

# Best accel params from Sweep A for use in low-corr accel runs
best_accel = df_a[df_a["picks"] == "1/1"].iloc[0]
best_ema   = int(best_accel["ema"])
best_lb    = int(best_accel["lb"])
best_win   = int(best_accel["win"])
print(f"Using best accel params from Sweep A: ema={best_ema} lb={best_lb} win={best_win}")

# Precompute smooth for best accel params
cols = [c for c in strategy_cols if c in prices_high.columns and c in prices_low.columns]
median = (prices_high[cols] + prices_low[cols]) / 2
for c in strategy_cols:
    if c not in cols and c in prices_raw.columns:
        median[c] = prices_raw[c]
median_adj = eng.apply_ter(median, ter_map)
best_smooth = median_adj.ewm(span=best_ema, adjust=False).mean()

results_b = []

# Universe variants
universes = {
    "full_lc":    (lc_factor_t, lc_sector_t),
    "no_gold":    (f_tickers,   lc_sector_no_gold),
    "gold_only_sector": (f_tickers, lc_sector_t),
}

# Metrics to test in each universe
configs_b = []

for univ_name, (ft, st_) in universes.items():
    # composite
    configs_b.append((univ_name, ft, st_, "composite", None, 84, 1, 1))
    configs_b.append((univ_name, ft, st_, "composite", None, 84, 2, 2))
    # raw across sel_lb
    for sel in RAW_SEL_LBS:
        configs_b.append((univ_name, ft, st_, "raw",       None,        sel,  1, 1))
        configs_b.append((univ_name, ft, st_, "raw",       None,        sel,  2, 2))
    # accel with best params
    configs_b.append((univ_name, ft, st_, "accel",     best_smooth, best_lb, 1, 1))
    configs_b.append((univ_name, ft, st_, "accel",     best_smooth, best_lb, 2, 2))

total_b = len(configs_b)
run_n = 0

for univ, ft, st_, metric, smooth_b, sel_lb, n_f, n_s in configs_b:
    run_n += 1
    picks = f"D{'1' if n_f == 1 else '2'}"
    label = f"{picks} | {univ:<20} {metric:<10} sel={sel_lb:3d}"
    print(f"[{run_n:3d}/{total_b}] {label} … ", end="", flush=True)

    warmup = max(REG_LB, sel_lb, 84 if metric == "composite" else 0,
                 max(best_lb, 2 * best_win) if metric == "accel" else 0)

    if metric == "composite":
        sf = lambda t, d, pm: composite_score(t, d, prices_adj, pm)
    elif metric == "accel":
        sf = lambda t, d, pm, _sm=smooth_b: accel_score(t, d, _sm, pm, best_lb, best_win)
    else:  # raw
        sf = lambda t, d, pm, _lb=sel_lb: raw_ret(t, d, prices_adj, pm, _lb)

    eq, to = run_bt(prices_adj, ft, st_, regime_t, ibts_t, cash_t,
                    sf, sf, n_f, n_s, warmup)
    st = stats(eq)
    results_b.append({**st, "label": label, "to": to})
    print(f"CAGR {st['cagr']:.1%}  Sh {st['sharpe']:.2f}  DDmo {st['dd_mo']:.1%}")

df_b = pd.DataFrame(results_b).sort_values("sharpe", ascending=False).reset_index(drop=True)

print(f"\n{'─'*80}")
print("TOP-15 LOW-CORR (by Sharpe)")
print(f"{'─'*80}")
print(hdr())
print("─" * 80)
for i, r in df_b.head(15).iterrows():
    print(row_str(i + 1, r["label"], r, r["to"]))

# ─────────────────────────────────────────────────────────────────────
# Save markdown
# ─────────────────────────────────────────────────────────────────────
out_path = Path(__file__).parent / "SWEEP_NEW.md"
with open(out_path, "w") as f:
    f.write("# New Strategy Parameter Sweeps\n\n")

    f.write("## Sweep A — Accelerated Momentum (top-15 by Sharpe)\n\n")
    f.write(f"Grid: lb∈{ACCEL_LOOKBACKS} × win∈{ACCEL_WINDOWS} × ema∈{EMA_SPANS} × D1/D2  "
            f"({total_a} runs)\n\n")
    f.write("| # | Config | CAGR | Sharpe | DD_mo | DD_d | Vol | TO/yr |\n")
    f.write("|---|--------|------|--------|-------|------|-----|-------|\n")
    for i, r in df_a.head(15).iterrows():
        st = r
        f.write(f"| {i+1} | {r['label']} | {st['cagr']:.1%} | {st['sharpe']:.2f} | "
                f"{st['dd_mo']:.1%} | {st['max_dd']:.1%} | {st['vol']:.1%} | {r['to']:.1f}× |\n")

    f.write("\n## Sweep B — Low-Corr Basket (top-15 by Sharpe)\n\n")
    f.write("Universe variants:\n"
            "- `full_lc`: GLD in factor+sector, low-corr sectors (Energy/Util/ConsStap/Comms/HC)\n"
            "- `no_gold`: normal factor sleeve, low-corr sectors without GLD\n"
            "- `gold_only_sector`: normal factor sleeve, low-corr sectors with GLD\n\n")
    f.write("| # | Config | CAGR | Sharpe | DD_mo | DD_d | Vol | TO/yr |\n")
    f.write("|---|--------|------|--------|-------|------|-----|-------|\n")
    for i, r in df_b.head(15).iterrows():
        st = r
        f.write(f"| {i+1} | {r['label']} | {st['cagr']:.1%} | {st['sharpe']:.2f} | "
                f"{st['dd_mo']:.1%} | {st['max_dd']:.1%} | {st['vol']:.1%} | {r['to']:.1f}× |\n")

print(f"\nSaved: {out_path}")
