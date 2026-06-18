#!/usr/bin/env python3
"""
One-time migration: import existing data into SQLite.

Sources:
  1. dashboard/backend/_price_cache.pkl  →  etf_prices table
  2. ppm_all_nav.csv                     →  ppm_nav table

Run from repo root:
  python3 scripts/migrate_to_db.py

After migration, verify with:
  python3 scripts/migrate_to_db.py --verify
"""
import argparse
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent / "dashboard" / "backend"))

import pandas as pd
from db import init_db, upsert_etf_prices, upsert_ppm_nav, get_conn, DB_PATH

REPO_ROOT  = Path(__file__).parent.parent
CACHE_PATH = REPO_ROOT / "dashboard" / "backend" / "_price_cache.pkl"
PPM_CSV    = REPO_ROOT / "ppm_all_nav.csv"


def migrate_etf(db_path: Path) -> int:
    if not CACHE_PATH.exists():
        print(f"[ETF] Cache not found at {CACHE_PATH} — skipping")
        return 0

    print(f"[ETF] Loading {CACHE_PATH} …")
    prices = pd.read_pickle(CACHE_PATH)

    close = prices.get("close", pd.DataFrame())
    high  = prices.get("high",  pd.DataFrame())
    low   = prices.get("low",   pd.DataFrame())

    if close.empty:
        print("[ETF] No close prices in cache — skipping")
        return 0

    print(f"[ETF] {close.shape[1]} tickers × {len(close)} days → building rows …")
    rows = []
    for ticker in close.columns:
        for dt, cl in close[ticker].items():
            if pd.isna(cl):
                continue
            hi = float(high.loc[dt, ticker]) if ticker in high.columns and not pd.isna(high.loc[dt, ticker]) else None
            lo = float(low.loc[dt, ticker])  if ticker in low.columns  and not pd.isna(low.loc[dt, ticker])  else None
            rows.append((ticker, dt.strftime("%Y-%m-%d"), float(cl), hi, lo))

    print(f"[ETF] Upserting {len(rows):,} rows …")
    # Batch to avoid huge transactions
    BATCH = 50_000
    for i in range(0, len(rows), BATCH):
        upsert_etf_prices(rows[i : i + BATCH], db_path)
        print(f"  {min(i + BATCH, len(rows)):,} / {len(rows):,}", end="\r")
    print()
    print(f"[ETF] Done — {len(rows):,} rows inserted")
    return len(rows)


def migrate_ppm(db_path: Path) -> int:
    if not PPM_CSV.exists():
        print(f"[PPM] CSV not found at {PPM_CSV} — skipping")
        return 0

    print(f"[PPM] Loading {PPM_CSV} …")
    df = pd.read_csv(PPM_CSV, dtype={"ppm_number": str})
    df = df[df["date"] > "2000-01-01"]
    df = df.dropna(subset=["nav_sek"])

    rows = [
        (str(r["ppm_number"]), str(r["date"])[:10], float(r["nav_sek"]))
        for _, r in df.iterrows()
    ]
    print(f"[PPM] Upserting {len(rows):,} rows …")
    BATCH = 50_000
    for i in range(0, len(rows), BATCH):
        upsert_ppm_nav(rows[i : i + BATCH], db_path)
        print(f"  {min(i + BATCH, len(rows)):,} / {len(rows):,}", end="\r")
    print()
    print(f"[PPM] Done — {len(rows):,} rows inserted")
    return len(rows)


def verify(db_path: Path):
    with get_conn(db_path) as conn:
        etf_count  = conn.execute("SELECT COUNT(*) FROM etf_prices").fetchone()[0]
        etf_ticks  = conn.execute("SELECT COUNT(DISTINCT ticker) FROM etf_prices").fetchone()[0]
        etf_range  = conn.execute("SELECT MIN(date), MAX(date) FROM etf_prices").fetchone()
        ppm_count  = conn.execute("SELECT COUNT(*) FROM ppm_nav").fetchone()[0]
        ppm_funds  = conn.execute("SELECT COUNT(DISTINCT ppm_number) FROM ppm_nav").fetchone()[0]
        ppm_range  = conn.execute("SELECT MIN(date), MAX(date) FROM ppm_nav").fetchone()

    print("\n── Verification ───────────────────────────────")
    print(f"  ETF prices : {etf_count:>8,} rows  |  {etf_ticks} tickers  |  {etf_range[0]} → {etf_range[1]}")
    print(f"  PPM NAV    : {ppm_count:>8,} rows  |  {ppm_funds} funds    |  {ppm_range[0]} → {ppm_range[1]}")
    print(f"  DB path    : {db_path}")
    print("───────────────────────────────────────────────\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", action="store_true", help="Only verify, don't migrate")
    ap.add_argument("--db", default=str(DB_PATH), help="SQLite path override")
    args = ap.parse_args()

    db = Path(args.db)
    print(f"DB path: {db}\n")
    init_db(db)

    if args.verify:
        verify(db)
    else:
        migrate_etf(db)
        migrate_ppm(db)
        verify(db)
        print("Migration complete. Run the engine to regenerate data.json:")
        print("  cd dashboard/backend && python3 engine.py")
