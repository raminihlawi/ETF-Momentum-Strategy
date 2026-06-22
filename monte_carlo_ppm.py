#!/usr/bin/env python3
"""
Monte Carlo — PPM Curated Strategy
===================================
Bootstrap-resampling av månadsavkastningar (med ersättning).
Testar robusthet för optimal config: EMA5, ROC63, accel10, top3, abs-mom.
10 000 simuleringar per strategi.
"""

import numpy as np
import pandas as pd
from pathlib import Path

DATA_FILE = Path(__file__).parent / "ppm_all_nav.csv"
ETF_JSON  = Path(__file__).parent / "dashboard/frontend/static/data.json"

EMA_SPAN, ROC_DAYS, ACCEL_WIN = 5, 63, 10
BENCH_PPM = "581371"
CASH_PPM  = "545541"
N_SIM     = 10_000
SEED      = 42

UNIVERSE = {
    "581371": "AP7 Aktie", "283408": "Tech", "644005": "Healthcare",
    "517748": "Energy",    "481911": "Mining", "479550": "Consumer Brands",
    "768556": "US Value",  "916354": "US Small", "456475": "US Quality",
    "163923": "US Growth", "182759": "EUR Small", "538462": "EUR Value",
    "162099": "Multifactor", "545541": "Ränta (AP7)",
}

# ── Data ──────────────────────────────────────────────────────────────
print("Laddar data…")
df   = pd.read_csv(DATA_FILE, parse_dates=["date"], dtype={"ppm_number": str})
df   = df[df["date"] > "2000-01-01"]
wide = df.pivot_table(index="date", columns="ppm_number",
                      values="nav_sek", aggfunc="last").sort_index()
wide = wide.reindex(pd.date_range(wide.index.min(), wide.index.max(), freq="B")).ffill()

bench = wide[BENCH_PPM].copy()
funds = wide[[c for c in UNIVERSE if c in wide.columns]].copy()

ema     = funds.ewm(span=EMA_SPAN, adjust=False).mean()
roc_sc  = ema / ema.shift(ROC_DAYS) - 1
scores  = roc_sc + (roc_sc - roc_sc.shift(ACCEL_WIN))
raw_roc = funds / funds.shift(ROC_DAYS) - 1

min_days   = ROC_DAYS + 2 * ACCEL_WIN + 10
month_ends = pd.date_range(
    wide.index.min() + pd.DateOffset(months=6),
    wide.index.max(), freq="BME"
)
month_ends = month_ends[month_ends <= wide.index.max()]

# ── Kör strategi — returnerar månadsavkastningar ───────────────────────
def get_monthly_returns(use_etf_cash=False, abs_mom=True, top_n=3):
    import json
    if use_etf_cash:
        with open(ETF_JSON) as f:
            etf_d = json.load(f)
        alloc_e  = etf_d["strategies"]["d1_accel"]["allocation"]
        cash_idx = alloc_e["tickers"].index("CASH")
        etf_cash = {
            (pd.Timestamp(dt).year, pd.Timestamp(dt).month)
            for dt, w in zip(alloc_e["dates"], alloc_e["weights"])
            if w[cash_idx] > 0
        }
    else:
        etf_cash = set()

    weights  = {}
    prev_dt  = None
    mo_rets  = []
    mo_dates = []

    for me in month_ends:
        avail = wide.index[wide.index <= me]
        if not len(avail):
            continue
        dt = avail[-1]

        elig = [c for c in funds.columns
                if funds[c].first_valid_index() is not None
                and (dt - funds[c].first_valid_index()).days >= min_days
                and not np.isnan(scores.loc[dt, c])]
        if not elig:
            continue

        in_etf_cash = (me.year, me.month) in etf_cash
        if in_etf_cash and CASH_PPM in funds.columns:
            picks = {CASH_PPM}
        else:
            row   = scores.loc[dt, elig].nlargest(top_n)
            picks = set(row.index)
            if abs_mom and CASH_PPM in funds.columns:
                if float(raw_roc.loc[dt, row.index[0]]) < 0:
                    picks = {CASH_PPM}

        if prev_dt is not None and weights:
            prev_avail = wide.index[wide.index <= prev_dt]
            p0  = prev_avail[-1]
            w   = 1.0 / len(weights)
            ret = sum(funds.loc[dt, p] / funds.loc[p0, p] - 1
                      for p in weights if p in funds.columns) * w
            mo_rets.append(ret)
            mo_dates.append(dt)

        weights = {p: 1/len(picks) for p in picks}
        prev_dt = me

    return pd.Series(mo_rets, index=mo_dates)

# ── Benchmark månadsavkastningar ──────────────────────────────────────
bench_mo = []
bench_dates = []
prev_b = None
for me in month_ends:
    avail = bench.index[bench.index <= me]
    if not len(avail):
        continue
    dt = avail[-1]
    if prev_b is not None:
        bench_mo.append(bench.loc[dt] / bench.loc[prev_b] - 1)
        bench_dates.append(dt)
    prev_b = dt
bench_rets = pd.Series(bench_mo, index=bench_dates)

# ── Monte Carlo ───────────────────────────────────────────────────────
def mc_stats(returns: pd.Series, n_sim=N_SIM, seed=SEED):
    """Bootstrap-resampling. Returnerar array (n_sim × 3): [cagr, sharpe, mdd]."""
    rng = np.random.default_rng(seed)
    r   = returns.values
    n   = len(r)
    ny  = n / 12

    results = np.empty((n_sim, 3))
    for i in range(n_sim):
        s  = rng.choice(r, size=n, replace=True)
        # CAGR
        total = np.prod(1 + s)
        cagr  = total ** (1/ny) - 1
        # Sharpe (annualiserad från månadsdata)
        sh    = s.mean() * 12 / (s.std() * np.sqrt(12)) if s.std() > 0 else 0
        # MaxDD
        nav   = np.cumprod(1 + s)
        peak  = np.maximum.accumulate(nav)
        mdd   = ((nav - peak) / peak).min()
        results[i] = [cagr, sh, mdd]
    return results

print("Beräknar månadsavkastningar…")
strat_rets = get_monthly_returns(abs_mom=True, top_n=3, use_etf_cash=False)
strat_ec   = get_monthly_returns(abs_mom=True, top_n=3, use_etf_cash=True)

# Justera benchmark till samma period
bench_rets = bench_rets.loc[strat_rets.index[0]:strat_rets.index[-1]]

print(f"Kör {N_SIM:,} Monte Carlo-simuleringar per strategi…")
mc_strat = mc_stats(strat_rets)
mc_ec    = mc_stats(strat_ec)
mc_bench = mc_stats(bench_rets)

# ── Rapport ───────────────────────────────────────────────────────────
def pct_str(arr, col, pcts=(5, 25, 50, 75, 95)):
    vals = np.percentile(arr[:, col], pcts)
    return "  ".join(f"P{p:<2}={v*100:+6.1f}%" for p, v in zip(pcts, vals))

def mdd_str(arr, pcts=(5, 25, 50, 75, 95)):
    vals = np.percentile(arr[:, 2], pcts)
    return "  ".join(f"P{p:<2}={v*100:+6.1f}%" for p, v in zip(pcts, vals))

ny   = len(strat_rets) / 12
obs_cagr  = (np.prod(1 + strat_rets.values)) ** (1/ny) - 1
obs_sh    = strat_rets.mean()*12 / (strat_rets.std()*np.sqrt(12))
obs_mdd   = ((np.cumprod(1+strat_rets.values) / np.maximum.accumulate(np.cumprod(1+strat_rets.values))) - 1).min()
b_cagr    = (np.prod(1 + bench_rets.values)) ** (1/ny) - 1
b_sh      = bench_rets.mean()*12 / (bench_rets.std()*np.sqrt(12))

print()
print("=" * 80)
print(f"MONTE CARLO  —  {N_SIM:,} bootstrap-simuleringar  ({len(strat_rets)} månader, {ny:.1f} år)")
print("=" * 80)
print(f"  Observerad period: {strat_rets.index[0].date()} → {strat_rets.index[-1].date()}")
print()

strategies = [
    ("top3 + abs-mom (optimal)", mc_strat, obs_cagr, obs_sh),
    ("top3 + abs-mom + ETF-cash", mc_ec,
     (np.prod(1+strat_ec.values))**(1/ny)-1,
     strat_ec.mean()*12/(strat_ec.std()*np.sqrt(12))),
    ("AP7 Aktiefond (benchmark)", mc_bench, b_cagr, b_sh),
]

for name, mc, obs_c, obs_s in strategies:
    print(f"  ── {name}")
    print(f"     Observerad:   CAGR {obs_c*100:+.1f}%   Sharpe {obs_s:.2f}")
    print(f"     CAGR:         {pct_str(mc, 0)}")
    print(f"     Sharpe:       {'  '.join(f'P{p:<2}={v:+.2f}' for p, v in zip([5,25,50,75,95], np.percentile(mc[:,1],[5,25,50,75,95])))}")
    print(f"     MaxDD:        {mdd_str(mc)}")
    # Sannolikheter
    p_beat = (mc_strat[:,0] > mc_bench[:,0]).mean() if "AP7" not in name else None
    p_pos  = (mc[:,0] > 0).mean()
    p_under15 = (mc[:,0] > 0.15).mean()
    if p_beat is not None:
        print(f"     P(slår AP7):  {p_beat*100:.1f}%   P(CAGR>0): {p_pos*100:.1f}%   P(CAGR>15%): {p_under15*100:.1f}%")
    else:
        print(f"     P(CAGR>0):    {p_pos*100:.1f}%   P(CAGR>15%): {p_under15*100:.1f}%")
    print()

# ── MaxDD-fördelning ──────────────────────────────────────────────────
print("=" * 80)
print("MaxDD-fördelning (sannolikhet för DD värre än tröskel)")
print("=" * 80)
thresholds = [-0.05, -0.10, -0.15, -0.20, -0.25, -0.30]
print(f"  {'Tröskel':>10}  {'top3+abs-mom':>14}  {'top3+abs+ETF':>14}  {'AP7':>14}")
print(f"  {'-'*58}")
for thr in thresholds:
    p1 = (mc_strat[:,2] < thr).mean()
    p2 = (mc_ec[:,2] < thr).mean()
    pb = (mc_bench[:,2] < thr).mean()
    print(f"  DD < {thr*100:>5.0f}%    {p1*100:>13.1f}%  {p2*100:>13.1f}%  {pb*100:>13.1f}%")

# ── Percentil-sammanfattning ──────────────────────────────────────────
print()
print("=" * 80)
print("PERCENTIL-SAMMANFATTNING  —  CAGR")
print("=" * 80)
pcts = [5, 10, 25, 50, 75, 90, 95]
print(f"  {'Percentil':>10}  {'top3+abs-mom':>14}  {'top3+abs+ETF':>14}  {'AP7':>14}")
print(f"  {'-'*58}")
for p in pcts:
    v1 = np.percentile(mc_strat[:,0], p) * 100
    v2 = np.percentile(mc_ec[:,0], p) * 100
    vb = np.percentile(mc_bench[:,0], p) * 100
    print(f"  P{p:<9}    {v1:>13.1f}%  {v2:>13.1f}%  {vb:>13.1f}%")
