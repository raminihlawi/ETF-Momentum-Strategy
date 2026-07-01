"""sp500_sammansatt_engine.py — Börslabbet Sammansatt Momentum på S&P 500 (PIT)."""
import json, logging, time
from pathlib import Path

log = logging.getLogger(__name__)

def run_sp500_sammansatt(data_root: Path) -> tuple[dict, dict]:
    path = data_root / "results" / "sp500_sammansatt_results.json"
    if not path.exists():
        log.warning("SP500 sammansatt: %s not found", path)
        return {}, {}
    try:
        data         = json.loads(path.read_text())
        strategies   = data.get("strategies", {})
        bench        = data.get("benchmark", {})
        company_info = data.get("company_info", {})
        for v in strategies.values():
            v.setdefault("benchmark", bench)
        log.info("SP500 sammansatt: %d strategies, %d tickers (%.1fh old)",
                 len(strategies), len(company_info), (time.time() - path.stat().st_mtime) / 3600)
        return strategies, company_info
    except Exception as e:
        log.warning("SP500 sammansatt: failed: %s", e)
        return {}, {}
