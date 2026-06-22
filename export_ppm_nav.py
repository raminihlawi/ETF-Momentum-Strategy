#!/usr/bin/env python3
"""
Export PPM fund NAV data from Supabase → ppm_nav.csv
Run locally: python3 export_ppm_nav.py
"""
import urllib.request
import urllib.parse
import json
import csv
from pathlib import Path

SUPABASE_URL = "https://iapzoattwnnmidkrbjcov.supabase.co/rest/v1"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImlhcHpvYXR0d25taWRrcmJqY292Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzE3NTM0NDgsImV4cCI6MjA4NzMyOTQ0OH0.UMYMm-qTMt_a-8Arnf9EwE0xPxwYZSCco2l0E0VX2yI"

HEADERS = {
    "apikey":        SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Accept":        "application/json",
}

# Target PPM numbers (excl JPMorgan 124438 — too short)
TARGET_PPM = {
    "283408": "Swedbank Robur Technology A",
    "644005": "Handelsbanken Hälsovård Tema A1",
    "517748": "BlackRock World Energy A2",
    "481911": "BlackRock World Mining A2",
    "479550": "Seligson Global Top 25 Brands A",
    "768556": "BlackRock US Basic Value A2",
    "916354": "SEB Nordamerikafond Små och Medelstora A",
    "456475": "Länsförsäkringar USA Aktiv A",
    "163923": "Öhman Global Growth A",
    "182759": "Lannebo Europa Småbolag A",
    "538462": "AMF Aktiefond Europa",
    "162099": "Storebrand Global Multifactor A",
    "581371": "AP7 Aktiefond",   # benchmark
}

OUT_FILE = Path(__file__).parent / "ppm_nav.csv"

def fetch(path, params=None):
    url = f"{SUPABASE_URL}/{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())

def fetch_all(table, select, filters, page_size=1000):
    rows = []
    offset = 0
    while True:
        params = {"select": select, "limit": page_size, "offset": offset}
        params.update(filters)
        hdrs = {**HEADERS, "Range-Unit": "items", "Prefer": "count=none"}
        url = f"{SUPABASE_URL}/{table}?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers=hdrs)
        with urllib.request.urlopen(req, timeout=30) as r:
            batch = json.loads(r.read())
        rows.extend(batch)
        print(f"  {table}: fetched {len(rows)} rows...", end="\r")
        if len(batch) < page_size:
            break
        offset += page_size
    print()
    return rows

# ── Step 1: Get fund UUIDs for our target PPM numbers ────────────────
print("Fetching fund metadata...")
ppm_list = ",".join(f"eq.{p}" for p in TARGET_PPM)
funds_raw = fetch("funds", {
    "select": "id,name,ppm_number",
    "ppm_number": f"in.({','.join(TARGET_PPM.keys())})",
})
fund_map = {f["id"]: f for f in funds_raw}
print(f"Found {len(fund_map)} funds:")
for f in funds_raw:
    print(f"  [{f['ppm_number']}] {f['name']}")

# ── Step 2: Fetch NAV history per fund ───────────────────────────────
print(f"\nFetching NAV history...")
all_rows = []
for fund in funds_raw:
    fid   = fund["id"]
    ppm   = fund["ppm_number"]
    name  = fund["name"]
    print(f"  Fetching {name} ({ppm})...")
    rows = fetch_all(
        "nav_history",
        select="date,nav_sek",
        filters={
            "fund_id": f"eq.{fid}",
            "date":    "gt.2000-01-01",   # skip epoch rows
            "order":   "date.asc",
        },
    )
    for r in rows:
        all_rows.append({
            "ppm_number": ppm,
            "name":       name,
            "date":       r["date"],
            "nav_sek":    r["nav_sek"],
        })

# ── Step 3: Write CSV ─────────────────────────────────────────────────
all_rows.sort(key=lambda r: (r["date"], r["ppm_number"]))
with open(OUT_FILE, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=["ppm_number","name","date","nav_sek"])
    writer.writeheader()
    writer.writerows(all_rows)

print(f"\nSparade {len(all_rows):,} rader → {OUT_FILE}")
print("\nTäckning per fond:")
from collections import defaultdict
coverage = defaultdict(list)
for r in all_rows:
    coverage[r["ppm_number"]].append(r["date"])
for ppm, dates in sorted(coverage.items()):
    name = next(f["name"] for f in funds_raw if f["ppm_number"] == ppm)
    print(f"  [{ppm}] {name[:45]:<45} {dates[0]} → {dates[-1]}  ({len(dates)} dagar)")
