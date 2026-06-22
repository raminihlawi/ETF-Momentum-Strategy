#!/usr/bin/env python3
"""
PPM Momentum Backtest
=====================
Samma accel-signal som D1-ACCEL men med PPM-fonder.
Universum: 12 aktiefonder + AP7 Räntefond som defensivt alternativ.
Benchmark: AP7 Aktiefond.

ETF-synk: när D1-ACCEL är i cash (data.json) → PPM håller AP7 Räntefond
oavsett momentum-signal. Strategierna går i synk med varandra.

Usage: python3 backtest_ppm.py
"""

import json
import numpy as np
import pandas as pd
from pathlib import Path

DATA_FILE  = Path(__file__).parent / "ppm_all_nav.csv"
ETF_JSON   = Path(__file__).parent / "dashboard/frontend/static/data.json"

# ── Parametrar ────────────────────────────────────────────────────────
EMA_SPAN   = 5
ROC_DAYS   = 63    # 3 månader — sweep visade att 63d slår 84d för detta universum
ACCEL_WIN  = 10    # 10d acceleration — snabbare än 15d, fångar vändningar bättre
BENCH_PPM  = "581371"   # AP7 Aktiefond — benchmark OCH möjligt val i rotation
CASH_PPM   = "545541"   # AP7 Räntefond — defensivt alternativ
ETF_STRAT  = "d1_accel" # vilken ETF-strategi styr cash-signalen

UNIVERSE = {
    "581371": "AP7 Aktie",        # passiv global med hävstång — möjligt momentumval
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
    "545541": "Ränta (AP7)",   # defensivt alternativ — väljs av signal ELLER ETF-cash
}

# ── Ladda ETF cash-datum ──────────────────────────────────────────────
def load_etf_cash_months(json_path: Path, strat: str) -> set:
    """Returnerar set av (year, month) då ETF-strategin är 100% i cash."""
    with open(json_path) as f:
        d = json.load(f)
    alloc   = d["strategies"][strat]["allocation"]
    tickers = alloc["tickers"]
    dates   = alloc["dates"]
    weights = alloc["weights"]
    cash_idx = tickers.index("CASH")
    cash_months = set()
    for dt_str, w in zip(dates, weights):
        if w[cash_idx] > 0:
            dt = pd.Timestamp(dt_str)
            cash_months.add((dt.year, dt.month))
    return cash_months

etf_cash_months = load_etf_cash_months(ETF_JSON, ETF_STRAT)
print(f"ETF cash-perioder ({len(etf_cash_months)} månader från {ETF_STRAT}):")
for ym in sorted(etf_cash_months):
    print(f"  {ym[0]}-{ym[1]:02d}")
print()

# ── Ladda PPM-data ────────────────────────────────────────────────────
df = pd.read_csv(DATA_FILE, parse_dates=["date"], dtype={"ppm_number": str})
df = df[df["date"] > "2000-01-01"]

wide = df.pivot_table(index="date", columns="ppm_number",
                      values="nav_sek", aggfunc="last").sort_index()
all_days = pd.date_range(wide.index.min(), wide.index.max(), freq="B")
wide = wide.reindex(all_days).ffill()

bench = wide[BENCH_PPM].copy()
funds = wide[[c for c in UNIVERSE if c in wide.columns]].copy()

print(f"Period:     {wide.index[0].date()} → {wide.index[-1].date()}")
print(f"Universum:  {len(funds.columns)} fonder  |  Benchmark: AP7 Aktiefond")
print(f"Signal:     EMA({EMA_SPAN}), ROC({ROC_DAYS}d), accel win={ACCEL_WIN}d")
print()

# ── Accel-signal ──────────────────────────────────────────────────────
def accel_score(prices: pd.Series) -> pd.Series:
    ema   = prices.ewm(span=EMA_SPAN, adjust=False).mean()
    roc   = ema / ema.shift(ROC_DAYS) - 1
    accel = roc - roc.shift(ACCEL_WIN)
    return roc + accel

scores  = funds.apply(accel_score)
# Råa ROC-värden för absolut momentum-filter (ROC < 0 → defensiv)
raw_roc = funds.apply(lambda p: p / p.shift(ROC_DAYS) - 1)

min_days = ROC_DAYS + 2 * ACCEL_WIN + 10

# ── Månadsslutsdatum ──────────────────────────────────────────────────
month_ends = pd.date_range(
    wide.index.min() + pd.DateOffset(months=4),
    wide.index.max(),
    freq="BME"
)
month_ends = month_ends[month_ends <= wide.index.max()]

# ── Backtest-funktion ─────────────────────────────────────────────────
def run_backtest(use_etf_cash: bool, top_n: int = 1, abs_mom: bool = False):
    capital      = 100_000.0
    nav          = capital
    holdings     = None
    prev_me_date = None
    nav_series   = []
    alloc_series = []
    trades       = 0
    cash_forced  = 0
    absmom_exits = 0

    for me in month_ends:
        avail = wide.index[wide.index <= me]
        if len(avail) == 0:
            continue
        dt = avail[-1]

        eligible = [
            c for c in funds.columns
            if funds[c].first_valid_index() is not None
            and (dt - funds[c].first_valid_index()).days >= min_days
            and not np.isnan(scores.loc[dt, c])
        ]
        if not eligible:
            continue

        # ETF cash-override
        in_etf_cash = use_etf_cash and (me.year, me.month) in etf_cash_months
        in_abs_mom  = False

        if in_etf_cash and CASH_PPM in funds.columns:
            picks = [CASH_PPM]
            cash_forced += 1
        else:
            row   = scores.loc[dt, eligible].nlargest(top_n)
            picks = list(row.index)

            # Absolut momentum-filter: om top-1 har negativt råROC → defensiv
            if abs_mom and CASH_PPM in funds.columns:
                best_roc = float(raw_roc.loc[dt, picks[0]]) if picks[0] in raw_roc.columns else 0
                if best_roc < 0:
                    picks = [CASH_PPM]
                    in_abs_mom = True
                    absmom_exits += 1

        # NAV-uppdatering baserat på tidigare innehav
        if prev_me_date is not None and holdings is not None:
            prev_avail = wide.index[wide.index <= prev_me_date]
            if len(prev_avail) > 0:
                p0  = prev_avail[-1]
                w   = 1.0 / len(holdings)
                ret = sum(funds.loc[dt, p] / funds.loc[p0, p] - 1 for p in holdings) * w
                nav *= (1 + ret)

        if picks != holdings:
            trades += 1

        holdings     = picks
        prev_me_date = me

        label = " + ".join(UNIVERSE.get(p, p) for p in picks)
        nav_series.append({"date": dt.date().isoformat(), "value": round(nav, 4)})
        alloc_series.append({
            "date":    dt.date().isoformat(),
            "fund":    label,
            "ppm":     picks[0] if len(picks) == 1 else picks,
            "cash":    in_etf_cash,
            "absmom":  in_abs_mom,
        })

    nav_df  = pd.DataFrame(nav_series).set_index("date")
    nav_df.index = pd.to_datetime(nav_df.index)
    mo_ret  = nav_df["value"].pct_change().dropna()
    n_years = (nav_df.index[-1] - nav_df.index[0]).days / 365.25
    cagr    = (nav_df["value"].iloc[-1] / capital) ** (1 / n_years) - 1
    sharpe  = mo_ret.mean() * 12 / (mo_ret.std() * np.sqrt(12))
    peak    = nav_df["value"].cummax()
    mdd     = ((nav_df["value"] - peak) / peak).min()
    total_r = nav_df["value"].iloc[-1] / capital - 1

    return dict(cagr=cagr, sharpe=sharpe, mdd=mdd, total=total_r,
                final=nav_df["value"].iloc[-1], trades=trades,
                cash_forced=cash_forced, absmom_exits=absmom_exits,
                nav=nav_df, alloc=alloc_series, n_years=n_years)

# ── Benchmark ─────────────────────────────────────────────────────────
bench_start  = bench.iloc[0]
bench_nav    = bench / bench_start * 100_000
bench_series = []
for me in month_ends:
    avail = bench.index[bench.index <= me]
    if len(avail) == 0:
        continue
    dt = avail[-1]
    bench_series.append({"date": dt.date().isoformat(), "value": round(float(bench_nav.loc[dt]), 4)})

bench_df    = pd.DataFrame(bench_series).set_index("date")
bench_df.index = pd.to_datetime(bench_df.index)
b_mo_ret    = bench_df["value"].pct_change().dropna()
n_years_b   = (bench_df.index[-1] - bench_df.index[0]).days / 365.25
b_cagr      = (bench_df["value"].iloc[-1] / 100_000) ** (1 / n_years_b) - 1
b_sharpe    = b_mo_ret.mean() * 12 / (b_mo_ret.std() * np.sqrt(12))
b_peak      = bench_df["value"].cummax()
b_mdd       = ((bench_df["value"] - b_peak) / b_peak).min()

# ── Kör varianter ─────────────────────────────────────────────────────
def raw_score(prices):
    return prices / prices.shift(ROC_DAYS) - 1

variants = [
    # label,                                   etf_cash, top_n, abs_mom
    ("top3 + abs-mom          (OPTIMAL)",       False,    3,     True),
    ("top3 + abs-mom + ETF-cash (LÄGST DD)",    True,     3,     True),
    ("top3 + ETF-cash",                         True,     3,     False),
    ("top1 + abs-mom",                          False,    1,     True),
    ("top1 + abs-mom + ETF-cash",               True,     1,     True),
    ("top1 (original)",                         False,    1,     False),
    ("top1 + ETF-cash (föregående bästa)",      True,     1,     False),
]
results = [(lbl, run_backtest(etf, n, am)) for lbl, etf, n, am in variants]

# ── Rapport ───────────────────────────────────────────────────────────
primary = results[0][1]

print("=" * 82)
print("PPM-ACCEL  vs  AP7 Aktiefond")
print(f"Signal: EMA({EMA_SPAN}), ROC({ROC_DAYS}d), accel({ACCEL_WIN}d)  |  +AP7 Aktiefond i universum")
print("=" * 82)
print(f"  Period:   {primary['nav'].index[0].date()} → {primary['nav'].index[-1].date()}  ({primary['n_years']:.1f} år)")
print()
print(f"  {'Variant':<40} {'CAGR':>7} {'Sharpe':>8} {'MaxDD':>8} {'Total':>8}")
print(f"  {'-'*75}")

for label, r in results:
    print(f"  {label:<40} {r['cagr']*100:>6.1f}% {r['sharpe']:>8.2f} {r['mdd']*100:>7.1f}% {r['total']*100:>7.1f}%")

b_total = (bench_df['value'].iloc[-1]/100_000 - 1)*100
print(f"  {'AP7 Aktiefond (benchmark)':<40} {b_cagr*100:>6.1f}% {b_sharpe:>8.2f} {b_mdd*100:>7.1f}% {b_total:>7.1f}%")

# ── Detalj för optimal variant ────────────────────────────────────────
best_lbl, best = results[0]
print()
print(f"  Detalj — {best_lbl}:")
print(f"  ETF-cash forced: {best['cash_forced']} mån  |  Abs-mom exits: {best['absmom_exits']} mån")
print()
print("  Fondfördelning:")
alloc_df    = pd.DataFrame(best["alloc"])
# Räkna individuella fonder (dela upp kombos)
all_picks = [f for row in best["alloc"] for f in row["fund"].split(" + ")]
from collections import Counter
fc = Counter(all_picks)
n_periods = len(best["alloc"])
for fund, cnt in sorted(fc.items(), key=lambda x: -x[1]):
    pct = cnt / n_periods * 100
    bar = "█" * int(pct / 4)
    print(f"    {fund:<28} {cnt:>3}×  {pct:>5.1f}%  {bar}")

print()
print("  Senaste 8 månader:")
for row in best["alloc"][-8:]:
    flags = ""
    if row["cash"]:   flags += "  [ETF-CASH]"
    if row["absmom"]: flags += "  [ABS-MOM]"
    print(f"    {row['date']}  →  {row['fund']:<38}{flags}")
