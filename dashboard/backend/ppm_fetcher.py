"""
PPM NAV fetcher — Pensionsmyndigheten fondtorg.

NOTE: The Pensionsmyndigheten REST API at /service/fondtorget/fonder/{id}/andelsvarden
requires authentication (redirects to "åtkomst nekad" for unauthenticated requests).
fetch_incremental() will log a warning and return 0 until authentication is resolved.

Practical workflow until API auth is configured:
  1. Download quarterly CSV from https://www.pensionsmyndigheten.se/service/fondtorget
     (click "Ladda ner fondandelskurser" → select funds & date range → export CSV)
  2. POST to /api/import-ppm (multipart/form-data, field "file") or call import_csv() directly.

API auth options to investigate:
  - Pensionsmyndigheten Öppna Data portal (may require API key registration)
  - CSRF token + session cookie from the website
  - OAuth2 via Swedish BankID / API gateway

import_csv() and import_excel() are always available as the reliable fallback.
"""
import logging
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

BASE_URL = "https://www.pensionsmyndigheten.se/service/fondtorget/fonder"
HEADERS  = {
    "Accept":     "application/json",
    "User-Agent": "etf-dashboard/1.0",
}


def _parse_response(data: dict | list) -> list[tuple[str, float]]:
    """
    Parse API response → list of (date_str, nav_sek).
    Handles the most common response shapes from Pensionsmyndigheten.
    """
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        # Try common key names
        items = (
            data.get("andelsvarden")
            or data.get("values")
            or data.get("data")
            or []
        )
    else:
        return []

    result = []
    for item in items:
        # Key names vary — try both Swedish and English
        d = item.get("datum") or item.get("date") or item.get("Datum")
        v = item.get("andelsvarde") or item.get("navSek") or item.get("nav") or item.get("value")
        if d and v is not None:
            try:
                result.append((str(d)[:10], float(v)))
            except (ValueError, TypeError):
                pass
    return result


def fetch_fund(
    ppm_number: str,
    from_date: str,
    to_date: str,
    client: httpx.Client,
) -> list[tuple[str, str, float]]:
    """Fetch NAV rows for one fund → list of (ppm_number, date, nav_sek)."""
    url = f"{BASE_URL}/{ppm_number}/andelsvarden"
    params = {"from": from_date, "tom": to_date}
    try:
        resp = client.get(url, params=params, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        rows = _parse_response(resp.json())
        return [(ppm_number, d, v) for d, v in rows]
    except httpx.HTTPStatusError as exc:
        log.error("PPM %s: HTTP %s — %s", ppm_number, exc.response.status_code, url)
    except Exception as exc:
        log.error("PPM %s: %s", ppm_number, exc)
    return []


def fetch_incremental(
    ppm_numbers: list[str] | None = None,
    db_path: Path | None = None,
) -> int:
    """
    Fetch only missing days for each PPM fund and upsert into ppm_nav.
    Returns total new rows inserted.
    """
    init_db(db_path)
    numbers = ppm_numbers or list(PPM_UNIVERSE.keys())
    today   = date.today().isoformat()

    last = last_ppm_date(db_path)
    from_date = (
        (date.fromisoformat(last) + timedelta(days=1)).isoformat()
        if last
        else "2010-01-01"
    )

    if from_date > today:
        log.info("PPM NAV already up to date (%s)", last)
        return 0

    log.info("Fetching PPM NAV from %s to %s (%d funds)…", from_date, today, len(numbers))

    total = 0
    with httpx.Client() as client:
        for ppm_number in numbers:
            rows = fetch_fund(ppm_number, from_date, today, client)
            if rows:
                upsert_ppm_nav(rows, db_path)
                total += len(rows)
                log.info(
                    "PPM %s (%s): +%d rows",
                    ppm_number,
                    PPM_UNIVERSE.get(ppm_number, "?"),
                    len(rows),
                )
            else:
                log.debug("PPM %s: no new rows", ppm_number)

    log.info("PPM fetch complete — %d new rows total", total)
    return total


def probe_api() -> bool:
    """
    Quick connectivity check — fetches 3 days for AP7 Aktiefond.
    Run this manually to verify the API endpoint is still valid:
      python3 -c "from ppm_fetcher import probe_api; probe_api()"
    """
    url = f"{BASE_URL}/581371/andelsvarden"
    params = {"from": "2024-01-01", "tom": "2024-01-05"}
    try:
        with httpx.Client() as client:
            resp = client.get(url, params=params, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            log.error("Probe failed — HTTP %s\nURL: %s", resp.status_code, resp.url)
            log.error("Response: %s", resp.text[:500])
            return False
        rows = _parse_response(resp.json())
        if not rows:
            log.error("Probe: connected but could not parse response:\n%s", resp.text[:500])
            return False
        log.info("Probe OK — got %d rows, first: %s", len(rows), rows[0])
        return True
    except Exception as exc:
        log.error("Probe exception: %s", exc)
        return False


# ── CSV / Excel import (reliable fallback) ─────────────────────────
def import_csv(file_path: Path, db_path: Path | None = None) -> int:
    """
    Import ppm_all_nav.csv (or any CSV with columns ppm_number,name,date,nav_sek)
    into the ppm_nav table. Returns number of new rows upserted.
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
    Returns number of new rows upserted.
    """
    import pandas as pd

    df = pd.read_excel(file_path, dtype=str)
    df.columns = [c.strip() for c in df.columns]

    # Map Swedish column names to our schema
    col_map = {
        # ppm_number
        "Fondnummer":   "ppm_number",
        "PPM-nummer":   "ppm_number",
        "Fund number":  "ppm_number",
        # date
        "Datum":        "date",
        "Date":         "date",
        # nav_sek
        "Andelsvärde":  "nav_sek",
        "Andelsvarde":  "nav_sek",
        "NAV":          "nav_sek",
        "nav_sek":      "nav_sek",
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
