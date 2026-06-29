"""
PPM NAV fetcher — Pensionsmyndigheten fondtorg.

Fetches daily NAV snapshot from:
  https://static.pensionsmyndigheten.se/fond/kurser.txt

The file is a fixed-width Latin-1 text with all PPM funds for the latest trading day.
One HTTP GET per day fetches all funds — no per-fund API calls needed.

For historical backfill (first-time setup or gap-fill):
  1. Download quarterly CSV from https://www.pensionsmyndigheten.se/service/fondtorget
     (click "Ladda ner fondandelskurser" → select funds & date range → export CSV)
  2. POST to /api/import-ppm or call import_csv() directly.
"""
import logging
import re
from datetime import date
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

KURSER_URL = "https://static.pensionsmyndigheten.se/fond/kurser.txt"
HEADERS    = {"User-Agent": "etf-dashboard/1.0"}


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
    Fetch today's NAV snapshot and upsert new rows into ppm_nav.
    Skips if DB already has today's data.
    Returns number of new rows inserted.
    """
    init_db(db_path)
    numbers = set(ppm_numbers or list(PPM_UNIVERSE.keys()))
    today   = date.today().isoformat()

    last = last_ppm_date(db_path)
    if last and last >= today:
        log.info("PPM NAV already up to date (%s)", last)
        return 0

    log.info("Fetching PPM NAV from kurser.txt…")
    try:
        with httpx.Client() as client:
            all_navs = fetch_kurser_txt(client)
    except Exception as exc:
        log.error("PPM fetch failed: %s", exc)
        return 0

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

    log.info("PPM fetch complete — %d new rows", len(rows))
    return len(rows)


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
