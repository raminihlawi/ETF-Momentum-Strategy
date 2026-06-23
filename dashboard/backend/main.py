"""
ETF Dashboard — FastAPI server
Serves frontend, exposes /api/config (GET/POST), /api/status.
Starts APScheduler for daily ETF + PPM data refresh.
"""
import json
import logging
import os
import shutil
import subprocess
import sys
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends, Header, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

log = logging.getLogger(__name__)

# ── Paths ──────────────────────────────────────────────────────────
BASE_DIR  = Path(__file__).parent
_DATA_DIR = Path(os.getenv("DATA_DIR", str(BASE_DIR.parent.parent)))
_DATA_DIR.mkdir(parents=True, exist_ok=True)

CONFIG_PATH      = _DATA_DIR / "config.json"
SCREENING_CONFIG = _DATA_DIR / "screening_config.json"
DATA_PATH        = _DATA_DIR / "data.json"
DB_PATH          = _DATA_DIR / "dashboard.db"
FRONTEND         = BASE_DIR.parent / "frontend"
ENGINE           = BASE_DIR / "engine.py"

# Seed config files from bundled defaults if not yet present in DATA_DIR
for _name in ("config.json", "screening_config.json"):
    _dst = _DATA_DIR / _name
    _src = BASE_DIR / _name
    if not _dst.exists() and _src.exists():
        shutil.copy(_src, _dst)
        log.info("Seeded %s → %s", _name, _dst)

# DATA_PATH for the static frontend (also expose via /static/)
STATIC_DATA_PATH = FRONTEND / "static" / "data.json"

SECRET = os.getenv("DASHBOARD_SECRET", "")
_engine_running = threading.Event()


# ── Engine runner ──────────────────────────────────────────────────
def _run_engine_bg():
    if _engine_running.is_set():
        return
    _engine_running.set()
    try:
        subprocess.run(
            [sys.executable, str(ENGINE)],
            cwd=str(BASE_DIR),
            env={**os.environ, "DATA_DIR": str(_DATA_DIR)},
            capture_output=False,
            timeout=300,
        )
        # Keep data.json in both locations so the static server and the API both work
        if DATA_PATH.exists() and DATA_PATH != STATIC_DATA_PATH:
            STATIC_DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(DATA_PATH, STATIC_DATA_PATH)
    finally:
        _engine_running.clear()


# ── Lifespan (startup / shutdown) ─────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize DB schema
    try:
        from db import init_db
        init_db(DB_PATH)
        log.info("SQLite DB ready at %s", DB_PATH)
    except Exception as exc:
        log.error("DB init failed: %s", exc)

    # Start scheduler
    try:
        import scheduler as sched
        sched.start(CONFIG_PATH, DB_PATH, _run_engine_bg)
    except Exception as exc:
        log.error("Scheduler start failed: %s", exc)

    yield

    # Shutdown
    try:
        import scheduler as sched
        sched.stop()
    except Exception:
        pass


# ── App ────────────────────────────────────────────────────────────
app = FastAPI(title="ETF Dashboard", docs_url=None, redoc_url=None, lifespan=lifespan)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


# ── Auth ───────────────────────────────────────────────────────────
def require_auth(authorization: str = Header(default="")):
    if SECRET and authorization != f"Bearer {SECRET}":
        raise HTTPException(status_code=401, detail="Unauthorized")


# ── API ────────────────────────────────────────────────────────────
@app.get("/api/config")
def get_config():
    if not CONFIG_PATH.exists():
        raise HTTPException(404, "config.json not found")
    return JSONResponse(json.loads(CONFIG_PATH.read_text()))


@app.post("/api/config")
def update_config(payload: dict, bg: BackgroundTasks, _=Depends(require_auth)):
    required = ("factor_sleeve", "sector_sleeve", "regime_baseline", "cash_proxy")
    for key in required:
        if key not in payload:
            raise HTTPException(400, f"Missing top-level key: {key}")
    if not isinstance(payload["factor_sleeve"], dict):
        raise HTTPException(400, "factor_sleeve must be an object")
    if not isinstance(payload["sector_sleeve"], dict):
        raise HTTPException(400, "sector_sleeve must be an object")
    for sleeve in ("factor_sleeve", "sector_sleeve"):
        for label, info in payload[sleeve].items():
            if not isinstance(info.get("ticker", ""), str) or not info.get("ticker"):
                raise HTTPException(400, f"{sleeve}.{label}.ticker must be non-empty string")
    CONFIG_PATH.write_text(json.dumps(payload, indent=2))
    bg.add_task(_run_engine_bg)
    return {"status": "saved", "message": "Config saved. Recalculating in background."}


@app.get("/api/status")
def get_status():
    ts = None
    if DATA_PATH.exists():
        try:
            ts = json.loads(DATA_PATH.read_text()).get("generated_at")
        except Exception:
            pass
    import scheduler as sched
    next_jobs = {}
    if sched._scheduler and sched._scheduler.running:
        for job in sched._scheduler.get_jobs():
            nf = job.next_run_time
            next_jobs[job.id] = nf.isoformat() if nf else None
    return {
        "engine_running":   _engine_running.is_set(),
        "data_generated_at": ts,
        "next_jobs":        next_jobs,
        "db_path":          str(DB_PATH),
    }


@app.post("/api/recalculate")
def recalculate(bg: BackgroundTasks, _=Depends(require_auth)):
    bg.add_task(_run_engine_bg)
    return {"status": "started"}


@app.post("/api/refresh-data")
def refresh_data(bg: BackgroundTasks, _=Depends(require_auth)):
    """Trigger a full data fetch (ETF + PPM) then recalculate."""
    def _full_refresh():
        import json as _json
        from etf_fetcher import fetch_incremental, get_all_tickers
        from ppm_fetcher import fetch_incremental as ppm_fetch
        try:
            cfg = _json.loads(CONFIG_PATH.read_text())
            screening_cfg = (
                _json.loads(SCREENING_CONFIG.read_text()) if SCREENING_CONFIG.exists() else {}
            )
            tickers = get_all_tickers(cfg, screening_cfg)
            n_etf = fetch_incremental(tickers, DB_PATH)
            log.info("Manual refresh: %d ETF rows", n_etf)
        except Exception as exc:
            log.error("ETF refresh failed: %s", exc)
        try:
            n_ppm = ppm_fetch(db_path=DB_PATH)
            log.info("Manual refresh: %d PPM rows", n_ppm)
        except Exception as exc:
            log.error("PPM refresh failed: %s", exc)
        _run_engine_bg()

    bg.add_task(_full_refresh)
    return {"status": "started", "message": "Full data refresh queued."}


# ── PPM data import ────────────────────────────────────────────────
@app.post("/api/import-ppm")
async def import_ppm(
    bg: BackgroundTasks,
    file: UploadFile = File(...),
    _: str = Depends(require_auth),
):
    """
    Upload a Pensionsmyndigheten CSV or Excel file to update PPM NAV data.
    Accepts: ppm_all_nav.csv  OR  Fondandelskurser YYYY Q*.xlsx
    After import, recalculates the dashboard automatically.
    """
    import tempfile
    from pathlib import Path as _Path

    suffix = _Path(file.filename or "upload").suffix.lower()
    if suffix not in (".csv", ".xlsx", ".xls"):
        raise HTTPException(400, "File must be .csv, .xlsx, or .xls")

    contents = await file.read()
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(contents)
        tmp_path = _Path(tmp.name)

    def _import_and_recalc():
        from ppm_fetcher import import_csv, import_excel
        try:
            if suffix == ".csv":
                n = import_csv(tmp_path, DB_PATH)
            else:
                n = import_excel(tmp_path, DB_PATH)
            log.info("PPM import: %d rows from %s", n, file.filename)
        except Exception as exc:
            log.error("PPM import failed: %s", exc)
        finally:
            tmp_path.unlink(missing_ok=True)
        _run_engine_bg()

    bg.add_task(_import_and_recalc)
    return {"status": "queued", "filename": file.filename}


# ── Screening endpoints ────────────────────────────────────────────
@app.get("/api/screening")
def get_screening():
    if not SCREENING_CONFIG.exists():
        return JSONResponse({"candidates": []})
    return JSONResponse(json.loads(SCREENING_CONFIG.read_text()))


@app.post("/api/screening/add")
def add_screening(payload: dict, bg: BackgroundTasks, _=Depends(require_auth)):
    ticker = (payload.get("ticker") or "").strip().upper()
    label  = (payload.get("label")  or "").strip()
    note   = (payload.get("note")   or "").strip()
    if not ticker or not label:
        raise HTTPException(400, "ticker and label are required")
    cfg = {"candidates": []}
    if SCREENING_CONFIG.exists():
        try:
            cfg = json.loads(SCREENING_CONFIG.read_text())
        except Exception:
            pass
    if any(c["ticker"] == ticker for c in cfg.get("candidates", [])):
        raise HTTPException(409, f"Ticker {ticker} already exists")
    cfg.setdefault("candidates", []).append({"ticker": ticker, "label": label, "note": note})
    SCREENING_CONFIG.write_text(json.dumps(cfg, indent=2, ensure_ascii=False))
    bg.add_task(_run_engine_bg)
    return {"status": "added", "ticker": ticker}


@app.get("/api/screening/history")
def get_screening_history():
    """Return consecutive-month streak data for all screener candidates."""
    try:
        from db import load_screener_streak
        return JSONResponse(load_screener_streak(path=DB_PATH))
    except Exception as e:
        log.warning(f"Screener history load failed: {e}")
        return JSONResponse({})


@app.delete("/api/screening/{ticker}")
def remove_screening(ticker: str, bg: BackgroundTasks, _=Depends(require_auth)):
    if not SCREENING_CONFIG.exists():
        raise HTTPException(404, "screening_config.json not found")
    cfg = json.loads(SCREENING_CONFIG.read_text())
    before = len(cfg.get("candidates", []))
    cfg["candidates"] = [c for c in cfg.get("candidates", []) if c["ticker"] != ticker.upper()]
    if len(cfg["candidates"]) == before:
        raise HTTPException(404, f"Ticker {ticker} not found")
    SCREENING_CONFIG.write_text(json.dumps(cfg, indent=2, ensure_ascii=False))
    bg.add_task(_run_engine_bg)
    return {"status": "removed", "ticker": ticker}


# ── Static files & SPA catch-all ──────────────────────────────────
static_dir = FRONTEND / "static"
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/")
def root():
    return FileResponse(str(FRONTEND / "index.html"))


@app.get("/{full_path:path}")
def spa_fallback(full_path: str):
    return FileResponse(str(FRONTEND / "index.html"))
