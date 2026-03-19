# Stock Market ETL Pipeline

A production-style ETL pipeline that extracts real-time and historical stock market data from the [Finnhub API](https://finnhub.io), transforms it with pandas, loads it into PostgreSQL, and visualizes it in a Streamlit dashboard — all containerized with Docker Compose.

---

## Architecture

```text
┌────────────────────────────────────────────────────────┐
│                     Docker Network                     │
│                                                        │
│  ┌──────────┐    ┌──────────┐    ┌──────────────────┐  │
│  │ Finnhub  │───▶│   ETL    │───▶│   PostgreSQL    │  │
│  │   API    │    │ Service  │    │                  │  │
│  └──────────┘    └──────────┘    │  stock_quotes    │  │
│                                  │  stock_candles   │  │
│  Rate limit:                     │  company_profiles│  │
│  60 req/min                      └────────┬─────────┘  │
│  (enforced)                               │            │
│                                  ┌────────▼─────────┐  │
│                                  │   Streamlit      │  │
│                                  │   Dashboard      │  │
│                                  │  :8501           │  │
│                                  └──────────────────┘  │
│                                                        │
│                                  ┌──────────────────┐  │
│                                  │    pgAdmin       │  │
│                                  │    :5050         │  │
│                                  └──────────────────┘  │
└────────────────────────────────────────────────────────┘
```

### ETL Flow

```text
Extract                  Transform               Load
───────                  ─────────               ────
Finnhub /quote      ──▶  rename columns    ──▶  upsert → stock_quotes
Finnhub /candle     ──▶  type coercion     ──▶  upsert → stock_candles
Finnhub /profile2   ──▶  filter nulls/0s   ──▶  upsert → company_profiles
  (paginated over tickers,  NaN → NULL
   rate-limited 60/min)     floor to minute
```

---

## Project Structure

```text
ETL Data pipeline/
├── .env                       # secrets — never commit
├── .env.example               # template
├── .gitignore
├── docker-compose.yml
│
├── etl/
│   ├── config.py              # typed settings from env vars
│   ├── extract.py             # Finnhub client: rate limit + retry + pagination
│   ├── transform.py           # pandas cleaning and normalization
│   ├── load.py                # SQLAlchemy upserts (INSERT … ON CONFLICT DO UPDATE)
│   ├── models.py              # ORM table definitions
│   ├── scheduler.py           # APScheduler: quote job (5 min), candle job (24 h)
│   ├── main.py                # entry point: wait for DB → initial load → schedule
│   ├── requirements.txt
│   └── Dockerfile
│
├── dashboard/
│   ├── app.py                 # Streamlit: KPIs, table, bar chart, candlestick
│   ├── requirements.txt
│   └── Dockerfile
│
├── db/
│   └── init.sql               # PostgreSQL schema (3 tables + indexes)
│
└── pgadmin/
    └── servers.json           # pre-configured pgAdmin server connection
```

---

## Prerequisites

| Requirement     | Version                                  |
|-----------------|------------------------------------------|
| Docker Desktop  | 24+                                      |
| Docker Compose  | v2+                                      |
| Finnhub API key | free at [finnhub.io](https://finnhub.io) |

---

## Quick Start

### 1. Get a free Finnhub API key

Register at [https://finnhub.io](https://finnhub.io) — the free tier provides **60 requests/minute**, which is sufficient for the default ticker list.

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and set your API key:

```dotenv
FINNHUB_API_KEY=your_real_api_key_here
```

Optionally customize the ticker list:

```dotenv
STOCK_TICKERS=AAPL,MSFT,GOOGL,AMZN,NVDA,META,TSLA,JPM,V,WMT,JNJ,XOM,UNH,MA
```

### 3. Start all services

```bash
docker compose up --build
```

First startup takes ~2 minutes to build images. Once running:

| Service             | URL                   |
|---------------------|-----------------------|
| Streamlit Dashboard | http://localhost:8501 |
| pgAdmin             | http://localhost:5050 |
| PostgreSQL          | localhost:5432        |

pgAdmin login: `admin@admin.com` / `admin`

### 4. Stop

```bash
docker compose down
```

To also remove stored data:

```bash
docker compose down -v
```

---

## Services

### ETL (`etl/`)

Runs on startup and then on a schedule:

| Job          | Trigger         | What it does                                              |
|--------------|-----------------|-----------------------------------------------------------|
| Quote job    | Every 5 minutes | Fetches real-time quotes for all tickers → `stock_quotes` |
| Candle job   | Every 24 hours  | Fetches last 2 days of OHLCV → `stock_candles`            |
| Initial load | On startup only | Fetches full history (default 30 days) + company profiles |

**Rate limiting** is enforced at the HTTP layer via `@sleep_and_retry` + `@limits(calls=60, period=60)` from the `ratelimit` library. A tenacity `@retry` decorator handles transient network errors with exponential backoff (2s → 4s → 8s → 16s → 32s, max 5 attempts).

### Dashboard (`dashboard/`)

Streamlit app with auto-refresh every 60 seconds:

- KPI row: tickers tracked, gainers/losers count, top gainer, top loser
- Market overview table: all tickers with price, change %, high/low
- Daily price change % bar chart (green/red color scale)
- Intraday price trend line chart (selected ticker)
- Candlestick chart with configurable date range (selected ticker)
- Volume bar chart (selected ticker)

### PostgreSQL (`db/`)

Three tables:

| Table | Description | Upsert Key |
|---|---|---|
| `stock_quotes` | Real-time snapshot per ETL run | `(ticker, fetched_at)` |
| `stock_candles` | Daily OHLCV history | `(ticker, date)` |
| `company_profiles` | Static company info | `ticker` |

---

## Configuration Reference

All settings are read from environment variables (`.env` file):

| Variable | Default | Description |
|---|---|---|
| `FINNHUB_API_KEY` | — | **Required.** Your Finnhub API key |
| `STOCK_TICKERS` | 14 large-cap US stocks | Comma-separated list of ticker symbols |
| `ETL_INTERVAL_SECONDS` | `300` | How often to fetch quotes (seconds) |
| `HISTORY_DAYS` | `30` | Days of candle history to load on startup |
| `POSTGRES_DB` | `stocks_etl` | Database name |
| `POSTGRES_USER` | `etl_user` | Database user |
| `POSTGRES_PASSWORD` | `etl_secret_password` | Database password |
| `PGADMIN_DEFAULT_EMAIL` | `admin@admin.com` | pgAdmin login email |
| `PGADMIN_DEFAULT_PASSWORD` | `admin` | pgAdmin login password |

---

## Development

To run the ETL outside Docker (useful for debugging):

```bash
cd etl
pip install -r requirements.txt
# set env vars or copy .env to etl/
python main.py
```

To view live ETL logs:

```bash
docker compose logs etl -f
```

To connect to the database directly:

```bash
docker compose exec postgres psql -U etl_user -d stocks_etl
```

---

## Stack

| Layer | Technology |
|---|---|
| Language | Python 3.12 |
| HTTP client | requests + tenacity (retry) + ratelimit |
| Data transformation | pandas |
| ORM / DB | SQLAlchemy 2.0 + psycopg2 |
| Database | PostgreSQL 16 |
| Scheduler | APScheduler 3.x |
| Dashboard | Streamlit + Plotly |
| Containerization | Docker + Docker Compose |
