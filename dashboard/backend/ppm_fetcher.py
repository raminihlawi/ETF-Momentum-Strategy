"""
PPM NAV fetcher — Pensionsmyndigheten fondtorg.

Primary daily source:
  https://static.pensionsmyndigheten.se/fond/kurser.txt
  Fixed-width Latin-1 snapshot with all PPM funds for the latest trading day.
  One GET per day fetches all 14 funds.

Historical backfill / gap-fill:
  fetch_from_supabase() pulls full history from our Supabase DB (always up to date).
  fetch_incremental() calls this automatically when the local DB is more than 5 days stale.

Manual CSV import (last resort):
  Download from https://www.pensionsmyndigheten.se/service/fondtorget → import_csv().
"""
import logging
import re
import urllib.request
import urllib.parse
import json
from datetime import date, timedelta
from pathlib import Path

import httpx

from db import upsert_ppm_nav, last_ppm_date, init_db

log = logging.getLogger(__name__)

PPM_UNIVERSE = {
    "581371": "AP7 Aktiefond",
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
    "545541": "AP7 Räntefond",
}

KURSER_URL     = "https://static.pensionsmyndigheten.se/fond/kurser.txt"
HEADERS        = {"User-Agent": "etf-dashboard/1.0"}

SUPABASE_URL   = "https://iapzoattwnnmidkrbjcov.supabase.co/rest/v1"
SUPABASE_KEY   = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImlhcHpvYXR0d25taWRrcmJqY292Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzE3NTM0NDgsImV4cCI6MjA4NzMyOTQ0OH0.UMYMm-qTMt_a-8Arnf9EwE0xPxwYZSCco2l0E0VX2yI"
SUPABASE_HDRS  = {
    "apikey":        SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Accept":        "application/json",
}
# Trigger Supabase backfill when local DB is this many days behind
BACKFILL_DAYS  = 5


def fetch_kurser_txt(client: httpx.Client) -> dict[str, tuple[str, float]]:
    """
    Fetch today's NAV snapshot from Pensionsmyndigheten.
    Returns {ppm_number: (date_str, nav_sek)} for every fund in the file.
    Uses Köpkurs (buy price) as NAV.
    """
    resp = client.get(KURSER_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    text = resp.content.decode("latin-1")

    result: dict[str, tuple[str, float]] = {}
    for line in text.splitlines():
        if not line or not line[0].isdigit():
            continue
        fondnr = line[:6].strip()
        if not fondnr:
            continue
        # Extract two prices and date from end of line (robust vs fixed-width)
        m = re.search(r'([0-9,]+)\s+([0-9,]+)\s+(\d{4}-\d{2}-\d{2})\s*$', line)
        if not m:
            continue
        try:
            kopkurs = float(m.group(1).replace(',', '.'))
            datum   = m.group(3)
            result[fondnr] = (datum, kopkurs)
        except ValueError:
            continue

    return result


def fetch_incremental(
    ppm_numbers: list[str] | None = None,
    db_path: Path | None = None,
) -> int:
    """
    Fetch latest PPM NAV and upsert into ppm_nav.

    Flow:
      1. If local DB is more than BACKFILL_DAYS behind → Supabase backfill (fills all gaps).
      2. Then fetch today's snapshot from kurser.txt (idempotent).
    Returns total new rows inserted.
    """
    init_db(db_path)
    numbers = set(ppm_numbers or list(PPM_UNIVERSE.keys()))
    today   = date.today().isoformat()

    last = last_ppm_date(db_path)
    if last and last >= today:
        log.info("PPM NAV already up to date (%s)", last)
        return 0

    total = 0

    # Gap recovery: if more than BACKFILL_DAYS behind, pull from Supabase first
    if last:
        days_behind = (date.today() - date.fromisoformat(last)).days
    else:
        days_behind = 9999

    if days_behind > BACKFILL_DAYS:
        from_date = (
            (date.fromisoformat(last) + timedelta(days=1)).isoformat()
            if last else "2010-01-01"
        )
        log.info("PPM: DB is %d days behind (%s) — running Supabase backfill from %s",
                 days_behind, last or "empty", from_date)
        try:
            total += fetch_from_supabase(from_date=from_date, db_path=db_path)
        except Exception as exc:
            log.warning("Supabase backfill failed (%s), continuing with kurser.txt", exc)

    # Daily snapshot from kurser.txt
    last2 = last_ppm_date(db_path)
    if last2 and last2 >= today:
        log.info("PPM NAV up to date after backfill (%s)", last2)
        return total

    log.info("Fetching PPM NAV from kurser.txt…")
    try:
        with httpx.Client() as client:
            all_navs = fetch_kurser_txt(client)
    except Exception as exc:
        log.error("PPM kurser.txt fetch failed: %s", exc)
        return total

    log.info("kurser.txt: %d funds in file", len(all_navs))

    rows: list[tuple[str, str, float]] = []
    for ppm_number in numbers:
        if ppm_number in all_navs:
            datum, nav = all_navs[ppm_number]
            rows.append((ppm_number, datum, nav))
            log.info("PPM %s (%s): %s = %.4f SEK",
                     ppm_number, PPM_UNIVERSE.get(ppm_number, "?"), datum, nav)
        else:
            log.warning("PPM %s not found in kurser.txt", ppm_number)

    if rows:
        upsert_ppm_nav(rows, db_path)
        total += len(rows)

    log.info("PPM fetch complete — %d new rows total", total)
    return total


def _supabase_get(path: str, params: dict) -> list:
    url = f"{SUPABASE_URL}/{path}?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=SUPABASE_HDRS)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def fetch_from_supabase(
    from_date: str = "2010-01-01",
    db_path: Path | None = None,
) -> int:
    """
    Pull full NAV history from Supabase for all PPM_UNIVERSE funds
    and upsert into ppm_nav. Used for initial fill and gap recovery.
    Returns total rows upserted.
    """
    log.info("Supabase backfill: fetching fund UUIDs…")
    try:
        funds_raw = _supabase_get("funds", {
            "select": "id,ppm_number",
            "ppm_number": f"in.({','.join(PPM_UNIVERSE.keys())})",
        })
    except Exception as exc:
        log.error("Supabase: could not fetch fund list: %s", exc)
        return 0

    log.info("Supabase: found %d funds", len(funds_raw))
    total = 0

    for fund in funds_raw:
        fid = fund["id"]
        ppm = fund["ppm_number"]
        rows_out: list[tuple[str, str, float]] = []
        offset = 0
        page = 1000
        while True:
            try:
                batch = _supabase_get("nav_history", {
                    "select":   "date,nav_sek",
                    "fund_id":  f"eq.{fid}",
                    "date":     f"gte.{from_date}",
                    "order":    "date.asc",
                    "limit":    page,
                    "offset":   offset,
                })
            except Exception as exc:
                log.error("Supabase: error fetching %s: %s", ppm, exc)
                break
            for r in batch:
                try:
                    rows_out.append((ppm, r["date"][:10], float(r["nav_sek"])))
                except (KeyError, ValueError, TypeError):
                    pass
            if len(batch) < page:
                break
            offset += page

        if rows_out:
            upsert_ppm_nav(rows_out, db_path)
            total += len(rows_out)
            log.info("Supabase: %s (%s) → %d rows", ppm,
                     PPM_UNIVERSE.get(ppm, "?"), len(rows_out))
        else:
            log.warning("Supabase: no rows for %s", ppm)

    log.info("Supabase backfill complete — %d total rows", total)
    return total


def probe_api() -> bool:
    """
    Quick connectivity check — fetches kurser.txt and verifies AP7 Aktiefond is present.
    Run manually:
      python3 -c "from ppm_fetcher import probe_api; probe_api()"
    """
    try:
        with httpx.Client() as client:
            navs = fetch_kurser_txt(client)
        if "581371" in navs:
            datum, nav = navs["581371"]
            log.info("Probe OK — AP7 Aktiefond (581371): %s = %.4f SEK", datum, nav)
            return True
        log.error("Probe: kurser.txt fetched (%d funds) but AP7 Aktiefond (581371) not found",
                  len(navs))
        return False
    except Exception as exc:
        log.error("Probe exception: %s", exc)
        return False


# ── CSV / Excel import (historical backfill) ───────────────────────
def import_csv(file_path: Path, db_path: Path | None = None) -> int:
    """
    Import ppm_all_nav.csv (columns: ppm_number, name, date, nav_sek)
    into ppm_nav. Returns number of rows upserted.
    """
    import pandas as pd
    df = pd.read_csv(file_path, dtype={"ppm_number": str})
    df = df[df["date"] > "2000-01-01"].dropna(subset=["nav_sek"])
    rows = [
        (str(r["ppm_number"]), str(r["date"])[:10], float(r["nav_sek"]))
        for _, r in df.iterrows()
    ]
    if rows:
        upsert_ppm_nav(rows, db_path)
    log.info("CSV import: %d rows from %s", len(rows), file_path.name)
    return len(rows)


def import_excel(file_path: Path, db_path: Path | None = None) -> int:
    """
    Import Pensionsmyndigheten quarterly Excel export
    (columns: Fondnummer / Fondnamn / Datum / Andelsvärde or similar).
    Returns number of rows upserted.
    """
    import pandas as pd

    df = pd.read_excel(file_path, dtype=str)
    df.columns = [c.strip() for c in df.columns]

    col_map = {
        "Fondnummer":  "ppm_number",
        "PPM-nummer":  "ppm_number",
        "Fund number": "ppm_number",
        "Datum":       "date",
        "Date":        "date",
        "Andelsvärde": "nav_sek",
        "Andelsvarde": "nav_sek",
        "NAV":         "nav_sek",
        "nav_sek":     "nav_sek",
    }
    df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})

    if not {"ppm_number", "date", "nav_sek"}.issubset(df.columns):
        raise ValueError(
            f"Could not find required columns in Excel. Found: {list(df.columns)}"
        )

    df["nav_sek"] = pd.to_numeric(df["nav_sek"].str.replace(",", "."), errors="coerce")
    df = df.dropna(subset=["nav_sek"])
    df = df[df["date"] > "2000-01-01"]

    rows = [
        (str(r["ppm_number"]), str(r["date"])[:10], float(r["nav_sek"]))
        for _, r in df.iterrows()
    ]
    if rows:
        upsert_ppm_nav(rows, db_path)
    log.info("Excel import: %d rows from %s", len(rows), file_path.name)
    return len(rows)
