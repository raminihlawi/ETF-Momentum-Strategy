"""
APScheduler — daily data refresh jobs.

Schedule (Europe/Stockholm):
  09:30  Weekdays — fetch PPM NAV (previous day) → recalculate
  18:00  Weekdays — fetch PPM NAV (today's close) → recalculate
  22:30  Weekdays — fetch ETF prices → recalculate
  06:00  2nd of each month — fetch stock prices → run sammansatt backtests → recalculate

The stock job runs on the 2nd to ensure month-end closing prices are available.
The scheduler is started once at FastAPI startup (see main.py lifespan).
All jobs run in a thread pool; the engine subprocess is guarded by an
existing lock in main.py so parallel runs are harmless.
"""
import json
import logging
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

log = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


# ── Job implementations ────────────────────────────────────────────
def _job_ppm(config_path: Path, db_path: Path, run_engine_fn) -> None:
    """09:30 job: fetch PPM NAV then recalculate."""
    from ppm_fetcher import fetch_incremental as ppm_fetch
    try:
        n = ppm_fetch(db_path=db_path)
        log.info("PPM job: %d new rows", n)
    except Exception as exc:
        log.error("PPM fetch failed: %s", exc)
    run_engine_fn()


def _job_etf(config_path: Path, db_path: Path, run_engine_fn) -> None:
    """22:30 job: fetch ETF prices then recalculate."""
    import json as _json
    from etf_fetcher import fetch_incremental, get_all_tickers

    try:
        cfg = _json.loads(config_path.read_text())
        screening_cfg_path = config_path.parent / "screening_config.json"
        screening_cfg = (
            _json.loads(screening_cfg_path.read_text())
            if screening_cfg_path.exists()
            else {}
        )
        tickers = get_all_tickers(cfg, screening_cfg)
        n = fetch_incremental(tickers, db_path)
        log.info("ETF job: %d new rows across %d tickers", n, len(tickers))
    except Exception as exc:
        log.error("ETF fetch failed: %s", exc)
    run_engine_fn()


def _job_stocks_daily(data_root: Path, backend_dir: Path, run_engine_fn) -> None:
    """Daily job (22:45): fetch incremental stock prices → extend NAV for current holdings."""
    from stock_fetcher import fetch_all
    from sammansatt_runner import extend_nav_daily

    try:
        counts = fetch_all(data_root, backend_dir)
        log.info("Stock daily fetch: %s", counts)
    except Exception as exc:
        log.error("Stock daily fetch failed: %s", exc)
        return

    try:
        nav_counts = extend_nav_daily(data_root)
        log.info("Stock NAV extension: %s", nav_counts)
    except Exception as exc:
        log.error("Stock NAV extension failed: %s", exc)

    run_engine_fn()


def _job_stocks_monthly(data_root: Path, backend_dir: Path, run_engine_fn) -> None:
    """Monthly job (2nd of month, 06:00): full sammansatt backtest with new month's rebalance."""
    from sammansatt_runner import run_all

    log.info("Stock monthly backtest: running all four universes …")
    try:
        status = run_all(data_root, backend_dir)
        log.info("Sammansatt backtests done: %s", status)
    except Exception as exc:
        log.error("Sammansatt backtest failed: %s", exc)

    run_engine_fn()


# ── Public API ─────────────────────────────────────────────────────
def start(config_path: Path, db_path: Path, run_engine_fn,
          data_root: Path | None = None, backend_dir: Path | None = None) -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        return

    tz = "Europe/Stockholm"
    _scheduler = BackgroundScheduler(timezone=tz)

    _scheduler.add_job(
        _job_ppm,
        CronTrigger(day_of_week="mon-fri", hour=9, minute=30, timezone=tz),
        args=[config_path, db_path, run_engine_fn],
        id="ppm_morning",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    _scheduler.add_job(
        _job_ppm,
        CronTrigger(day_of_week="mon-fri", hour=18, minute=0, timezone=tz),
        args=[config_path, db_path, run_engine_fn],
        id="ppm_close",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    _scheduler.add_job(
        _job_etf,
        CronTrigger(day_of_week="mon-fri", hour=22, minute=30, timezone=tz),
        args=[config_path, db_path, run_engine_fn],
        id="etf_daily",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    if data_root and backend_dir:
        # Daily: fetch incremental prices + extend NAV for current holdings
        _scheduler.add_job(
            _job_stocks_daily,
            CronTrigger(day_of_week="mon-fri", hour=22, minute=45, timezone=tz),
            args=[data_root, backend_dir, run_engine_fn],
            id="stocks_daily",
            replace_existing=True,
            misfire_grace_time=3600,
        )
        # Monthly: full backtest on the 1st at 01:00 CET.
        # Prices were fetched the previous evening (22:45) on the last trading day
        # of the month, so the backtest runs with correct month-end closing prices
        # and the new allocation is ready before European markets open (~09:00).
        _scheduler.add_job(
            _job_stocks_monthly,
            CronTrigger(day=1, hour=1, minute=0, timezone=tz),
            args=[data_root, backend_dir, run_engine_fn],
            id="stocks_monthly",
            replace_existing=True,
            misfire_grace_time=7200,
        )

    _scheduler.start()
    log.info(
        "Scheduler started — PPM @ 09:30+18:00, ETF @ 22:30, Stocks @ 22:45 (weekdays), "
        "Full backtest @ 01:00 on 1st of month (CET) — ready before EU open"
    )


def stop() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        _scheduler = None
