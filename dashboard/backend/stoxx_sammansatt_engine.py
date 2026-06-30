"""stoxx_sammansatt_engine.py — Börslabbet Sammansatt Momentum på Euro STOXX 600."""
import json, logging, time
from pathlib import Path

log = logging.getLogger(__name__)

def run_stoxx_sammansatt(data_root: Path) -> tuple[dict, dict]:
    path = data_root / "results" / "stoxx_sammansatt_results.json"
    if not path.exists():
        log.warning("STOXX sammansatt: %s not found", path)
        return {}, {}
    try:
        data = json.loads(path.read_text())
        strategies = data.get("strategies", {})
        bench      = data.get("benchmark", {})
        for v in strategies.values():
            v.setdefault("benchmark", bench)
        log.info("STOXX sammansatt: %d strategies (%.1fh old)",
                 len(strategies), (time.time() - path.stat().st_mtime) / 3600)
        return strategies, {}
    except Exception as e:
        log.warning("STOXX sammansatt: failed: %s", e)
        return {}, {}
