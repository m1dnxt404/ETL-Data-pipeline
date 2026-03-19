import logging

import pandas as pd

logger = logging.getLogger(__name__)


def transform_quotes(raw: list[dict]) -> pd.DataFrame:
    if not raw:
        return pd.DataFrame()

    df = pd.DataFrame(raw)

    df.rename(
        columns={
            "c": "current_price",
            "o": "open",
            "h": "high",
            "l": "low",
            "pc": "prev_close",
            "d": "price_change",
            "dp": "price_change_pct",
        },
        inplace=True,
    )

    for col in ["current_price", "open", "high", "low", "prev_close",
                "price_change", "price_change_pct"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df["fetched_at"] = pd.Timestamp.utcnow().floor("min")

    # Remove rows with missing/zero price (market closed or bad data)
    df = df.dropna(subset=["ticker", "current_price"])
    df = df[df["current_price"] > 0]
    df = df.drop_duplicates(subset=["ticker"])

    keep = ["ticker", "current_price", "open", "high", "low",
            "prev_close", "price_change", "price_change_pct", "fetched_at"]
    return df[[c for c in keep if c in df.columns]]


def transform_candles(raw: list[dict]) -> pd.DataFrame:
    if not raw:
        return pd.DataFrame()

    records = []
    for item in raw:
        ticker = item["ticker"]
        d = item["data"]
        try:
            for ts, o, h, l, c, v in zip(
                d["t"], d["o"], d["h"], d["l"], d["c"], d["v"]
            ):
                records.append(
                    {
                        "ticker": ticker,
                        "date": pd.Timestamp(ts, unit="s", tz="UTC").date(),
                        "open": o,
                        "high": h,
                        "low": l,
                        "close": c,
                        "volume": int(v) if v else None,
                    }
                )
        except (KeyError, TypeError) as e:
            logger.warning("Skipping malformed candle data for %s: %s", ticker, e)

    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records)
    for col in ["open", "high", "low", "close"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df["fetched_at"] = pd.Timestamp.utcnow()
    df = df.dropna(subset=["ticker", "date", "close"])
    df = df.drop_duplicates(subset=["ticker", "date"])
    return df


def transform_profiles(raw: list[dict]) -> pd.DataFrame:
    if not raw:
        return pd.DataFrame()

    df = pd.DataFrame(raw)

    rename_map = {
        "name": "name",
        "exchange": "exchange",
        "finnhubIndustry": "industry",
        "marketCapitalization": "market_cap",
        "shareOutstanding": "shares_out",
        "logo": "logo_url",
        "weburl": "website",
    }
    df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns}, inplace=True)

    if "market_cap" in df.columns:
        # Finnhub returns market cap in millions USD
        df["market_cap"] = pd.to_numeric(df["market_cap"], errors="coerce") * 1_000_000
    if "shares_out" in df.columns:
        df["shares_out"] = pd.to_numeric(df["shares_out"], errors="coerce")

    df["updated_at"] = pd.Timestamp.utcnow()
    df = df.dropna(subset=["ticker", "name"])
    df = df.drop_duplicates(subset=["ticker"])

    keep = ["ticker", "name", "exchange", "industry", "market_cap",
            "shares_out", "logo_url", "website", "updated_at"]
    return df[[c for c in keep if c in df.columns]]
