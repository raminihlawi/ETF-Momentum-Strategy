#!/usr/bin/env python3
"""
PPM Curated Universe — Parameter Sweep
=======================================
Söker efter konfigurationer som ger lägre MaxDD utan att offra för mycket CAGR.

Strategier som testas:
  1. Ren momentum (accel / raw ROC)
  2. Absolut momentum-filter: om bästa fondens ROC < 0 → AP7 Räntefond
  3. Trailing DD-stop: om portföljens DD från topp > tröskel → AP7 Räntefond
  4. ETF cash-synk (D1-ACCEL signal från data.json)
  5. Kombinationer av ovanstående

Universum: 14 fonder (+ AP7 Aktiefond som valbart alternativ)
"""

import json
import itertools
import numpy as np
import pandas as pd
from pathlib import Path

DATA_FILE = Path(__file__).parent / "ppm_all_nav.csv"
ETF_JSON  = Path(__file__).parent / "dashboard/frontend/static/data.json"

# ── Parametrar ────────────────────────────────────────────────────────
BENCH_PPM = "581371"  # AP7 Aktiefond — benchmark OCH möjligt val
CASH_PPM  = "545541"  # AP7 Räntefond — defensivt alternativ
ETF_STRAT = "d1_accel"

UNIVERSE = {
    "581371": "AP7 Aktie",        # nu valbar — passiv global med hävstång
    "283408": "Tech",
    "644005": "Healthcare",
    "517748": "Energy",
    "481911": "Mining",
    "479550": "Consumer Brands",
    "768556": "US Value",
    "916354": "US Small",
    "456475": "US Quality",
    "163923": "US Growth",
    "182759": "EUR Small",
    "538462": "EUR Value",
    "162099": "Multifactor",
    "545541": "Ränta (AP7)",
}

# ── Sweep-parametrar ──────────────────────────────────────────────────
EMA_SPANS   = [3, 5, 10]
ROC_PERIODS = [42, 63, 84, 126]     # 2m, 3m, 4m, 6m
ACCEL_WINS  = [10, 15, 30]
TOP_NS      = [1, 2, 3]
DD_STOPS    = [None, -0.15, -0.20]  # None = ingen stop
ABS_MOM     = [False, True]         # absolut momentum-filter (ROC < 0 → Ränta)
ETF_CASH    = [False, True]

# ── Ladda ETF cash-månader ────────────────────────────────────────────
with open(ETF_JSON) as f:
    etf_d = json.load(f)
alloc_e   = etf_d["strategies"][ETF_STRAT]["allocation"]
cash_idx  = alloc_e["tickers"].index("CASH")
etf_cash_months = {
    (pd.Timestamp(dt).year, pd.Timestamp(dt).month)
    for dt, w in zip(alloc_e["dates"], alloc_e["weights"])
    if w[cash_idx] > 0
}

# ── Ladda PPM-data ────────────────────────────────────────────────────
print("Laddar data…")
df   = pd.read_csv(DATA_FILE, parse_dates=["date"], dtype={"ppm_number": str})
df   = df[df["date"] > "2000-01-01"]
wide = df.pivot_table(index="date", columns="ppm_number",
                      values="nav_sek", aggfunc="last").sort_index()
wide = wide.reindex(pd.date_range(wide.index.min(), wide.index.max(), freq="B")).ffill()

bench = wide[BENCH_PPM].copy()
funds = wide[[c for c in UNIVERSE if c in wide.columns]].copy()

bench_start = bench.iloc[0]
bench_nav   = bench / bench_start * 100_000

month_ends = pd.date_range(
    wide.index.min() + pd.DateOffset(months=6),
    wide.index.max(),
    freq="BME"
)
month_ends = month_ends[month_ends <= wide.index.max()]

# Benchmark stats
b_vals  = pd.Series({
    avail[-1]: float(bench_nav.loc[avail[-1]])
    for me in month_ends
    if len(avail := bench.index[bench.index <= me]) > 0
})
b_mo    = b_vals.pct_change().dropna()
b_ny    = (b_vals.index[-1] - b_vals.index[0]).days / 365.25
b_cagr  = (b_vals.iloc[-1] / 100_000) ** (1/b_ny) - 1
b_sh    = b_mo.mean()*12 / (b_mo.std()*np.sqrt(12))
b_mdd   = ((b_vals - b_vals.cummax()) / b_vals.cummax()).min()

# ── Signal-cache ──────────────────────────────────────────────────────
print("Förberäknar signaler…")
_score_cache = {}

def get_scores(ema_span, roc_days, accel_win):
    key = (ema_span, roc_days, accel_win)
    if key not in _score_cache:
        ema   = funds.ewm(span=ema_span, adjust=False).mean()
        roc   = ema / ema.shift(roc_days) - 1
        accel = roc - roc.shift(accel_win)
        _score_cache[key] = (roc + accel, roc)  # (accel_score, raw_roc)
    return _score_cache[key]

def get_raw(roc_days):
    key = ("raw", roc_days)
    if key not in _score_cache:
        _score_cache[key] = (funds / funds.shift(roc_days) - 1, None)
    return _score_cache[key]

# Förberäkna alla kombinationer
for es, rd, aw in itertools.product(EMA_SPANS, ROC_PERIODS, ACCEL_WINS):
    get_scores(es, rd, aw)
for rd in ROC_PERIODS:
    get_raw(rd)

# ── Backtest-kärna ────────────────────────────────────────────────────
def backtest(scores, roc_series, top_n, dd_stop, abs_mom, etf_cash):
    capital   = 100_000.0
    nav       = capital
    peak_nav  = capital
    holdings  = None
    prev_me   = None
    nav_vals  = []

    for me in month_ends:
        avail = wide.index[wide.index <= me]
        if len(avail) == 0:
            continue
        dt = avail[-1]

        # Trailing DD-stop check
        dd_now = nav / peak_nav - 1
        force_cash = (dd_stop is not None and dd_now < dd_stop)

        # ETF cash-override
        etf_in_cash = etf_cash and (me.year, me.month) in etf_cash_months

        if force_cash or etf_in_cash:
            picks = [CASH_PPM] if CASH_PPM in funds.columns else []
        else:
            sc_row  = scores.loc[dt].dropna()
            # filtrera bort fonder utan tillräcklig historik
            min_d   = max(scores.index[scores.notna().any(axis=1)][0], wide.index[0])
            eligible = [
                c for c in funds.columns
                if funds[c].first_valid_index() is not None
                and (dt - funds[c].first_valid_index()).days >= 100
                and c in sc_row.index
                and not np.isnan(sc_row[c])
            ]
            if not eligible:
                nav_vals.append(nav)
                continue

            sc_elig = sc_row[eligible].nlargest(top_n)
            picks   = list(sc_elig.index)

            # Absolut momentum-filter: om bästa fondens raw ROC < 0 → Räntefond
            if abs_mom and roc_series is not None:
                best_roc = float(roc_series.loc[dt, picks[0]]) if picks[0] in roc_series.columns else 0
                if best_roc < 0:
                    picks = [CASH_PPM] if CASH_PPM in funds.columns else picks

        # NAV-uppdatering
        if prev_me is not None and holdings:
            prev_avail = wide.index[wide.index <= prev_me]
            if len(prev_avail) > 0:
                p0  = prev_avail[-1]
                w   = 1.0 / len(holdings)
                ret = sum(
                    funds.loc[dt, p] / funds.loc[p0, p] - 1
                    for p in holdings if p in funds.columns
                ) * w
                nav *= (1 + ret)
                peak_nav = max(peak_nav, nav)

        holdings = picks
        prev_me  = me
        nav_vals.append(nav)

    if len(nav_vals) < 6:
        return None
    s    = pd.Series(nav_vals)
    mo_r = s.pct_change().dropna()
    ny   = (month_ends[len(nav_vals)-1] - month_ends[0]).days / 365.25
    if ny < 1:
        return None
    cagr = (s.iloc[-1] / capital) ** (1/ny) - 1
    sh   = mo_r.mean()*12 / (mo_r.std()*np.sqrt(12)) if mo_r.std() > 0 else 0
    peak = s.cummax()
    mdd  = ((s - peak) / peak).min()
    return cagr, sh, mdd

# ── Sweep ─────────────────────────────────────────────────────────────
print("Kör sweep…\n")
results = []

for ema_span, roc_days, accel_win, top_n, dd_stop, abs_m, etf_c in itertools.product(
        EMA_SPANS, ROC_PERIODS, ACCEL_WINS, TOP_NS, DD_STOPS, ABS_MOM, ETF_CASH):

    sc, raw_roc = get_scores(ema_span, roc_days, accel_win)
    res = backtest(sc, raw_roc, top_n, dd_stop, abs_m, etf_c)
    if res:
        cagr, sh, mdd = res
        results.append({
            "ema": ema_span, "roc": roc_days, "accel": accel_win,
            "top_n": top_n, "dd_stop": dd_stop,
            "abs_mom": abs_m, "etf_cash": etf_c,
            "cagr": cagr, "sharpe": sh, "mdd": mdd,
            "score": sh,   # sorterar på Sharpe
        })

# ── Råsignal (utan EMA-accel) ─────────────────────────────────────────
for roc_days, top_n, dd_stop, abs_m, etf_c in itertools.product(
        ROC_PERIODS, TOP_NS, DD_STOPS, ABS_MOM, ETF_CASH):

    sc, _ = get_raw(roc_days)
    res = backtest(sc, sc, top_n, dd_stop, abs_m, etf_c)
    if res:
        cagr, sh, mdd = res
        results.append({
            "ema": 0, "roc": roc_days, "accel": 0,
            "top_n": top_n, "dd_stop": dd_stop,
            "abs_mom": abs_m, "etf_cash": etf_c,
            "cagr": cagr, "sharpe": sh, "mdd": mdd,
            "score": sh,
        })

df_r = pd.DataFrame(results).sort_values("sharpe", ascending=False)

print(f"Totalt {len(df_r)} konfigurationer testade.")
print()

# ── Topp-20 på Sharpe ─────────────────────────────────────────────────
print("=" * 100)
print("TOPP-20 PÅ SHARPE")
print("=" * 100)
print(f"{'Signal':<14} {'ROC':>4} {'Ac':>4} {'N':>2}  {'DDstop':>7}  {'AbsMom':>6}  {'ETFcsh':>6}  {'CAGR':>7}  {'Sharpe':>7}  {'MaxDD':>7}  {'vs AP7':>7}")
print("-" * 100)
for _, row in df_r.head(20).iterrows():
    sig   = f"EMA{int(row['ema'])}" if row['ema'] > 0 else "RAW"
    stop  = f"{row['dd_stop']*100:.0f}%" if row['dd_stop'] else "  —  "
    vs    = (row['cagr'] - b_cagr) * 100
    print(f"  {sig:<12} {int(row['roc']):>4} {int(row['accel']):>4} {int(row['top_n']):>2}  "
          f"{stop:>7}  {'✓' if row['abs_mom'] else '·':>6}  {'✓' if row['etf_cash'] else '·':>6}  "
          f"{row['cagr']*100:>6.1f}%  {row['sharpe']:>7.2f}  {row['mdd']*100:>6.1f}%  "
          f"{'+' if vs>=0 else ''}{vs:>5.1f}pp")

# ── Topp-20 på Sharpe bland konfigurationer med MaxDD > -25% ──────────
safe = df_r[df_r["mdd"] > -0.25].sort_values("sharpe", ascending=False)
print()
print("=" * 100)
print("TOPP-20 PÅ SHARPE  —  begränsat till MaxDD > -25%")
print("=" * 100)
print(f"{'Signal':<14} {'ROC':>4} {'Ac':>4} {'N':>2}  {'DDstop':>7}  {'AbsMom':>6}  {'ETFcsh':>6}  {'CAGR':>7}  {'Sharpe':>7}  {'MaxDD':>7}  {'vs AP7':>7}")
print("-" * 100)
for _, row in safe.head(20).iterrows():
    sig   = f"EMA{int(row['ema'])}" if row['ema'] > 0 else "RAW"
    stop  = f"{row['dd_stop']*100:.0f}%" if row['dd_stop'] else "  —  "
    vs    = (row['cagr'] - b_cagr) * 100
    print(f"  {sig:<12} {int(row['roc']):>4} {int(row['accel']):>4} {int(row['top_n']):>2}  "
          f"{stop:>7}  {'✓' if row['abs_mom'] else '·':>6}  {'✓' if row['etf_cash'] else '·':>6}  "
          f"{row['cagr']*100:>6.1f}%  {row['sharpe']:>7.2f}  {row['mdd']*100:>6.1f}%  "
          f"{'+' if vs>=0 else ''}{vs:>5.1f}pp")

if safe.empty:
    print("  (inga konfigurationer klarar MaxDD > -25%)")

# ── Benchmark ─────────────────────────────────────────────────────────
print()
print(f"  AP7 Aktiefond (benchmark)                                              "
      f"{b_cagr*100:>6.1f}%  {b_sh:>7.2f}  {b_mdd*100:>6.1f}%")

# ── Pareto-front: bästa CAGR för varje MaxDD-bucket ──────────────────
print()
print("=" * 60)
print("PARETO  —  bästa CAGR per MaxDD-nivå (Sharpe ≥ 0.50)")
print("=" * 60)
buckets = [(-0.10, -0.05), (-0.15, -0.10), (-0.20, -0.15),
           (-0.25, -0.20), (-0.30, -0.25), (-0.40, -0.30)]
for lo, hi in buckets:
    sub = df_r[(df_r["mdd"] >= lo) & (df_r["mdd"] < hi) & (df_r["sharpe"] >= 0.50)]
    if sub.empty:
        continue
    best = sub.sort_values("cagr", ascending=False).iloc[0]
    sig  = f"EMA{int(best['ema'])}" if best['ema'] > 0 else "RAW"
    stop = f"{best['dd_stop']*100:.0f}%" if best['dd_stop'] else "—"
    print(f"  MaxDD {lo*100:.0f}%…{hi*100:.0f}%:  "
          f"CAGR {best['cagr']*100:.1f}%  Sharpe {best['sharpe']:.2f}  "
          f"({sig} ROC{int(best['roc'])} top{int(best['top_n'])} "
          f"stop={stop} abs={'✓' if best['abs_mom'] else '·'} etf={'✓' if best['etf_cash'] else '·'})")
