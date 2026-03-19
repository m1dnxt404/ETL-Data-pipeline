-- Stock ETL Database Schema

CREATE TABLE IF NOT EXISTS stock_quotes (
    id                  SERIAL PRIMARY KEY,
    ticker              VARCHAR(20)     NOT NULL,
    current_price       NUMERIC(12, 4),
    open                NUMERIC(12, 4),
    high                NUMERIC(12, 4),
    low                 NUMERIC(12, 4),
    prev_close          NUMERIC(12, 4),
    price_change        NUMERIC(12, 4),
    price_change_pct    NUMERIC(8, 4),
    fetched_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_stock_quote UNIQUE (ticker, fetched_at)
);

CREATE TABLE IF NOT EXISTS stock_candles (
    id          SERIAL PRIMARY KEY,
    ticker      VARCHAR(20)     NOT NULL,
    date        DATE            NOT NULL,
    open        NUMERIC(12, 4),
    high        NUMERIC(12, 4),
    low         NUMERIC(12, 4),
    close       NUMERIC(12, 4),
    volume      BIGINT,
    fetched_at  TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_stock_candle UNIQUE (ticker, date)
);

CREATE TABLE IF NOT EXISTS company_profiles (
    ticker      VARCHAR(20)     PRIMARY KEY,
    name        VARCHAR(200),
    exchange    VARCHAR(50),
    industry    VARCHAR(100),
    market_cap  NUMERIC(20, 2),
    shares_out  BIGINT,
    logo_url    TEXT,
    website     TEXT,
    updated_at  TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_quotes_ticker       ON stock_quotes (ticker);
CREATE INDEX IF NOT EXISTS idx_quotes_fetched_at   ON stock_quotes (fetched_at DESC);
CREATE INDEX IF NOT EXISTS idx_candles_ticker_date ON stock_candles (ticker, date DESC);
