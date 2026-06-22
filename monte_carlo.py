#!/usr/bin/env python3
"""
Monte Carlo Simulation — D1-accel
==================================
Bootstrap-resampling av historiska månadsavkastningar (med återläggning).
Kör N simulerade portföljbanor med samma längd som den historiska perioden.

Metod: stationär block-bootstrap (block=3 månader) för att bevara
kortfristig autokorrelation i momentum-strategins avkastningar.

Usage: python3 monte_carlo.py [--n 10000] [--block 3] [--seed 42]
"""

import sys
import json
import argparse
import numpy as np
import pandas as pd
from pathlib import Path

DATA_PATH = Path(__file__).parent / "dashboard/frontend/static/data.json"
CAPITAL   = 100_000

# ── Args ─────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser()
parser.add_argument("--n",     type=int, default=10_000, help="Antal simuleringar")
parser.add_argument("--block", type=int, default=3,      help="Block-längd (månader)")
parser.add_argument("--seed",  type=int, default=42,     help="Random seed")
args = parser.parse_args()

N      = args.n
BLOCK  = args.block
SEED   = args.seed

# ── Load historical returns ──────────────────────────────────────────
with open(DATA_PATH) as f:
    data = json.load(f)

nav_raw = data["strategies"]["d1_accel"]["nav"]
df = pd.DataFrame(nav_raw)
df["date"]  = pd.to_datetime(df["date"])
df = df.set_index("date").sort_index()

# Monthly returns (end-of-month NAV)
mo_nav  = df["value"].resample("ME").last()
mo_rets = mo_nav.pct_change().dropna().values   # shape: (T,)
T       = len(mo_rets)
n_years = T / 12

# Benchmark: MSCI World monthly returns (same period)
bench_raw = data["benchmarks"]["MSCI World"]["series"]
bdf = pd.DataFrame(bench_raw).set_index("date")
bdf.index = pd.to_datetime(bdf.index)
bench_mo  = bdf["value"].resample("ME").last().pct_change().dropna()
# Align to same months as strategy
bench_mo  = bench_mo.reindex(mo_nav.index[1:]).dropna().values

# Historical actuals
hist_cagr   = float(data["strategies"]["d1_accel"]["stats"]["cagr"])
hist_sharpe = float(data["strategies"]["d1_accel"]["stats"]["sharpe"])
hist_mdd_mo = float(data["strategies"]["d1_accel"]["stats"]["max_dd_monthly"])

print(f"\nHistorisk D1-accel:  CAGR {hist_cagr*100:.1f}%  "
      f"Sharpe {hist_sharpe:.2f}  MaxDD(mo) {hist_mdd_mo*100:.1f}%")
print(f"Period: {mo_nav.index[0].date()} – {mo_nav.index[-1].date()}  "
      f"({T} månader / {n_years:.1f} år)")
print(f"\nKör {N:,} Monte Carlo-simuleringar  |  block={BLOCK}m  |  seed={SEED}")
print("─" * 70)

# ── Block bootstrap ──────────────────────────────────────────────────
rng    = np.random.default_rng(SEED)
cagrs  = np.empty(N)
sharps = np.empty(N)
mdds   = np.empty(N)
finals = np.empty(N)   # slutvärde som multipel av startkapital

for i in range(N):
    # Sample blocks with replacement to fill T months
    sim_rets = np.empty(T)
    filled   = 0
    while filled < T:
        start = rng.integers(0, T - BLOCK + 1)
        block = mo_rets[start : start + BLOCK]
        take  = min(BLOCK, T - filled)
        sim_rets[filled : filled + take] = block[:take]
        filled += take

    # Equity curve
    nav = CAPITAL * np.cumprod(1 + sim_rets)

    # CAGR
    cagr = (nav[-1] / CAPITAL) ** (1 / n_years) - 1
    cagrs[i]  = cagr

    # Sharpe (annualised)
    sharps[i] = np.mean(sim_rets) * 12 / (np.std(sim_rets, ddof=1) * np.sqrt(12))

    # MaxDD on simulated monthly NAV
    peak     = np.maximum.accumulate(nav)
    mdds[i]  = ((nav - peak) / peak).min()

    finals[i] = nav[-1] / CAPITAL

# ── Results ──────────────────────────────────────────────────────────
pcts = [5, 10, 25, 50, 75, 90, 95]

def row(arr, fmt=".1f", scale=100):
    return "  ".join(f"p{p:>2}: {np.percentile(arr*scale, p):>{5+len(fmt)}{'f' if 'f' in fmt else 's'}}"
                     for p in pcts)

print(f"\n{'CAGR (%)':}")
print(f"  " + "  ".join(f"p{p:>2}: {np.percentile(cagrs*100, p):>5.1f}%" for p in pcts))

print(f"\n{'Sharpe-kvot':}")
print(f"  " + "  ".join(f"p{p:>2}: {np.percentile(sharps, p):>5.2f} " for p in pcts))

print(f"\n{'Max Drawdown månadsslut (%)':}")
print(f"  " + "  ".join(f"p{p:>2}: {np.percentile(mdds*100, p):>5.1f}%" for p in pcts))

print(f"\n{'Slutvärde (× startkapital)':}")
print(f"  " + "  ".join(f"p{p:>2}: {np.percentile(finals, p):>5.2f}x " for p in pcts))

# Key probabilities
p_pos_cagr   = np.mean(cagrs > 0) * 100
p_gt10       = np.mean(cagrs > 0.10) * 100
p_gt15       = np.mean(cagrs > 0.15) * 100
p_gt_hist    = np.mean(cagrs > hist_cagr) * 100
p_mdd_lt15   = np.mean(mdds > -0.15) * 100   # MaxDD bättre än -15%
p_mdd_lt20   = np.mean(mdds > -0.20) * 100
p_sh_gt1     = np.mean(sharps > 1.0) * 100

# Beat MSCI World CAGR
bench_cagr = (1 + bench_mo).prod() ** (12 / len(bench_mo)) - 1 if len(bench_mo) > 0 else 0
p_beat_bench = np.mean(cagrs > bench_cagr) * 100

print(f"\n{'─'*70}")
print("SANNOLIKHETER")
print(f"{'─'*70}")
print(f"  P(CAGR > 0%)         = {p_pos_cagr:>5.1f}%")
print(f"  P(CAGR > 10%)        = {p_gt10:>5.1f}%")
print(f"  P(CAGR > 15%)        = {p_gt15:>5.1f}%")
print(f"  P(CAGR > historisk {hist_cagr*100:.1f}%) = {p_gt_hist:>5.1f}%")
print(f"  P(slå MSCI World {bench_cagr*100:.1f}%) = {p_beat_bench:>5.1f}%")
print(f"  P(MaxDD bättre än -15%) = {p_mdd_lt15:>5.1f}%")
print(f"  P(MaxDD bättre än -20%) = {p_mdd_lt20:>5.1f}%")
print(f"  P(Sharpe > 1.0)      = {p_sh_gt1:>5.1f}%")

# Downside scenarios
print(f"\n{'─'*70}")
print("NEDSIDE-SCENARIER (värsta percentiler)")
print(f"{'─'*70}")
print(f"  Värsta 5%  av utfall:  CAGR {np.percentile(cagrs*100, 5):>5.1f}%  "
      f"Sharpe {np.percentile(sharps, 5):>4.2f}  MaxDD {np.percentile(mdds*100, 5):>5.1f}%")
print(f"  Värsta 10% av utfall:  CAGR {np.percentile(cagrs*100, 10):>5.1f}%  "
      f"Sharpe {np.percentile(sharps, 10):>4.2f}  MaxDD {np.percentile(mdds*100, 10):>5.1f}%")
print(f"  Median (p50):          CAGR {np.percentile(cagrs*100, 50):>5.1f}%  "
      f"Sharpe {np.percentile(sharps, 50):>4.2f}  MaxDD {np.percentile(mdds*100, 50):>5.1f}%")
print(f"  Bästa 10% av utfall:   CAGR {np.percentile(cagrs*100, 90):>5.1f}%  "
      f"Sharpe {np.percentile(sharps, 90):>4.2f}  MaxDD {np.percentile(mdds*100, 90):>5.1f}%")

print(f"\n  Förväntad CAGR (medel):  {np.mean(cagrs)*100:.1f}%  "
      f"±{np.std(cagrs)*100:.1f}pp (1σ)")
print(f"  Förväntad Sharpe (medel): {np.mean(sharps):.2f}  "
      f"±{np.std(sharps):.2f} (1σ)")
print()
