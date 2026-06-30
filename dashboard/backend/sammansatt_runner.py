"""
sammansatt_runner.py — Börslabbet Sammansatt Momentum backtest runner.

Reads cached prices from {data_root}/stock_prices/ and produces:
  {data_root}/results/omxs_sammansatt_results.json
  {data_root}/results/stoxx_sammansatt_results.json
  {data_root}/results/sp500_sammansatt_results.json
  {data_root}/results/global_sammansatt_results.json

Strategy: score = mean(ret_3m, ret_6m, ret_12m) with 1M skip.
Absolute momentum filter (score > 0 → else cash). Monthly rebalancing.
Global: top-N with max picks per universe to force diversification.
"""
import json
import logging
import time
from pathlib import Path

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# ── Strategy constants ────────────────────────────────────────────────
SKIP, LB3, LB6, LB12 = 21, 63, 126, 252
MIN_PTS  = SKIP + LB12 + 20
COST     = 0.003
CAPITAL  = 100_000.0
START    = "2006-01-01"


# ── Helpers ───────────────────────────────────────────────────────────
def _composite_score(arr: np.ndarray, pos: int) -> float:
    if pos < MIN_PTS:
        return np.nan
    p_s = arr[pos - SKIP]
    if p_s <= 0 or np.isnan(p_s):
        return np.nan
    vals = [arr[pos - SKIP - lb] for lb in (LB3, LB6, LB12)]
    if any(v <= 0 or np.isnan(v) for v in vals):
        return np.nan
    return sum(p_s / v - 1 for v in vals) / 3.0


def _calc_stats(nav: list[dict]) -> dict:
    s = pd.Series({e["date"]: e["value"] for e in nav}, dtype=float)
    s.index = pd.to_datetime(s.index)
    r = s.pct_change().dropna()
    y = len(s) / 252
    cagr = float((s.iloc[-1] / s.iloc[0]) ** (1 / y) - 1)
    vol  = float(r.std() * 252 ** 0.5)
    sh   = float(r.mean() * 252 / vol) if vol > 0 else 0.0
    mdd  = float(((s - s.cummax()) / s.cummax()).min())
    total = float(s.iloc[-1] / s.iloc[0] - 1)
    s_m  = s.resample("ME").last()
    m_r  = s_m.pct_change().dropna()
    monthly: dict = {}
    for d, v in m_r.items():
        monthly.setdefault(str(d.year), {})[str(d.month)] = round(float(v), 6)
    return dict(cagr=round(cagr, 4), ann_vol=round(vol, 4), sharpe=round(sh, 3),
                max_dd=round(mdd, 4), total=round(total, 4), monthly=monthly)


def _alloc_matrix(log_entries: list[dict]) -> dict:
    seen: list = []
    for e in log_entries:
        for t in e["holdings"]:
            if t not in seen:
                seen.append(t)
    return {
        "tickers": seen,
        "dates":   [e["date"] for e in log_entries],
        "weights": [[round(e["holdings"].get(t, 0.0), 4) for t in seen]
                    for e in log_entries],
    }


def _load_prices(universe_dir: Path, min_pts: int = MIN_PTS) -> dict[str, pd.DataFrame]:
    prices = {}
    for f in sorted(universe_dir.glob("*.csv.gz")):
        ticker = f.name.replace(".csv.gz", "")
        try:
            df = pd.read_csv(f, index_col=0, parse_dates=True, compression="gzip")
            if "Close" not in df.columns or len(df) < min_pts:
                continue
            prices[ticker] = df[["Close"]].dropna()
        except Exception as e:
            log.debug("Skip %s: %s", f.name, e)
    return prices


def _load_fx(fx_dir: Path, ticker: str) -> pd.Series:
    path = fx_dir / f"{ticker.replace('/', '_')}.csv.gz"
    if not path.exists():
        log.warning("FX file not found: %s", path)
        return pd.Series(dtype=float)
    df = pd.read_csv(path, index_col=0, parse_dates=True, compression="gzip")
    return df["Close"].dropna()


def _apply_fx(prices: dict[str, pd.DataFrame], fx: pd.Series) -> dict[str, pd.DataFrame]:
    out = {}
    for tk, df in prices.items():
        rate = fx.reindex(df.index).ffill().bfill()
        out[tk] = (df["Close"] * rate).rename("Close").to_frame()
    return out


def _run_backtest(
    all_prices: dict[str, pd.DataFrame],
    valid_fn=None,          # callable(ticker, date_str) → bool
    top_n: int = 7,
    max_per_universe: dict[str, int] | None = None,  # {"SP500": 3, ...}
    tag: dict[str, str] | None = None,                # ticker → universe
) -> tuple[list[dict], list[dict]]:
    """Core monthly backtest. Returns (nav, alloc_log)."""
    tickers   = list(all_prices.keys())
    all_dates = sorted({d for df in all_prices.values()
                        for d in df.index if str(d)[:10] >= START})
    dates = pd.DatetimeIndex(all_dates)
    cw    = pd.concat({t: all_prices[t]["Close"].rename(t) for t in tickers},
                      axis=1).reindex(dates).ffill()
    arrs  = {t: cw[t].values for t in tickers if t in cw.columns}
    rebal = set(
        pd.Series(dates).groupby(pd.Series(dates).dt.to_period("M")).last().values
    )
    pos_map = {d: i for i, d in enumerate(dates)}

    shares: dict = {}
    cash         = CAPITAL
    nav:    list = []
    alloc_log: list = []
    pending: dict | None = None

    for date in dates:
        if date < pd.Timestamp(START):
            continue
        # Execute pending rebalance
        if pending is not None:
            all_t = set(shares) | set(pending)
            px = {t: float(cw.at[date, t])
                  for t in all_t if t in cw.columns and np.isfinite(cw.at[date, t])}
            pv = cash + sum(shares.get(t, 0) * px.get(t, 0) for t in shares)
            ns = {t: (pv * w) / px[t] for t, w in pending.items() if px.get(t, 0) > 0}
            tv = sum(abs(ns.get(t, 0) * px.get(t, 0) - shares.get(t, 0) * px.get(t, 0))
                     for t in set(shares) | set(ns))
            cash   = pv - sum(ns[t] * px[t] for t in ns) - tv * COST
            shares = ns
            pending = None

        hv = sum(shares[t] * float(cw.at[date, t])
                 for t in shares
                 if t in cw.columns and np.isfinite(cw.at[date, t]))
        nav.append({"date": date.strftime("%Y-%m-%d"), "value": round(cash + hv, 2)})

        if date not in rebal:
            continue

        pos      = pos_map[date]
        date_str = date.strftime("%Y-%m-%d")

        def _ok(t: str) -> bool:
            if valid_fn and not valid_fn(t, date_str):
                return False
            return True

        scores = {t: _composite_score(arrs[t], pos)
                  for t in tickers if t in arrs and _ok(t)}
        positive = {t: s for t, s in scores.items() if np.isfinite(s) and s > 0}

        if not positive:
            pending = {}
            alloc_log.append({"date": date_str, "holdings": {"CASH": 1.0}})
            continue

        ranked = sorted(positive, key=positive.__getitem__, reverse=True)

        if max_per_universe and tag:
            chosen: list = []
            counts: dict = {}
            for t in ranked:
                u   = tag.get(t, "")
                cap = max_per_universe.get(u, top_n)
                if counts.get(u, 0) < cap:
                    chosen.append(t)
                    counts[u] = counts.get(u, 0) + 1
                if len(chosen) >= top_n:
                    break
        else:
            chosen = ranked[:top_n]

        if not chosen:
            pending = {}
            alloc_log.append({"date": date_str, "holdings": {"CASH": 1.0}})
            continue

        w       = 1.0 / len(chosen)
        pending = {t: w for t in chosen}
        alloc_log.append({"date": date_str,
                          "holdings": {t: round(w, 6) for t in chosen}})

    return nav, alloc_log


def _bench_nav(series: pd.Series, start: str = START) -> list[dict]:
    s = series[series.index >= pd.Timestamp(start)]
    if s.empty:
        return []
    base = float(s.iloc[0])
    return [{"date": str(d)[:10], "value": round(float(v) / base * CAPITAL, 2)}
            for d, v in s.items()]


# ── Per-universe runners ───────────────────────────────────────────────
def run_omxs(data_root: Path) -> dict:
    stock_dir = data_root / "stock_prices"
    prices    = _load_prices(stock_dir / "omxs")
    fx        = _load_fx(stock_dir / "fx", "SEKUSD=X")
    prices_usd = _apply_fx(prices, fx)

    omx       = _load_fx(stock_dir / "gates", "^OMX")
    omx_usd   = (omx * fx.reindex(omx.index).ffill()).dropna()
    bench_s   = _bench_nav(omx_usd)

    strategies: dict = {}
    for top_n in (5, 7, 10):
        log.info("OMXS Top-%d …", top_n)
        nav, al = _run_backtest(prices_usd, top_n=top_n)
        key = f"omxs_sammansatt_top{top_n}"
        strategies[key] = {
            "label":          f"OMXS Sammansatt Top-{top_n}",
            "nav":            nav,
            "stats":          _calc_stats(nav),
            "alloc_log":      al,
            "allocation":     _alloc_matrix(al),
            "current_signal": {"date": al[-1]["date"],
                               "holdings": [{"ticker": t, "weight": w}
                                            for t, w in al[-1]["holdings"].items()]},
            "params":         {"top_n": top_n, "cost": COST},
            "benchmark":      {"label": "OMXS30", "series": bench_s},
        }
    return {"generated_at": pd.Timestamp.now().isoformat(),
            "strategies": strategies,
            "benchmark":  {"label": "OMXS30", "series": bench_s}}


def run_stoxx(data_root: Path) -> dict:
    stock_dir = data_root / "stock_prices"
    prices    = _load_prices(stock_dir / "stoxx")
    fx        = _load_fx(stock_dir / "fx", "EURUSD=X")
    prices_usd = _apply_fx(prices, fx)

    exsa_raw  = _load_fx(stock_dir / "gates", "EXSA.DE")
    bench_s   = _bench_nav((exsa_raw * fx.reindex(exsa_raw.index).ffill()).dropna())

    strategies: dict = {}
    for top_n in (5, 7, 10):
        log.info("STOXX Top-%d …", top_n)
        nav, al = _run_backtest(prices_usd, top_n=top_n)
        key = f"stoxx_sammansatt_top{top_n}"
        strategies[key] = {
            "label":          f"STOXX Sammansatt Top-{top_n}",
            "nav":            nav,
            "stats":          _calc_stats(nav),
            "alloc_log":      al,
            "allocation":     _alloc_matrix(al),
            "current_signal": {"date": al[-1]["date"],
                               "holdings": [{"ticker": t, "weight": w}
                                            for t, w in al[-1]["holdings"].items()]},
            "params":         {"top_n": top_n, "cost": COST},
            "benchmark":      {"label": "EXSA.DE (USD)", "series": bench_s},
        }
    return {"generated_at": pd.Timestamp.now().isoformat(),
            "strategies": strategies,
            "benchmark":  {"label": "EXSA.DE (USD)", "series": bench_s}}


def run_sp500(data_root: Path, backend_dir: Path) -> dict:
    stock_dir = data_root / "stock_prices"
    prices    = _load_prices(stock_dir / "sp500")

    pit = pd.read_csv(backend_dir.parent / "data" / "sp500_ticker_start_end.csv",
                      parse_dates=["start_date", "end_date"])
    pit["end_date"] = pit["end_date"].fillna(pd.Timestamp("2099-01-01"))

    def valid_sp500(ticker: str, date_str: str) -> bool:
        d = pd.Timestamp(date_str)
        return bool(((pit.start_date <= d) & (pit.end_date > d) &
                     (pit.ticker == ticker)).any())

    spy_raw   = _load_fx(stock_dir / "gates", "SPY")
    bench_s   = _bench_nav(spy_raw)

    strategies: dict = {}
    for top_n in (5, 7, 10):
        log.info("SP500 Top-%d …", top_n)
        nav, al = _run_backtest(prices, valid_fn=valid_sp500, top_n=top_n)
        key = f"sp500_sammansatt_top{top_n}"
        strategies[key] = {
            "label":          f"SP500 Sammansatt Top-{top_n}",
            "nav":            nav,
            "stats":          _calc_stats(nav),
            "alloc_log":      al,
            "allocation":     _alloc_matrix(al),
            "current_signal": {"date": al[-1]["date"],
                               "holdings": [{"ticker": t, "weight": w}
                                            for t, w in al[-1]["holdings"].items()]},
            "params":         {"top_n": top_n, "cost": COST},
            "benchmark":      {"label": "SPY", "series": bench_s},
        }
    return {"generated_at": pd.Timestamp.now().isoformat(),
            "strategies": strategies,
            "benchmark":  {"label": "SPY", "series": bench_s}}


def run_global(data_root: Path, backend_dir: Path) -> dict:
    stock_dir  = data_root / "stock_prices"
    fx_sek     = _load_fx(stock_dir / "fx", "SEKUSD=X")
    fx_eur     = _load_fx(stock_dir / "fx", "EURUSD=X")

    omxs_usd   = _apply_fx(_load_prices(stock_dir / "omxs"), fx_sek)
    stoxx_usd  = _apply_fx(_load_prices(stock_dir / "stoxx"), fx_eur)
    sp500_raw  = _load_prices(stock_dir / "sp500")

    all_prices: dict = {}
    tag:        dict = {}
    for tk, df in omxs_usd.items():  all_prices[f"OMXS:{tk}"]  = df; tag[f"OMXS:{tk}"]  = "OMXS"
    for tk, df in stoxx_usd.items(): all_prices[f"STOXX:{tk}"] = df; tag[f"STOXX:{tk}"] = "STOXX"
    for tk, df in sp500_raw.items(): all_prices[f"SP500:{tk}"] = df; tag[f"SP500:{tk}"] = "SP500"

    pit = pd.read_csv(backend_dir.parent / "data" / "sp500_ticker_start_end.csv",
                      parse_dates=["start_date", "end_date"])
    pit["end_date"] = pit["end_date"].fillna(pd.Timestamp("2099-01-01"))

    def valid_global(ticker: str, date_str: str) -> bool:
        if not ticker.startswith("SP500:"):
            return True
        raw = ticker.replace("SP500:", "")
        d   = pd.Timestamp(date_str)
        return bool(((pit.start_date <= d) & (pit.end_date > d) &
                     (pit.ticker == raw)).any())

    spy_raw  = _load_fx(stock_dir / "gates", "SPY")
    bench_s  = _bench_nav(spy_raw)

    configs = [(7, {"OMXS": 3, "STOXX": 3, "SP500": 3}),
               (10, {"OMXS": 4, "STOXX": 4, "SP500": 4}),
               (15, {"OMXS": 5, "STOXX": 5, "SP500": 5})]

    strategies: dict = {}
    for top_n, max_u in configs:
        log.info("Global Top-%d (max %d/univ) …", top_n, max_u["SP500"])
        nav, al = _run_backtest(all_prices, valid_fn=valid_global,
                                top_n=top_n, max_per_universe=max_u, tag=tag)
        key = f"global_top{top_n}"
        strategies[key] = {
            "label":          f"Global Top-{top_n} (max {max_u['SP500']}/univ)",
            "nav":            nav,
            "stats":          _calc_stats(nav),
            "alloc_log":      al,
            "allocation":     _alloc_matrix(al),
            "current_signal": {
                "date": al[-1]["date"],
                "holdings": [{"ticker": t, "weight": w, "universe": tag.get(t, "")}
                             for t, w in al[-1]["holdings"].items()],
            },
            "params":  {"top_n": top_n, "max_per_universe": max_u, "cost": COST},
            "benchmark": {"label": "SPY", "series": bench_s},
        }

    return {"generated_at": pd.Timestamp.now().isoformat(),
            "strategies": strategies,
            "benchmark":  {"label": "SPY", "series": bench_s},
            "ticker_tag": tag}


# ── Main entry point ──────────────────────────────────────────────────
def run_all(data_root: Path, backend_dir: Path) -> dict[str, str]:
    """Run all four backtests and save results. Returns status per universe."""
    results_dir = data_root / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    status: dict = {}

    for name, runner in [
        ("omxs",   lambda: run_omxs(data_root)),
        ("stoxx",  lambda: run_stoxx(data_root)),
        ("sp500",  lambda: run_sp500(data_root, backend_dir)),
        ("global", lambda: run_global(data_root, backend_dir)),
    ]:
        t0 = time.time()
        try:
            out  = runner()
            path = results_dir / f"{name}_sammansatt_results.json"
            path.write_text(json.dumps(out, separators=(",", ":")))
            elapsed = time.time() - t0
            n_strats = len(out.get("strategies", {}))
            log.info("%s: wrote %s (%d strategies, %.0fs)", name, path.name, n_strats, elapsed)
            status[name] = "ok"
        except Exception as e:
            log.error("%s backtest failed: %s", name, e, exc_info=True)
            status[name] = f"error: {e}"

    return status


def results_are_stale(data_root: Path, max_age_days: int = 35) -> bool:
    """True if any sammansatt results JSON is older than max_age_days or missing."""
    import time as _time
    now = _time.time()
    for name in ("omxs", "stoxx", "sp500", "global"):
        path = data_root / "results" / f"{name}_sammansatt_results.json"
        if not path.exists():
            return True
        age_days = (now - path.stat().st_mtime) / 86400
        if age_days > max_age_days:
            return True
    return False
