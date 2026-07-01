"""nasdaq_sammansatt_engine.py — Börslabbet Sammansatt Momentum på Nasdaq (top ~200)."""
import json, logging, time
from pathlib import Path

log = logging.getLogger(__name__)

def run_nasdaq_sammansatt(data_root: Path) -> tuple[dict, dict, dict]:
    """Return (strategies_dict, company_info_dict, all_scores_dict) for dashboard."""
    path = data_root / "results" / "nasdaq_sammansatt_results.json"
    if not path.exists():
        log.warning("Nasdaq sammansatt: %s not found", path)
        return {}, {}, {}
    try:
        data         = json.loads(path.read_text())
        strategies   = data.get("strategies", {})
        bench        = data.get("benchmark", {})
        company_info = data.get("company_info", {})
        all_scores   = data.get("all_scores", {})
        for v in strategies.values():
            v.setdefault("benchmark", bench)
        log.info("Nasdaq sammansatt: %d strategies, %d tickers (%.1fh old)",
                 len(strategies), len(company_info), (time.time() - path.stat().st_mtime) / 3600)
        return strategies, company_info, all_scores
    except Exception as e:
        log.warning("Nasdaq sammansatt: failed: %s", e)
        return {}, {}, {}
