import logging
import time
from datetime import datetime, timezone

from sqlalchemy import text

from config import get_settings
from extract import fetch_all_candles, fetch_all_profiles, fetch_all_quotes
from load import ensure_tables, get_engine, upsert_candles, upsert_profiles, upsert_quotes
from scheduler import run_candle_job, run_quote_job, start_scheduler
from transform import transform_candles, transform_profiles, transform_quotes

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)


def wait_for_db(engine, max_retries: int = 10, delay: int = 5) -> None:
    for attempt in range(1, max_retries + 1):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.info("Database is ready")
            return
        except Exception as e:
            logger.warning(
                "DB not ready (attempt %d/%d): %s", attempt, max_retries, e
            )
            time.sleep(delay)
    raise RuntimeError("Database never became ready after %d attempts" % max_retries)


def initial_load(settings, engine) -> None:
    """Run a full historical load on first startup."""
    logger.info("Running initial full load (%d-day history)...", settings.history_days)

    # Quotes
    run_quote_job(settings, engine)

    # Historical candles
    now = int(datetime.now(timezone.utc).timestamp())
    from_ts = now - settings.history_days * 86400
    raw_candles = fetch_all_candles(settings.tickers, from_ts, now, settings)
    df_candles = transform_candles(raw_candles)
    upsert_candles(engine, df_candles)
    logger.info("Initial candle load: %d rows", len(df_candles))

    # Company profiles (once on startup)
    raw_profiles = fetch_all_profiles(settings.tickers, settings)
    df_profiles = transform_profiles(raw_profiles)
    upsert_profiles(engine, df_profiles)
    logger.info("Company profiles loaded: %d rows", len(df_profiles))


if __name__ == "__main__":
    settings = get_settings()
    engine = get_engine(settings.db_url)

    wait_for_db(engine)
    ensure_tables(engine)
    initial_load(settings, engine)
    start_scheduler(settings, engine)
