"""
ETF Dashboard — FastAPI server
Serves frontend, exposes /api/config (GET/POST), /api/status.
"""
import json
import os
import subprocess
import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends, Header
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

BASE_DIR    = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.json"
DATA_PATH   = BASE_DIR.parent / "frontend" / "static" / "data.json"
FRONTEND    = BASE_DIR.parent / "frontend"
ENGINE      = BASE_DIR / "engine.py"

SECRET = os.getenv("DASHBOARD_SECRET", "")  # set in environment for write-auth
_engine_running = threading.Event()

app = FastAPI(title="ETF Dashboard", docs_url=None, redoc_url=None)


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
def update_config(payload: dict, bg: BackgroundTasks,
                  _=Depends(require_auth)):
    # Validate structure
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
                raise HTTPException(400, f"{sleeve}.{label}.ticker must be a non-empty string")

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
    return {
        "engine_running": _engine_running.is_set(),
        "data_generated_at": ts,
    }


@app.post("/api/recalculate")
def recalculate(bg: BackgroundTasks, _=Depends(require_auth)):
    bg.add_task(_run_engine_bg)
    return {"status": "started"}


def _run_engine_bg():
    if _engine_running.is_set():
        return
    _engine_running.set()
    try:
        subprocess.run(
            ["python3", str(ENGINE)],
            cwd=str(BASE_DIR),
            capture_output=False,
            timeout=300,
        )
    finally:
        _engine_running.clear()


# ── Static files & SPA catch-all ──────────────────────────────────
static_dir = FRONTEND / "static"
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/")
def root():
    return FileResponse(str(FRONTEND / "index.html"))


@app.get("/{full_path:path}")
def spa_fallback(full_path: str):
    # Avoid catching /api/* — FastAPI routes already handled above
    return FileResponse(str(FRONTEND / "index.html"))
