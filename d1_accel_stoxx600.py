"""
d1_accel_stoxx600.py
====================
D1-ACCEL on a EUROZONE subset of STOXX 600 (~160 tickers).
All stocks are EUR-denominated (France, Germany, Netherlands, Spain,
Italy, Belgium, Austria, Finland). Non-EUR markets excluded to avoid
currency mixing in the backtest.

Period: 2010-01-01 → today.
Gate:   EXSA.DE (iShares STOXX Europe 600 ETF) 84d return ≤ 0 → cash.
Config: lb=63, win=10, ema=8, 30bp.
TOP_NS: [5, 10, 20].

Data downloaded from yfinance and cached in stoxx600_data/.

UNVALIDATED: survivorship bias present. No historical membership data.
"""

import warnings, json, time
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")

ROOT       = Path(__file__).parent
CACHE_DIR  = ROOT / "stoxx600_data"
CACHE_DIR.mkdir(exist_ok=True)
RESULTS    = ROOT / "results"
RESULTS.mkdir(exist_ok=True)

LB        = 63
WIN       = 10
EMA_SPAN  = 8
TOP_NS    = [5, 10, 20]
COST      = 0.003
REG_LB    = 84
START     = "2010-01-01"
DL_START  = "2008-01-01"
CAPITAL   = 100_000.0

GATE_TICKER   = "EXSA.DE"   # iShares STOXX Europe 600 ETF (EUR)
GATE_FALLBACK = "^STOXX"   # STOXX Europe 600 index (fallback)

# ── Universe ──────────────────────────────────────────────────────────────────
# ~160 Eurozone STOXX 600 stocks, all naturally EUR-denominated.
# Countries: France (.PA), Germany (.DE), Netherlands (.AS), Spain (.MC),
#            Italy (.MI), Belgium (.BR), Austria (.VI), Finland (.HE).
# Non-EUR markets excluded (UK/GBX, CHF, SEK, NOK, DKK) to avoid
# currency mixing in the portfolio calculation.
# Survivorship-biased (current members). Accepted — same as OMXS broad.
UNIVERSE = [
    # ── France (.PA) ──────────────────────────────────────────────────
    "MC.PA",    # LVMH
    "TTE.PA",   # TotalEnergies
    "SAN.PA",   # Sanofi
    "AIR.PA",   # Airbus
    "OR.PA",    # L'Oréal
    "RMS.PA",   # Hermès
    "DG.PA",    # VINCI
    "BNP.PA",   # BNP Paribas
    "SU.PA",    # Schneider Electric
    "AI.PA",    # Air Liquide
    "EL.PA",    # EssilorLuxottica
    "SAF.PA",   # Safran
    "RI.PA",    # Pernod Ricard
    "SGO.PA",   # Saint-Gobain
    "PUB.PA",   # Publicis
    "ML.PA",    # Michelin
    "BN.PA",    # Danone
    "KER.PA",   # Kering
    "CS.PA",    # AXA
    "GLE.PA",   # Société Générale
    "ACA.PA",   # Crédit Agricole
    "DSY.PA",   # Dassault Systèmes
    "CA.PA",    # Carrefour
    "ORA.PA",   # Orange
    "EN.PA",    # Bouygues
    "CAP.PA",   # Capgemini
    "LR.PA",    # Legrand
    "HO.PA",    # Thales
    "TEP.PA",   # Teleperformance
    "RNO.PA",   # Renault
    "VIE.PA",   # Veolia
    "ENGI.PA",  # Engie
    "STMPA.PA", # STMicroelectronics
    "TE.PA",    # Technip Energies
    "FGR.PA",   # Eiffage
    "ALO.PA",   # Alstom
    "FR.PA",    # Valeo
    "FRVIA.PA", # Forvia (Faurecia)
    "RCO.PA",   # Rémy Cointreau
    "SOP.PA",   # Sopra Steria
    "AC.PA",    # Accor

    # ── Germany (.DE) ─────────────────────────────────────────────────
    "SAP.DE",   # SAP
    "SIE.DE",   # Siemens
    "ALV.DE",   # Allianz
    "DTE.DE",   # Deutsche Telekom
    "MBG.DE",   # Mercedes-Benz
    "BMW.DE",   # BMW
    "BAYN.DE",  # Bayer
    "BAS.DE",   # BASF
    "VOW3.DE",  # Volkswagen
    "IFX.DE",   # Infineon
    "ENR.DE",   # Siemens Energy
    "DHL.DE",   # DHL Group
    "ADS.DE",   # Adidas
    "MUV2.DE",  # Munich Re
    "EOAN.DE",  # E.ON
    "DBK.DE",   # Deutsche Bank
    "CBK.DE",   # Commerzbank
    "HEN3.DE",  # Henkel
    "BEI.DE",   # Beiersdorf
    "RWE.DE",   # RWE
    "FRE.DE",   # Fresenius
    "FME.DE",   # Fresenius Medical Care
    "VNA.DE",   # Vonovia
    "MTX.DE",   # MTU Aero Engines
    "ZAL.DE",   # Zalando
    "CON.DE",   # Continental
    "SY1.DE",   # Symrise
    "SRT3.DE",  # Sartorius (pref)
    "BNR.DE",   # Brenntag
    "DB1.DE",   # Deutsche Börse
    "MRK.DE",   # Merck KGaA
    "RHM.DE",   # Rheinmetall
    "SHL.DE",   # Siemens Healthineers
    "HNR1.DE",  # Hannover Re
    "AIXA.DE",  # AIXTRON
    "PAH3.DE",  # Porsche Automobil Holding
    "P911.DE",  # Porsche AG
    "BOSS.DE",  # Hugo Boss
    "PUM.DE",   # Puma
    "EVK.DE",   # Evonik
    "SDF.DE",   # K+S
    "AFX.DE",   # Carl Zeiss Meditec
    "WCH.DE",   # Wacker Chemie
    "G1A.DE",   # GEA Group
    "KBX.DE",   # Knorr-Bremse
    "NEM.DE",   # Nemetschek
    "G24.DE",   # Scout24

    # ── Netherlands (.AS) ─────────────────────────────────────────────
    "ASML.AS",  # ASML
    "SHELL.AS", # Shell
    "INGA.AS",  # ING
    "HEIA.AS",  # Heineken
    "WKL.AS",   # Wolters Kluwer
    "AKZA.AS",  # Akzo Nobel
    "NN.AS",    # NN Group
    "RAND.AS",  # Randstad
    "ADYEN.AS", # Adyen
    "ABN.AS",   # ABN AMRO
    "DSFIR.AS", # DSM-Firmenich
    "PHIA.AS",  # Philips
    "IMCD.AS",  # IMCD
    "MT.AS",    # ArcelorMittal
    "AGN.AS",   # Aegon
    "BESI.AS",  # BE Semiconductor
    "ASM.AS",   # ASM International
    "UMG.AS",   # Universal Music Group
    "LIGHT.AS", # Signify
    "PRX.AS",   # Prosus
    "FLOW.AS",  # Flow Traders
    "JDEP.AS",  # JDE Peet's
    "OCI.AS",   # OCI

    # ── Spain (.MC) ───────────────────────────────────────────────────
    "ITX.MC",   # Inditex
    "IBE.MC",   # Iberdrola
    "SAN.MC",   # Banco Santander
    "BBVA.MC",  # BBVA
    "REP.MC",   # Repsol
    "TEF.MC",   # Telefónica
    "ACS.MC",   # ACS
    "AMS.MC",   # Amadeus IT
    "IAG.MC",   # IAG
    "CABK.MC",  # CaixaBank
    "NTGY.MC",  # Naturgy
    "ELE.MC",   # Endesa
    "AENA.MC",  # Aena
    "GRF.MC",   # Grifols
    "FER.MC",   # Ferrovial
    "MAP.MC",   # Mapfre
    "MRL.MC",   # Merlin Properties

    # ── Italy (.MI) ───────────────────────────────────────────────────
    "UCG.MI",   # UniCredit
    "ENEL.MI",  # Enel
    "ENI.MI",   # ENI
    "ISP.MI",   # Intesa Sanpaolo
    "RACE.MI",  # Ferrari
    "G.MI",     # Assicurazioni Generali
    "LDO.MI",   # Leonardo
    "TRN.MI",   # Terna
    "SRG.MI",   # Snam
    "MB.MI",    # Mediobanca
    "PST.MI",   # Poste Italiane
    "NEXI.MI",  # Nexi
    "MONC.MI",  # Moncler
    "PRY.MI",   # Prysmian
    "BAMI.MI",  # Banco BPM
    "CPR.MI",   # Campari
    "A2A.MI",   # A2A
    "IG.MI",    # Italgas

    # ── Belgium (.BR) ─────────────────────────────────────────────────
    "ABI.BR",   # Anheuser-Busch InBev
    "UCB.BR",   # UCB
    "AGS.BR",   # Ageas
    "UMI.BR",   # Umicore
    "GLPG.BR",  # Galapagos
    "SOF.BR",   # Sofina
    "GBLB.BR",  # Groupe Bruxelles Lambert

    # ── Austria (.VI) ─────────────────────────────────────────────────
    "EBS.VI",   # Erste Group Bank
    "OMV.VI",   # OMV
    "VOE.VI",   # voestalpine
    "VIG.VI",   # Vienna Insurance Group
    "RBI.VI",   # Raiffeisen Bank International
    "ANDR.VI",  # Andritz

    # ── Finland (.HE) — Eurozone member ───────────────────────────────
    "NOKIA.HE",  # Nokia
    "KNEBV.HE",  # KONE
    "NESTE.HE",  # Neste
    "UPM.HE",    # UPM-Kymmene
    "SAMPO.HE",  # Sampo
    "STERV.HE",  # Stora Enso R
    "METSO.HE",  # Metso
    "WRT1V.HE",  # Wärtsilä
    "FORTUM.HE", # Fortum
    "ORNBV.HE",  # Orion B
]

UNIVERSE = list(dict.fromkeys(UNIVERSE))  # deduplicate, preserve order


# ── Price cache ────────────────────────────────────────────────────────────────
def _cache_path(ticker: str) -> Path:
    safe = ticker.replace("/", "_").replace("^", "_").replace("-", "_")
    return CACHE_DIR / f"{safe}.csv.gz"


def load_price(ticker: str) -> pd.DataFrame | None:
    p = _cache_path(ticker)
    if p.exists():
        try:
            df = pd.read_csv(p, index_col=0, parse_dates=True, compression="gzip")
            if not df.empty and df.index[-1] >= pd.Timestamp.today() - pd.Timedelta(days=5):
                return df
        except Exception:
            pass
    # Download
    try:
        df = yf.download(ticker, start=DL_START, progress=False, auto_adjust=True)
        if df.empty:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df[["High", "Low", "Close"]].dropna()
        df.index = pd.to_datetime(df.index)
        df.to_csv(p, compression="gzip")
        return df
    except Exception:
        return None


# ── D1-ACCEL signal ────────────────────────────────────────────────────────────
def score_series(close: pd.Series, high: pd.Series, low: pd.Series) -> pd.Series:
    hl2   = (high + low) / 2
    ema   = hl2.ewm(span=EMA_SPAN, adjust=False).mean()
    roc   = ema.pct_change(LB)
    delta = ema.diff()
    accel = delta.rolling(WIN).mean() - delta.rolling(WIN * 2).mean()
    accel_n = accel / ema.abs().replace(0, np.nan)
    return (roc + accel_n).rename("score")


# ── Regime gate ───────────────────────────────────────────────────────────────
def load_gate() -> pd.Series:
    """Load EXSA.DE (STOXX 600 ETF) close; fall back to ^STOXX index."""
    for ticker in [GATE_TICKER, GATE_FALLBACK]:
        df = load_price(ticker)
        if df is not None and not df.empty:
            print(f"Gate loaded: {ticker} ({len(df)} rows)")
            return df["Close"].dropna()
    raise RuntimeError("Could not load regime gate — both EXSA.DE and ^STOXX failed")


# ── Backtest ───────────────────────────────────────────────────────────────────
def run_backtest(prices: dict[str, pd.DataFrame], gate: pd.Series, top_n: int) -> list[dict]:
    """
    Daily mark-to-market backtest with month-end rebalancing.
    Transaction cost = COST × total turnover (buy + sell) per rebal.
    """
    tickers = list(prices.keys())

    # Align all price series to a common daily index
    all_dates = sorted({d for df in prices.values() for d in df.index if str(d)[:10] >= START})
    dates     = pd.DatetimeIndex(all_dates)

    close_wide = pd.concat(
        {t: prices[t]["Close"].rename(t) for t in tickers}, axis=1
    ).reindex(dates).ffill()

    gate_aligned = gate.reindex(dates).ffill()
    gate_arr     = gate_aligned.values

    # Month-end rebalance set
    s_dates   = pd.Series(dates)
    rebal_set = set(s_dates.groupby(s_dates.dt.to_period("M")).last().values)

    min_pts = LB * 2 + WIN * 2 + EMA_SPAN + 10
    start_ts = pd.Timestamp(START)

    # Pre-compute scores on a monthly basis (at each rebal date)
    pos_map = {d: i for i, d in enumerate(dates)}

    # Build score arrays per ticker
    score_df: dict[str, np.ndarray] = {}
    for t in tickers:
        df = prices[t].reindex(dates).ffill()
        s  = score_series(df["Close"], df["High"], df["Low"]).values
        score_df[t] = s

    # ── Main loop ─────────────────────────────────────────────────────
    shares: dict[str, float] = {}   # current positions (shares)
    cash   = CAPITAL
    nav    = []

    pending_target: dict[str, float] | None = None  # weights → execute next bar

    for i, date in enumerate(dates):
        if date < start_ts:
            continue

        # Execute pending rebalance at today's open (use today's close as proxy)
        if pending_target is not None:
            px = {t: float(close_wide.at[date, t])
                  for t in list(shares) + list(pending_target)
                  if t in close_wide.columns and np.isfinite(close_wide.at[date, t])}
            port_val = cash + sum(shares.get(t, 0) * px.get(t, 0) for t in shares)
            new_sh = {t: (port_val * w) / px[t]
                      for t, w in pending_target.items()
                      if px.get(t, 0) > 0}
            turnover = sum(
                abs(new_sh.get(t, 0) * px.get(t, 0) - shares.get(t, 0) * px.get(t, 0))
                for t in set(shares) | set(new_sh)
            )
            cash   = port_val - sum(new_sh[t] * px[t] for t in new_sh) - turnover * COST
            shares = new_sh
            pending_target = None

        # Mark to market
        held_val = sum(
            shares[t] * float(close_wide.at[date, t])
            for t in shares
            if t in close_wide.columns and np.isfinite(close_wide.at[date, t])
        )
        nav.append({"date": date.strftime("%Y-%m-%d"), "value": round(cash + held_val, 2)})

        if date not in rebal_set:
            continue

        # ── Rebalance signal ──────────────────────────────────────────
        pos = pos_map[date]

        # Regime gate
        in_regime = True
        if pos >= REG_LB:
            g0, glb = gate_arr[pos], gate_arr[pos - REG_LB]
            if np.isfinite(g0) and np.isfinite(glb) and glb > 0:
                in_regime = (g0 / glb - 1) > 0

        if not in_regime:
            pending_target = {}  # go to cash
            continue

        # Score eligible tickers
        raw: dict[str, float] = {}
        for t in tickers:
            if pos < min_pts:
                continue
            s = score_df[t][pos]
            if np.isfinite(s):
                raw[t] = float(s)

        if not raw:
            pending_target = {}
            continue

        ranked   = sorted(raw, key=raw.__getitem__, reverse=True)
        top_tkrs = ranked[:top_n]
        w        = 1.0 / len(top_tkrs)
        pending_target = {t: w for t in top_tkrs}

    return nav


# ── Stats ──────────────────────────────────────────────────────────────────────
def calc_stats(nav: list[dict]) -> dict:
    if not nav:
        return {}
    df  = pd.DataFrame(nav).set_index("date")["value"]
    rets = df.pct_change().dropna()
    years = len(df) / 252
    cagr  = (df.iloc[-1] / df.iloc[0]) ** (1 / max(years, 0.01)) - 1
    vol   = rets.std() * np.sqrt(252)
    sharpe = (rets.mean() * 252) / vol if vol > 0 else 0
    roll_max = df.cummax()
    dd    = (df - roll_max) / roll_max
    mdd   = float(dd.min())
    return {
        "cagr":   round(float(cagr), 4),
        "vol":    round(float(vol), 4),
        "sharpe": round(float(sharpe), 3),
        "mdd":    round(mdd, 4),
        "years":  round(years, 1),
    }


# ── Benchmark: EXSA.DE total return ───────────────────────────────────────────
def calc_benchmark(gate: pd.Series) -> list[dict]:
    sub = gate.loc[gate.index >= pd.Timestamp(START)]
    if sub.empty:
        return []
    base = sub.iloc[0]
    return [{"date": d.strftime("%Y-%m-%d"), "value": round(v / base * CAPITAL, 2)}
            for d, v in sub.items()]


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    print(f"=== D1-ACCEL STOXX 600 | lb={LB} win={WIN} ema={EMA_SPAN} ===\n")

    print("Loading gate (EXSA.DE / ^STOXX)…")
    gate = load_gate()
    print(f"  Gate: {gate.index[0].date()} → {gate.index[-1].date()}, {len(gate)} days\n")

    print(f"Downloading {len(UNIVERSE)} tickers…")
    prices: dict[str, pd.DataFrame] = {}
    failed = []
    for i, tkr in enumerate(UNIVERSE):
        df = load_price(tkr)
        if df is not None and len(df) > 100:
            prices[tkr] = df
        else:
            failed.append(tkr)
        if (i + 1) % 20 == 0:
            print(f"  {i+1}/{len(UNIVERSE)} — loaded {len(prices)}, failed {len(failed)}")
        time.sleep(0.05)

    print(f"\nLoaded: {len(prices)} tickers, failed/skipped: {len(failed)}")
    if failed:
        print("  Failed:", ", ".join(failed[:20]))
    print()

    benchmark = calc_benchmark(gate)

    results = {}
    for n in TOP_NS:
        print(f"Running Top-{n}…", end=" ", flush=True)
        nav   = run_backtest(prices, gate, n)
        stats = calc_stats(nav)
        print(f"CAGR={stats.get('cagr', 0):.1%}  Sharpe={stats.get('sharpe', 0):.2f}  MDD={stats.get('mdd', 0):.1%}")
        results[f"stoxx600_top{n}"] = {
            "label": f"STOXX 600 Top-{n}",
            "nav":   nav,
            "stats": stats,
            "params": {"lb": LB, "win": WIN, "ema": EMA_SPAN, "top_n": n, "cost": COST},
        }

    out = {
        "generated_at": pd.Timestamp.now().isoformat(),
        "universe_size": len(UNIVERSE),
        "loaded": len(prices),
        "failed": failed,
        "strategies": results,
        "benchmark": {
            "label": "STOXX Europe 600 ETF (EXSA.DE)",
            "series": benchmark,
        },
    }

    out_path = RESULTS / "stoxx600_results.json"
    out_path.write_text(json.dumps(out, separators=(",", ":")))
    print(f"\nSaved → {out_path}")

    # Summary table
    print("\n── Summary ──────────────────────────────────────────────────")
    print(f"{'Strategy':<20} {'CAGR':>7} {'Vol':>7} {'Sharpe':>7} {'MDD':>8} {'Years':>6}")
    print("-" * 60)
    for key, r in results.items():
        s = r["stats"]
        print(f"{r['label']:<20} {s.get('cagr',0):>7.1%} {s.get('vol',0):>7.1%} "
              f"{s.get('sharpe',0):>7.2f} {s.get('mdd',0):>8.1%} {s.get('years',0):>6.1f}")


if __name__ == "__main__":
    main()
