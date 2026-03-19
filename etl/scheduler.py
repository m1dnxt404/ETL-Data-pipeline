import logging
import time
from datetime import datetime, timezone

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger

from config import Settings
from extract import fetch_all_candles, fetch_all_quotes
from transform import transform_candles, transform_quotes
from load import upsert_candles, upsert_quotes

logger = logging.getLogger(__name__)


def run_quote_job(settings: Settings, engine) -> None:
    logger.info("--- Quote job started ---")
    try:
        raw = fetch_all_quotes(settings.tickers, settings)
        logger.info("Extracted %d quotes", len(raw))
    except Exception as e:
        logger.error("Quote extraction failed: %s", e)
        return

    try:
        df = transform_quotes(raw)
        logger.info("Transformed %d valid quote rows", len(df))
    except Exception as e:
        logger.error("Quote transform failed: %s", e)
        return

    try:
        upsert_quotes(engine, df)
    except Exception as e:
        logger.error("Quote load failed: %s", e)

    logger.info("--- Quote job complete ---")


def run_candle_job(settings: Settings, engine, days: int = 2) -> None:
    logger.info("--- Candle job started (last %d days) ---", days)
    now = int(datetime.now(timezone.utc).timestamp())
    from_ts = now - days * 86400

    try:
        raw = fetch_all_candles(settings.tickers, from_ts, now, settings)
        logger.info("Extracted candle data for %d tickers", len(raw))
    except Exception as e:
        logger.error("Candle extraction failed: %s", e)
        return

    try:
        df = transform_candles(raw)
        logger.info("Transformed %d candle rows", len(df))
    except Exception as e:
        logger.error("Candle transform failed: %s", e)
        return

    try:
        upsert_candles(engine, df)
    except Exception as e:
        logger.error("Candle load failed: %s", e)

    logger.info("--- Candle job complete ---")


def start_scheduler(settings: Settings, engine) -> None:
    scheduler = BlockingScheduler(timezone="UTC")

    scheduler.add_job(
        func=run_quote_job,
        trigger=IntervalTrigger(seconds=settings.interval_seconds),
        args=[settings, engine],
        id="quote_job",
        name="Finnhub Quote ETL",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=60,
    )

    scheduler.add_job(
        func=run_candle_job,
        trigger=IntervalTrigger(hours=24),
        args=[settings, engine],
        id="candle_job",
        name="Finnhub Daily Candle ETL",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=300,
    )

    logger.info(
        "Scheduler starting — quote interval: %ds, candle interval: 24h",
        settings.interval_seconds,
    )
    scheduler.start()
