"""
d1_accel_omxs_gates.py
=======================
Three-way gate comparison for D1-ACCEL on OMX Stockholm.
UNVALIDATED (survivorship bias). Config fixed: lb=63, win=10, ema=8, 30bp.

Versions:
  1. no_gate   — pure rotation, no regime filter
  2. spy_gate  — SPY 84d return ≤ 0 → cash  (was used for US baseline)
  3. omxs_gate — XACT-OMXS30.ST 84d return ≤ 0 → cash (local index)

Goal: isolate gate vs mechanic. If (3) >> (2) ≈ baseline and (1) is flat →
mechanic doesn't replicate. If (3) >> (2) and (1) has some edge → gate was
mis-calibrated, mechanic replicates with local gate.

Note on prior run bug: d1_accel_omxs.py had a 1-row OMXS30 cache → NaN gate
→ effectively ran with no gate. Now corrected.
"""

import os, json, time, warnings
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")

ROOT        = Path(__file__).parent
CACHE_DIR   = ROOT / "omxs_data"
RESULTS_DIR = ROOT / "results"
CACHE_DIR.mkdir(exist_ok=True); RESULTS_DIR.mkdir(exist_ok=True)

LB     = 63
WIN    = 10
EMA    = 8
TOP_NS = [3, 5]
COST   = 0.003
REG_LB = 84
START  = "2019-10-01"
CAPITAL = 100_000.0

OMXS_TICKERS_SECTORS = {
    "SEB-A.ST":   "Financials", "SEB-C.ST":   "Financials",
    "SWED-A.ST":  "Financials", "NDA-SE.ST":  "Financials",
    "KINV-A.ST":  "Financials", "KINV-B.ST":  "Financials",
    "INVE-A.ST":  "Financials", "INVE-B.ST":  "Financials",
    "ATCO-A.ST":  "Financials", "ATCO-B.ST":  "Financials",
    "INDU-A.ST":  "Financials", "INDU-C.ST":  "Financials",
    "LUNDBERGF.ST":"Financials","EQT.ST":      "Financials",
    "BURE.ST":    "Financials", "LATO-B.ST":  "Financials",
    "FABG.ST":    "Financials", "SFAB.ST":    "Financials",
    "RATO-B.ST":  "Financials", "SAGAX-B.ST": "Real Estate",
    "CAST.ST":    "Real Estate","WIHL.ST":    "Real Estate",
    "HUFV-A.ST":  "Real Estate","NYFOSA.ST":  "Real Estate",
    "JM.ST":      "Real Estate","CEVI-B.ST":  "Real Estate",
    "LOOMIS.ST":  "Industrials",
    "VOLV-A.ST":  "Industrials","VOLV-B.ST":  "Industrials",
    "SAND.ST":    "Industrials","ALFA.ST":    "Industrials",
    "ASSA-B.ST":  "Industrials","HEXA-B.ST":  "Industrials",
    "SKF-B.ST":   "Industrials","SKA-B.ST":   "Industrials",
    "SWEC-B.ST":  "Industrials","WALL-B.ST":  "Industrials",
    "SAAB-B.ST":  "Industrials","TREL-B.ST":  "Industrials",
    "AXFO.ST":    "Industrials","BOL.ST":     "Materials",
    "NCAB.ST":    "Industrials","BUFAB.ST":   "Industrials",
    "OEM-B.ST":   "Industrials","XANO-B.ST":  "Industrials",
    "AAK.ST":     "Consumer Staples",
    "HUSQ-B.ST":  "Consumer Discretionary",
    "DOMETIC.ST": "Consumer Discretionary",
    "BHG-B.ST":   "Consumer Discretionary",
    "THULE.ST":   "Consumer Discretionary",
    "CLAS-B.ST":  "Consumer Discretionary",
    "AZN.ST":     "Health Care", "EKTA-B.ST": "Health Care",
    "GETI-B.ST":  "Health Care", "IMMNB-B.ST":"Health Care",
    "LIFCO-B.ST": "Health Care",
    "HM-B.ST":    "Consumer Discretionary",
    "ELUX-B.ST":  "Consumer Discretionary",
    "ICA.ST":     "Consumer Staples",
    "ESSITY-A.ST":"Consumer Staples","ESSITY-B.ST":"Consumer Staples",
    "SCA-B.ST":   "Materials",   "KIND-SDB.ST":"Consumer Discretionary",
    "ERIC-A.ST":  "Communication Services",
    "ERIC-B.ST":  "Communication Services",
    "TELE2-B.ST": "Communication Services",
    "TELIA.ST":   "Communication Services",
    "ADDNODE-B.ST":"Information Technology",
    "HMS.ST":     "Information Technology",
    "KNOW-B.ST":  "Information Technology",
    "ENEA.ST":    "Information Technology",
    "NIBE-B.ST":  "Industrials",
    "TOBII.ST":   "Information Technology",
    "SSAB-A.ST":  "Materials",   "SSAB-B.ST":  "Materials",
    "HOLM-B.ST":  "Materials",
    "DIOS.ST":    "Real Estate", "REJL-B.ST":  "Industrials",
    "EMBRAC-B.ST":"Consumer Discretionary",
    "INWI.ST":    "Information Technology",
    "NOBI.ST":    "Consumer Staples",
    "SECU-B.ST":  "Industrials",
    "GRNG.ST":    "Real Estate",
    "ISGR-B.ST":  "Industrials",
    "IVER.ST":    "Industrials",
    "PNDX-B.ST":  "Information Technology",
    "PREV.ST":    "Health Care",
    "SINT.ST":    "Industrials",
    "VIQ.ST":     "Industrials",
    "MEAB.ST":    "Industrials",
    "KLOV-B.ST":  "Real Estate",
    "FPAR-A.ST":  "Financials",
    "LOGI-B.ST":  "Information Technology",
}


# ── Data loading ───────────────────────────────────────────────────

def load_omxs_data():
    """Load from omxs_data cache (pre-built by d1_accel_omxs.py)."""
    min_len = LB + 2 * WIN + 50
    data = {}
    for t in OMXS_TICKERS_SECTORS:
        safe  = t.replace(".", "_").replace("-", "_")
        cache = CACHE_DIR / f"{safe}.csv.gz"
        if not cache.exists(): continue
        try:
            df = pd.read_csv(cache, index_col=0, parse_dates=True, compression="gzip")
            df = df[["High", "Low", "Close"]].dropna()
            if len(df) >= min_len:
                data[t] = df.sort_index()
        except Exception:
            pass
    return data


def load_spy():
    cache = CACHE_DIR / "_SPY.csv.gz"
    if cache.exists():
        try:
            df = pd.read_csv(cache, index_col=0, parse_dates=True, compression="gzip")
            cl = df["Close"].sort_index()
            if len(cl) > 1000:
                return cl.rename("SPY")
        except Exception:
            pass
    raw = yf.download("SPY", start="2014-01-01", auto_adjust=True, progress=False)
    raw.index = pd.to_datetime(raw.index)
    raw.columns = [c[0] if isinstance(c, tuple) else c for c in raw.columns]
    raw[["Close"]].to_csv(cache, compression="gzip")
    return raw["Close"].rename("SPY")


def load_omxs_gate():
    """XACT-OMXS30.ST — local OMXS regime index (SEK-denominated)."""
    cache = CACHE_DIR / "_XACT_OMXS30.csv.gz"
    if cache.exists():
        try:
            df  = pd.read_csv(cache, index_col=0, parse_dates=True, compression="gzip")
            cl  = df["Close"].sort_index()
            if len(cl) > 1000:
                return cl.rename("XACT-OMXS30")
        except Exception:
            pass
    raw = yf.download("XACT-OMXS30.ST", start="2014-01-01", auto_adjust=True, progress=False)
    raw.index = pd.to_datetime(raw.index)
    raw.columns = [c[0] if isinstance(c, tuple) else c for c in raw.columns]
    raw[["Close"]].to_csv(cache, compression="gzip")
    return raw["Close"].rename("XACT-OMXS30")


# ── Simulation ────────────────────────────────────────────────────

def month_ends(idx):
    s = pd.Series(idx, index=idx)
    return set(s.groupby(s.dt.to_period("M")).apply(lambda g: g.index[-1]).values)


def accel(arr, pos):
    if pos < LB + 2 * WIN: return np.nan
    p0, plb = arr[pos], arr[pos - LB]
    pw, p2w  = arr[pos - WIN], arr[pos - 2 * WIN]
    if any(v <= 0 or np.isnan(v) for v in [p0, plb, pw, p2w]): return np.nan
    return (p0 / plb - 1) + (p0 / pw - 1) - (pw / p2w - 1)


def simulate(smooth_df, data, gate_close, top_n, gate_name):
    """
    gate_close: pd.Series or None (no gate).
    """
    tickers    = list(data.keys())
    ticker_set = set(tickers)
    all_dates  = smooth_df.index
    pos_map    = {d: i for i, d in enumerate(all_dates)}
    rebal_set  = month_ends(all_dates)
    start_ts   = pd.Timestamp(START)
    close_mat  = pd.concat({t: data[t]["Close"] for t in tickers},
                           axis=1).reindex(all_dates).ffill()
    smooth_arrs= {t: smooth_df[t].values for t in tickers if t in smooth_df.columns}

    # Gate arrays (pre-aligned)
    if gate_close is not None:
        gate_al  = gate_close.reindex(all_dates).ffill().bfill()
        gate_arr = gate_al.values
        # Validate: must have real data
        n_valid = int(np.sum(~np.isnan(gate_arr)))
        if n_valid < 100:
            raise ValueError(f"Gate '{gate_name}' has only {n_valid} valid rows after align — check data")
    else:
        gate_arr = None

    def get_px(t, d):
        if t in close_mat.columns and d in close_mat.index:
            v = close_mat.loc[d, t]
            return float(v) if not np.isnan(v) else 0.0
        return 0.0

    equity   = []
    alloc    = []
    cash_months = []
    holdings = {}
    cash     = CAPITAL
    pending  = None

    for date in all_dates:
        if date < start_ts: continue
        if pending is not None:
            all_h = set(holdings) | set(pending)
            px = {t: get_px(t, date) for t in all_h}
            port_val = cash + sum(holdings.get(t,0)*px.get(t,0) for t in holdings)
            new_sh   = {t:(port_val*w)/px[t] for t,w in pending.items() if px.get(t,0)>0}
            traded   = sum(abs(new_sh.get(t,0)*px.get(t,0)-holdings.get(t,0)*px.get(t,0)) for t in all_h)
            cash     = port_val - sum(new_sh[t]*px[t] for t in new_sh) - traded*COST
            holdings = new_sh; pending = None

        held_val = sum(holdings[t]*get_px(t,date) for t in holdings)
        equity.append({"date": date.strftime("%Y-%m-%d"), "value": round(cash+held_val, 2)})
        if date not in rebal_set: continue

        # ── Regime gate ──────────────────────────────────────────
        if gate_arr is not None:
            pos_i = pos_map[date]
            if pos_i >= REG_LB:
                g_now = gate_arr[pos_i]
                g_lb  = gate_arr[pos_i - REG_LB]
                if not (np.isnan(g_now) or np.isnan(g_lb) or g_lb <= 0):
                    gate_ret = g_now / g_lb - 1
                    if gate_ret <= 0:
                        pending = {"__CASH__": 1.0}
                        alloc.append({"date": date.strftime("%Y-%m-%d"),
                                      "holdings": {"CASH": 1.0}})
                        cash_months.append(date.strftime("%Y-%m"))
                        continue

        # ── Score & rank ──────────────────────────────────────────
        pos = pos_map[date]
        scores = {}
        for t in ticker_set:
            if t not in smooth_arrs: continue
            s = accel(smooth_arrs[t], pos)
            if not np.isnan(s): scores[t] = s
        if not scores: continue
        top = sorted(scores, key=scores.__getitem__, reverse=True)[:top_n]
        w   = {t: 1.0/len(top) for t in top}
        pending = w
        alloc.append({"date": date.strftime("%Y-%m-%d"),
                      "holdings": {t: round(v, 4) for t, v in w.items()}})

    return equity, alloc, cash_months


# ── Metrics ───────────────────────────────────────────────────────

def metrics(equity_list):
    if len(equity_list) < 20: return {}
    dates = pd.to_datetime([e["date"] for e in equity_list])
    vals  = np.array([e["value"] for e in equity_list], dtype=float)
    rets  = np.diff(vals) / vals[:-1]
    n_yrs = (dates[-1] - dates[0]).days / 365.25
    cagr  = (vals[-1] / vals[0]) ** (1/n_yrs) - 1 if n_yrs > 0 else 0
    vol   = np.std(rets, ddof=1) * np.sqrt(252)
    sharpe= (np.mean(rets)*252) / vol if vol > 0 else 0
    peak  = np.maximum.accumulate(vals)
    max_dd= float(((vals-peak)/peak).min())
    df = pd.DataFrame({"value": vals}, index=dates)
    annual = {}
    for yr, grp in df.groupby(df.index.year):
        yr_v = grp["value"].values
        yr_r = np.diff(yr_v)/yr_v[:-1]
        yr_ret= float(yr_v[-1]/yr_v[0]-1)
        yr_vol= float(np.std(yr_r,ddof=1)*np.sqrt(252)) if len(yr_r)>1 else 0
        yr_sh = float(np.mean(yr_r)*252/yr_vol) if yr_vol>0 else 0
        yr_pk = np.maximum.accumulate(yr_v)
        yr_dd = float(((yr_v-yr_pk)/yr_pk).min())
        annual[str(yr)] = {"ret": round(yr_ret,4), "sharpe": round(yr_sh,2),
                           "max_dd": round(yr_dd,4)}
    mo = {}
    for (yr,mon), grp in df.groupby([df.index.year, df.index.month]):
        mo.setdefault(str(yr), {})[str(mon)] = round(
            float(grp["value"].iloc[-1]/grp["value"].iloc[0]-1), 4)
    return {"cagr": round(float(cagr),4), "sharpe": round(float(sharpe),4),
            "max_dd": round(float(max_dd),4), "ann_vol": round(float(vol),4),
            "total": round(float(vals[-1]/vals[0]-1),4),
            "annual": annual, "monthly": mo,
            "max_dd_monthly": round(float(max_dd),4)}


def correlation_to_us(omxs_eq, us_key="sp500_pit_top7"):
    """Compute daily-return correlation between OMXS equity and US strategy."""
    try:
        with open(ROOT / "data.json") as f:
            us = json.load(f)
        us_nav = us["strategies"][us_key]["nav"]
        s1 = pd.Series({e["date"]: e["value"] for e in omxs_eq}).pct_change().dropna()
        s2 = pd.Series({e["date"]: e["value"] for e in us_nav}).pct_change().dropna()
        common = s1.align(s2, join="inner")
        return round(float(common[0].corr(common[1])), 3) if len(common[0]) > 30 else None
    except Exception:
        return None


# ── Main ──────────────────────────────────────────────────────────

def main():
    print("=" * 80)
    print("  D1-ACCEL OMXS — Gate Comparison  (3 versions, lb=63 win=10 ema=8)")
    print("  UNVALIDATED: survivorship bias, accepted.")
    print("=" * 80)

    print("\nLoading OMXS price data (from omxs_data/ cache) …")
    data = load_omxs_data()
    print(f"  {len(data)} tickers loaded")
    if len(data) < 10:
        print("  Too few tickers. Run d1_accel_omxs.py first to populate cache.")
        return

    print("Loading regime indexes …")
    spy   = load_spy()
    xact  = load_omxs_gate()
    print(f"  SPY:          {len(spy)} rows ({spy.index[0].date()} → {spy.index[-1].date()})")
    print(f"  XACT-OMXS30:  {len(xact)} rows ({xact.index[0].date()} → {xact.index[-1].date()})")

    print("Building smooth prices …")
    mid_df = pd.concat({t: ((data[t]["High"]+data[t]["Low"])/2).rename(t) for t in data}, axis=1)
    smooth = mid_df.ewm(span=EMA, adjust=False).mean().sort_index()

    # Gate configs: (name, display, close_series_or_None)
    gates = [
        ("no_gate",   "No gate (pure rotation)",  None),
        ("spy_gate",  "SPY 84d gate",              spy),
        ("omxs_gate", "XACT-OMXS30 84d gate (local)", xact),
    ]

    all_results = {}   # key: f"{gate_key}_top{n}" → dict

    print("\nRunning 6 configurations (3 gates × 2 N) …\n")
    for gate_key, gate_label, gate_close in gates:
        for n in TOP_NS:
            label = f"{gate_label}, Top-{n}"
            try:
                eq, alloc, cash_mos = simulate(smooth, data, gate_close, n, gate_key)
                m = metrics(eq)
                corr = correlation_to_us(eq, "sp500_pit_top7")
                key = f"{gate_key}_top{n}"
                all_results[key] = {
                    "label": label, "gate": gate_key, "n": n,
                    "equity": eq, "alloc": alloc,
                    "stats": m, "cash_months": cash_mos,
                    "corr_us_top7": corr,
                }
                cash_2022 = [c for c in cash_mos if c.startswith("2022")]
                print(f"  {label:<42}: Sharpe={m.get('sharpe',0):+.3f}  "
                      f"CAGR={m.get('cagr',0)*100:+.1f}%  "
                      f"MaxDD={m.get('max_dd',0)*100:.1f}%  "
                      f"cash2022={len(cash_2022)}mo  corrUS={corr}")
            except Exception as e:
                print(f"  {label}: FAILED — {e}")

    # ── Save equity CSVs ──────────────────────────────────────────
    for k, res in all_results.items():
        pd.Series({e["date"]: e["value"] for e in res["equity"]}).to_csv(
            RESULTS_DIR / f"omxs_{k}_equity.csv")

    # ── FULL REPORT ───────────────────────────────────────────────
    print("\n" + "=" * 80)
    print("  FULL RESULTS — OMXS Gate Comparison")
    print("=" * 80)

    hdr = f"  {'Config':<42}{'Sharpe':>8}{'CAGR':>9}{'MaxDD':>9}{'Vol':>8}{'CashMo':>8}{'CorrUS':>8}"
    print(hdr); print("  " + "-" * 80)

    for gate_key, gate_label, _ in gates:
        print(f"\n  ── {gate_label} ──")
        for n in TOP_NS:
            key = f"{gate_key}_top{n}"
            r   = all_results.get(key, {})
            m   = r.get("stats", {})
            label = f"Top-{n}, {gate_label}"
            corr  = r.get("corr_us_top7")
            n_cash= len(r.get("cash_months", []))
            print(f"  {label:<42}{m.get('sharpe',0):>+8.3f}{m.get('cagr',0)*100:>+8.1f}%"
                  f"{m.get('max_dd',0)*100:>+8.1f}%{m.get('ann_vol',0)*100:>7.1f}%"
                  f"{n_cash:>8}  {corr if corr is not None else '—':>6}")

    # ── 2022 deep dive ────────────────────────────────────────────
    print("\n" + "=" * 80)
    print("  2022 ANALYSIS (the critical bear market year)")
    print("=" * 80)
    print(f"  {'Config':<42}{'2022 ret':>10}{'2022 MaxDD':>12}{'Cash months':>14}")
    print("  " + "-" * 76)
    for gate_key, gate_label, _ in gates:
        for n in TOP_NS:
            key = f"{gate_key}_top{n}"
            r   = all_results.get(key, {})
            ann = r.get("stats", {}).get("annual", {}).get("2022", {})
            cash_2022 = [c for c in r.get("cash_months", []) if c.startswith("2022")]
            print(f"  Top-{n}, {gate_label:<38}"
                  f"{ann.get('ret',0)*100:>+9.1f}%"
                  f"{ann.get('max_dd',0)*100:>+11.1f}%"
                  f"  {', '.join(cash_2022) if cash_2022 else '(none)':>14}")

    # ── Annual tables for baseline configs ────────────────────────
    print("\n" + "=" * 80)
    print("  ANNUAL RETURNS — Top-5 across 3 gates")
    print("=" * 80)
    keys_to_show = ["no_gate_top5", "spy_gate_top5", "omxs_gate_top5"]
    labels_show  = ["No gate", "SPY gate", "OMXS-local gate"]
    years = sorted({yr for k in keys_to_show
                    for yr in all_results.get(k,{}).get("stats",{}).get("annual",{})})
    header = f"  {'Year':<8}" + "".join(f"{'Ret '+l:>16}" for l in labels_show)
    print(header); print("  " + "-" * (8 + 16*len(labels_show)))
    for yr in years:
        row = f"  {yr:<8}"
        for k in keys_to_show:
            a = all_results.get(k,{}).get("stats",{}).get("annual",{}).get(yr,{})
            ret = a.get("ret", None)
            row += f"{('+' if ret and ret>=0 else '')+f'{ret*100:.1f}%' if ret is not None else '—':>16}"
        print(row)

    # ── Verdict ───────────────────────────────────────────────────
    print("\n" + "=" * 80)
    print("  VERDICT")
    print("=" * 80)
    ng5  = all_results.get("no_gate_top5",   {}).get("stats", {})
    sp5  = all_results.get("spy_gate_top5",  {}).get("stats", {})
    om5  = all_results.get("omxs_gate_top5", {}).get("stats", {})

    print(f"\n  No-gate Top-5:         Sharpe={ng5.get('sharpe',0):+.3f}  CAGR={ng5.get('cagr',0)*100:+.1f}%  MaxDD={ng5.get('max_dd',0)*100:.1f}%")
    print(f"  SPY-gate Top-5:        Sharpe={sp5.get('sharpe',0):+.3f}  CAGR={sp5.get('cagr',0)*100:+.1f}%  MaxDD={sp5.get('max_dd',0)*100:.1f}%")
    print(f"  OMXS-local-gate Top-5: Sharpe={om5.get('sharpe',0):+.3f}  CAGR={om5.get('cagr',0)*100:+.1f}%  MaxDD={om5.get('max_dd',0)*100:.1f}%")

    def verdict():
        ng_sh = ng5.get("sharpe", 0)
        om_sh = om5.get("sharpe", 0)
        sp_sh = sp5.get("sharpe", 0)
        us_sh = 1.081   # S&P 500 Top-7 reference

        lines = []
        if ng_sh < 0.3:
            lines.append("• Mechanic has weak/no edge on OMXS (no-gate Sharpe < 0.3)")
            lines.append("  → Acceleration-rotation is more US-specific than hoped.")
        elif ng_sh >= 0.5:
            lines.append(f"• Mechanic DOES have some edge on OMXS (no-gate Sharpe {ng_sh:.2f})")
            if om_sh > ng_sh + 0.1:
                lines.append(f"  → Local gate lifts Sharpe by +{om_sh-ng_sh:.2f} → pattern replicates WITH local gate")
            else:
                lines.append("  → Gate adds little incremental benefit beyond the base mechanic")
        else:
            lines.append(f"• Marginal OMXS edge (Sharpe {ng_sh:.2f}) — weaker than US ({us_sh:.2f})")

        if om_sh > sp_sh + 0.05:
            lines.append(f"• Local OMXS gate clearly beats SPY gate (+{om_sh-sp_sh:.2f} Sharpe)")
            lines.append("  → Gate needed localizing, not mechanic — confirms gate was the suspect.")
        elif abs(om_sh - sp_sh) < 0.05:
            lines.append(f"• SPY and OMXS gates give similar results (Δ={om_sh-sp_sh:+.2f})")
            lines.append("  → The gate source isn't the culprit.")
        else:
            lines.append(f"• SPY gate actually beats OMXS gate ({sp_sh:.2f} vs {om_sh:.2f})")
            lines.append("  → Using US macro as protection works better on OMXS than local signal.")

        n_cash_om = len(all_results.get("omxs_gate_top5",{}).get("cash_months",[]))
        n_cash_sp = len(all_results.get("spy_gate_top5",{}).get("cash_months",[]))
        lines.append(f"\n  Gate activity: SPY gate={n_cash_sp} cash months, OMXS gate={n_cash_om} cash months total")

        return "\n".join(lines)

    print()
    print(verdict())
    print("\n" + "=" * 80)

    # ── Export for dashboard / notebook ───────────────────────────
    export = {}
    for gate_key, gate_label, _ in gates:
        for n in TOP_NS:
            k = f"{gate_key}_top{n}"
            r = all_results.get(k, {})
            eq    = r.get("equity", [])
            alloc = r.get("alloc",  [])
            stats = r.get("stats",  {})

            seen = []; dates_out = []; weights_out = []
            for entry in alloc:
                for t in entry["holdings"]:
                    if t not in seen: seen.append(t)
                dates_out.append(entry["date"])
                weights_out.append([round(entry["holdings"].get(t, 0.0), 4) for t in seen])

            cur = alloc[-1] if alloc else {}
            holdings_list = [{"ticker": t, "weight": w, "sleeve": "omxs",
                               "label": t.replace(".ST",""), "nordnet_name": "", "isin": ""}
                              for t, w in cur.get("holdings", {}).items()]

            export[k] = {
                "label":    f"OMXS {gate_label} — Top {n}",
                "nav":      eq,
                "stats":    stats,
                "allocation": {"tickers": seen, "dates": dates_out, "weights": weights_out},
                "current_signal": {
                    "date":     cur.get("date", ""),
                    "holdings": sorted(holdings_list, key=lambda x: -x["weight"])
                },
                "meta": {"gate": gate_key, "gate_label": gate_label, "n": n,
                          "cash_months": r.get("cash_months", []),
                          "corr_us_top7": r.get("corr_us_top7")}
            }

    export_path = ROOT / "omxs_gates_results.json"
    with open(export_path, "w") as f:
        json.dump(export, f)
    print(f"  Full results exported to {export_path}")


if __name__ == "__main__":
    main()
