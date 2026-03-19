import logging

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from models import Base, CompanyProfile, StockCandle, StockQuote

logger = logging.getLogger(__name__)


def get_engine(db_url: str):
    return create_engine(
        db_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        echo=False,
    )


def ensure_tables(engine) -> None:
    Base.metadata.create_all(engine)
    logger.info("Tables verified / created")


def _clean(records: list[dict]) -> list[dict]:
    """Replace pandas NaN / NaT with None for SQL NULL compatibility."""
    cleaned = []
    for row in records:
        cleaned.append(
            {k: (None if (isinstance(v, float) and pd.isna(v)) or
                        (hasattr(v, '__class__') and v.__class__.__name__ == 'NaT')
                        else v)
             for k, v in row.items()}
        )
    return cleaned


def upsert_quotes(engine, df: pd.DataFrame) -> int:
    if df.empty:
        return 0
    records = _clean(df.to_dict(orient="records"))
    stmt = pg_insert(StockQuote).values(records)
    upsert = stmt.on_conflict_do_update(
        index_elements=["ticker", "fetched_at"],
        set_={
            col.name: stmt.excluded[col.name]
            for col in StockQuote.__table__.columns
            if col.name not in ("id", "ticker", "fetched_at")
        },
    )
    with engine.begin() as conn:
        result = conn.execute(upsert)
    logger.info("Upserted %d quote rows", result.rowcount)
    return result.rowcount


def upsert_candles(engine, df: pd.DataFrame) -> int:
    if df.empty:
        return 0
    records = _clean(df.to_dict(orient="records"))
    stmt = pg_insert(StockCandle).values(records)
    upsert = stmt.on_conflict_do_update(
        index_elements=["ticker", "date"],
        set_={
            "open":       stmt.excluded.open,
            "high":       stmt.excluded.high,
            "low":        stmt.excluded.low,
            "close":      stmt.excluded.close,
            "volume":     stmt.excluded.volume,
            "fetched_at": stmt.excluded.fetched_at,
        },
    )
    with engine.begin() as conn:
        result = conn.execute(upsert)
    logger.info("Upserted %d candle rows", result.rowcount)
    return result.rowcount


def upsert_profiles(engine, df: pd.DataFrame) -> int:
    if df.empty:
        return 0
    records = _clean(df.to_dict(orient="records"))
    stmt = pg_insert(CompanyProfile).values(records)
    upsert = stmt.on_conflict_do_update(
        index_elements=["ticker"],
        set_={
            col.name: stmt.excluded[col.name]
            for col in CompanyProfile.__table__.columns
            if col.name != "ticker"
        },
    )
    with engine.begin() as conn:
        result = conn.execute(upsert)
    logger.info("Upserted %d profile rows", result.rowcount)
    return result.rowcount
