#!/usr/bin/env python3
"""
PPM Full Universe Sweep
=======================
Alla ~567 PPM-fonder. Constraint: max 1 fond per kategori i portföljen.
Sweep: top-N = [2,3,4,5], rebalansfrekvens = [månadsvis, varannan vecka, kvartalsvis].
Signal: EMA(5) × ROC(84d) + acceleration(15d). Benchmark: AP7 Aktiefond.

Usage: python3 sweep_ppm.py
"""

import re
import numpy as np
import pandas as pd
from pathlib import Path
from itertools import product

DATA_FILE = Path(__file__).parent / "ppm_all_nav.csv"
BENCH_PPM = "581371"   # AP7 Aktiefond

EMA_SPAN  = 5
ROC_DAYS  = 84
ACCEL_WIN = 15
MIN_DAYS      = ROC_DAYS + 2 * ACCEL_WIN + 20   # ~134 handelsdagar för signal
MIN_HIST_DAYS = 500    # fond måste ha >500 handelsdagar total historik

TOP_NS    = [2, 3, 4, 5]
REBAL_FREQS = {
    "Månadsvis":       "BME",
    "Varannan vecka":  "2W",
    "Kvartalsvis":     "BQE",
}

# Kategorier som INTE tillåts som portföljinnehav
# (för volatila/nischade för rotation — guld, råvaror, energi, blandade)
EXCLUDED_CATS = {
    "Sektor Energi",      # olja/gas — extremt cyklisk
    "Sektor Råvaror",     # guld, mining — spikig och mean-reverting
    "Sektor Fastighet",   # REIT — för nischad
    "Sektor Finans",      # banker — cyklisk, ej indexlik rotation
    "Sektor Konsument",   # consumer goods — nischad
    "Blandfond",          # inherent diversifierade, ger aldrig toppmomentum
    "Övrigt",             # okategoriserade — okänd risk
}

# ── Kategorisering via nyckelord ──────────────────────────────────────
def categorize(name: str) -> str:
    n = name.lower()
    # Räntefonder
    if re.search(r'ränte|obligation|frn|likviditet|kortränta|bond|kredit|high.?yield|penningmark|realränta', n):
        if re.search(r'kort|likviditet|penningmark|frn', n):
            return "Ränta Kort"
        if re.search(r'realränta|inflation', n):
            return "Ränta Realränta"
        return "Ränta Lång/Kredit"
    # Blandfonder
    if re.search(r'bland|mixfond|balans|försiktig|offensiv|generation|transfer|livscykel|allokering', n):
        return "Blandfond"
    # Sektorer — måste komma FÖRE geografi-fällor (gold/world, resources/global etc.)
    # Biotech måste fångas FÖRE tech (annars matchar "biotech " på "tech ")
    if re.search(r'hälsovård|healthcare|health|medicin|bioteknologi|biotech|farmaceut|läkemedel|pharma', n):
        return "Sektor Hälsovård"
    if re.search(r'teknik|technology|tech |digital|it-fond|kommunik', n):
        return "Sektor Tech"
    if re.search(r'energi|energy|olja|petroleum|clean energy|förnybar', n):
        return "Sektor Energi"
    if re.search(r'råvaror|mining|gruv|naturresurs|metall|mineral|material|resources|resource|gold|guld|silver|precious|commodity|commodit', n):
        return "Sektor Råvaror"
    if re.search(r'fastighet|real estate|property|infrastruktur|reit', n):
        return "Sektor Fastighet"
    if re.search(r'finans|bank |financial', n):
        return "Sektor Finans"
    if re.search(r'konsument|varumärke|brand|food|nutrition|livsmedel', n):
        return "Sektor Konsument"
    # Volatilitets- och specialstrategifonder → Övrigt
    if re.search(r'volatil|absolute return|market neutral|long.?short|hedge|arbitrage', n):
        return "Övrigt"
    # Geografi
    if re.search(r'sverige|svensk|nordic|norden|nordisk|stockholm', n):
        if re.search(r'småbol|micro|small', n):
            return "Aktier Sverige Småbolag"
        return "Aktier Sverige"
    if re.search(r'europa|europe|european', n):
        if re.search(r'småbol|small', n):
            return "Aktier Europa Småbolag"
        return "Aktier Europa"
    if re.search(r'\busa\b|amerik|nordamerik| us |u\.s\.', n):
        if re.search(r'småbol|small|mid|micro', n):
            return "Aktier USA Småbolag"
        return "Aktier USA"
    if re.search(r'japan|asien|asia|kina|china|indien|india|vietnam|korea|taiwan', n):
        return "Aktier Asien"
    if re.search(r'tillväxt|emerging|latam|latin|afrika|africa|brasilien|ryssland', n):
        return "Aktier Tillväxt"
    if re.search(r'global|värld|world|international|multi', n):
        if re.search(r'småbol|small', n):
            return "Aktier Global Småbolag"
        return "Aktier Global"
    if re.search(r'småbol|micro cap|small cap', n):
        return "Aktier Småbolag Övrigt"
    return "Övrigt"

# ── Ladda data ────────────────────────────────────────────────────────
print("Laddar data…")
df = pd.read_csv(DATA_FILE, dtype={"ppm_number": str}, parse_dates=["date"])
df = df[df["date"] > "2000-01-01"]

# Pivot till wide format
wide = df.pivot_table(index="date", columns="ppm_number",
                      values="nav_sek", aggfunc="last")
wide = wide.sort_index()

# Full affärsdag-kalender + forward-fill
all_days = pd.date_range(wide.index.min(), wide.index.max(), freq="B")
wide     = wide.reindex(all_days).ffill()

bench    = wide[BENCH_PPM].copy()
funds    = wide.drop(columns=[BENCH_PPM], errors="ignore")

# Kategorier per fond
fund_meta = df[["ppm_number","name"]].drop_duplicates().set_index("ppm_number")
categories = {ppm: categorize(fund_meta.loc[ppm, "name"])
              for ppm in funds.columns if ppm in fund_meta.index}

cat_counts = pd.Series(categories).value_counts()
print(f"\nFonder per kategori ({len(cat_counts)} kategorier, {len(funds.columns)} fonder totalt):")
for cat, cnt in cat_counts.items():
    print(f"  {cat:<30} {cnt:>3} fonder")

# ── Accel-signal (beräknas en gång) ──────────────────────────────────
print("\nBeräknar signaler…")
ema    = funds.ewm(span=EMA_SPAN, adjust=False).mean()
roc    = ema / ema.shift(ROC_DAYS) - 1
accel  = roc - roc.shift(ACCEL_WIN)
scores = roc + accel

# Markera fonder med tillräcklig historik per datum
first_valid = funds.apply(lambda s: s.first_valid_index())

def eligible_on(dt):
    """Fonder med tillräcklig historik på datum dt."""
    return [
        c for c in funds.columns
        if first_valid[c] is not None
        and (dt - first_valid[c]).days >= MIN_DAYS
        and (wide.index[-1] - first_valid[c]).days >= MIN_HIST_DAYS
        and categories.get(c, "Övrigt") not in EXCLUDED_CATS
        and pd.notna(scores.loc[dt, c])
    ]

# ── Backtest-funktion ─────────────────────────────────────────────────
def backtest(rebal_dates, top_n, label=""):
    capital   = 100_000.0
    nav_v     = capital
    holdings  = {}   # {ppm: weight}
    prev_date = None
    nav_series  = []
    alloc_log   = []

    for dt in rebal_dates:
        # Närmaste tillgängliga datum
        avail = wide.index[wide.index <= dt]
        if len(avail) == 0:
            continue
        d = avail[-1]

        # Uppdatera NAV baserat på prisrörelse sedan förra datum
        if prev_date is not None and holdings:
            prev_avail = wide.index[wide.index <= prev_date]
            if len(prev_avail) > 0:
                pd0 = prev_avail[-1]
                ret = sum(
                    funds.loc[d, ppm] / funds.loc[pd0, ppm] - 1
                    for ppm in holdings
                    if ppm in funds.columns
                ) * (1 / len(holdings))
                nav_v *= (1 + ret)

        # Välj top-N fonder, max 1 per kategori
        elig   = eligible_on(d)
        if not elig:
            nav_series.append((d, nav_v))
            continue

        sc_row = scores.loc[d, elig].dropna().sort_values(ascending=False)
        picked = {}
        used_cats = set()
        for ppm, score in sc_row.items():
            cat = categories.get(ppm, "Övrigt")
            if cat not in used_cats:
                picked[ppm] = score
                used_cats.add(cat)
            if len(picked) == top_n:
                break

        holdings  = picked
        prev_date = dt
        nav_series.append((d, nav_v))
        alloc_log.append((d, {fund_meta.loc[p,"name"][:25]: round(s,4)
                               for p,s in picked.items()}))

    if len(nav_series) < 4:
        return None

    nav_s = pd.Series({d: v for d, v in nav_series})
    mo_r  = nav_s.pct_change().dropna()
    ny    = (nav_s.index[-1] - nav_s.index[0]).days / 365.25
    if ny < 0.5:
        return None
    cagr  = (nav_s.iloc[-1] / capital) ** (1/ny) - 1
    sh    = mo_r.mean() * 12 / (mo_r.std() * np.sqrt(12))  # annualiserar rough
    peak  = nav_s.cummax()
    mdd   = ((nav_s - peak) / peak).min()
    tot   = nav_s.iloc[-1] / capital - 1

    return dict(cagr=cagr, sharpe=sh, mdd=mdd, total=tot,
                final=nav_s.iloc[-1], nav=nav_s, alloc=alloc_log)

# ── Benchmark ─────────────────────────────────────────────────────────
bench_start = bench.iloc[0]
bench_nav   = bench / bench_start * 100_000

# ── Sweep ────────────────────────────────────────────────────────────
print("\nKör sweep…\n")
results = {}
for freq_label, freq in REBAL_FREQS.items():
    if freq == "2W":
        # Varannan vecka = var 10:e handelsdag
        rebal_dates = wide.index[::10]
    else:
        rebal_dates = pd.date_range(wide.index[0], wide.index[-1], freq=freq)
        rebal_dates = pd.DatetimeIndex([d for d in rebal_dates if d <= wide.index[-1]])

    for top_n in TOP_NS:
        key = (freq_label, top_n)
        res = backtest(rebal_dates, top_n, label=f"{freq_label} top{top_n}")
        results[key] = res
        if res:
            print(f"  {freq_label:<20} top-{top_n}  "
                  f"CAGR {res['cagr']*100:>5.1f}%  "
                  f"Sharpe {res['sharpe']:>5.2f}  "
                  f"MaxDD {res['mdd']*100:>6.1f}%  "
                  f"Total {res['total']*100:>6.1f}%")

# Benchmark stats
b_ny  = (bench_nav.index[-1] - bench_nav.index[0]).days / 365.25
b_mo  = bench_nav.pct_change().dropna()
b_cagr   = (bench_nav.iloc[-1] / 100_000) ** (1/b_ny) - 1
b_sharpe = b_mo.mean() * 12 / (b_mo.std() * np.sqrt(12))
b_mdd    = ((bench_nav - bench_nav.cummax()) / bench_nav.cummax()).min()
b_tot    = bench_nav.iloc[-1] / 100_000 - 1

print(f"\n  {'AP7 Aktiefond (benchmark)':<20}       "
      f"CAGR {b_cagr*100:>5.1f}%  "
      f"Sharpe {b_sharpe:>5.2f}  "
      f"MaxDD {b_mdd*100:>6.1f}%  "
      f"Total {b_tot*100:>6.1f}%")

# ── Sammanställning ───────────────────────────────────────────────────
print("\n" + "="*80)
print("SWEEP-SAMMANSTÄLLNING")
print("="*80)
print(f"{'Frekvens':<22} {'Top-N':>6} {'CAGR':>8} {'Sharpe':>8} {'MaxDD':>8} {'vs AP7':>8}")
print("-"*65)
for (freq_label, top_n), res in results.items():
    if not res:
        continue
    vs = (res['cagr'] - b_cagr) * 100
    sign = "+" if vs >= 0 else ""
    print(f"{freq_label:<22} {top_n:>6}    "
          f"{res['cagr']*100:>6.1f}%  "
          f"{res['sharpe']:>7.2f}  "
          f"{res['mdd']*100:>6.1f}%  "
          f"{sign}{vs:>5.1f}pp")
print(f"\n{'AP7 Aktiefond':^65}")
print(f"{'':22} {'':6}    {b_cagr*100:>6.1f}%  {b_sharpe:>7.2f}  {b_mdd*100:>6.1f}%  {'0.0pp':>8}")

# ── Bästa konfiguration: detaljvy ────────────────────────────────────
best_key = max(
    [(k, r) for k, r in results.items() if r],
    key=lambda x: x[1]["sharpe"]
)[0]
best = results[best_key]
print(f"\n{'='*80}")
print(f"BÄSTA SHARPE: {best_key[0]}, top-{best_key[1]}")
print(f"{'='*80}")
print(f"  CAGR {best['cagr']*100:.1f}%  Sharpe {best['sharpe']:.2f}  MaxDD {best['mdd']*100:.1f}%")
print(f"\n  Senaste 6 allokeringar:")
for dt, alloc in best["alloc"][-6:]:
    funds_str = "  |  ".join(f"{n}: {s:+.3f}" for n, s in alloc.items())
    print(f"    {dt.date()}  {funds_str}")

# Fondfördelning för bästa config
all_funds_picked = [n for _, alloc in best["alloc"] for n in alloc]
fc = pd.Series(all_funds_picked).value_counts().head(15)
print(f"\n  Vanligaste fondval:")
total_periods = len(best["alloc"])
for fname, cnt in fc.items():
    pct = cnt / total_periods * 100
    bar = "█" * int(pct / 3)
    print(f"    {fname:<28} {cnt:>3}×  {pct:>5.1f}%  {bar}")
