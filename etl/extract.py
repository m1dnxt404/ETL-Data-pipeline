import logging
import time

import requests
from ratelimit import limits, sleep_and_retry
from requests.exceptions import ConnectionError, HTTPError, Timeout
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from config import Settings

logger = logging.getLogger(__name__)

CALLS_PER_MINUTE = 60
ONE_MINUTE = 60


@sleep_and_retry
@limits(calls=CALLS_PER_MINUTE, period=ONE_MINUTE)
@retry(
    retry=retry_if_exception_type((ConnectionError, Timeout, HTTPError)),
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=2, max=60),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
def _get(url: str, params: dict, api_key: str) -> dict:
    """
    Single rate-limited, retrying HTTP GET.
    - @limits enforces 60 req/min; raises RateLimitException when exceeded.
    - @sleep_and_retry catches RateLimitException and sleeps until the window resets.
    - @retry handles transient network/HTTP errors with exponential backoff.
    """
    params = {**params, "token": api_key}
    response = requests.get(url, params=params, timeout=15)
    if response.status_code == 429:
        retry_after = int(response.headers.get("Retry-After", 60))
        logger.warning("429 from Finnhub — sleeping %ds (Retry-After)", retry_after)
        time.sleep(retry_after)
        response.raise_for_status()
    response.raise_for_status()
    return response.json()


def fetch_quote(ticker: str, settings: Settings) -> dict:
    data = _get(f"{settings.base_url}/quote", {"symbol": ticker}, settings.api_key)
    data["ticker"] = ticker
    return data


def fetch_candles(ticker: str, from_ts: int, to_ts: int, settings: Settings) -> dict:
    """
    Returns Finnhub candle response:
      {"o": [...], "h": [...], "l": [...], "c": [...], "v": [...], "t": [...], "s": "ok"}
    """
    return _get(
        f"{settings.base_url}/stock/candle",
        {"symbol": ticker, "resolution": "D", "from": from_ts, "to": to_ts},
        settings.api_key,
    )


def fetch_profile(ticker: str, settings: Settings) -> dict:
    data = _get(
        f"{settings.base_url}/stock/profile2", {"symbol": ticker}, settings.api_key
    )
    data["ticker"] = ticker
    return data


def fetch_all_quotes(tickers: list[str], settings: Settings) -> list[dict]:
    results = []
    for ticker in tickers:
        try:
            results.append(fetch_quote(ticker, settings))
            logger.debug("Fetched quote: %s", ticker)
        except Exception as e:
            logger.warning("Quote fetch failed for %s: %s", ticker, e)
    return results


def fetch_all_candles(
    tickers: list[str], from_ts: int, to_ts: int, settings: Settings
) -> list[dict]:
    results = []
    for ticker in tickers:
        try:
            data = fetch_candles(ticker, from_ts, to_ts, settings)
            if data.get("s") == "ok":
                results.append({"ticker": ticker, "data": data})
                logger.debug("Fetched candles: %s", ticker)
            else:
                logger.warning("No candle data for %s (status=%s)", ticker, data.get("s"))
        except Exception as e:
            logger.warning("Candle fetch failed for %s: %s", ticker, e)
    return results


def fetch_all_profiles(tickers: list[str], settings: Settings) -> list[dict]:
    results = []
    for ticker in tickers:
        try:
            data = fetch_profile(ticker, settings)
            if data.get("name"):
                results.append(data)
                logger.debug("Fetched profile: %s", ticker)
        except Exception as e:
            logger.warning("Profile fetch failed for %s: %s", ticker, e)
    return results
