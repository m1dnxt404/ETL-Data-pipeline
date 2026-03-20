# Stock Market ETL Pipeline

A production-style ETL pipeline that extracts real-time and historical stock market data from the [Finnhub API](https://finnhub.io), transforms it with pandas, loads it into PostgreSQL, and visualizes it in a Streamlit dashboard — all containerized with Docker Compose and orchestrated by Apache Airflow.

---

## Architecture

```text
┌──────────────────────────────────────────────────────────────────┐
│                          Docker Network                          │
│                                                                  │
│  ┌──────────┐   ┌───────────────────────────────────────────┐    │
│  │ Finnhub  │──▶│              Apache Airflow              │    │
│  │   API    │   │                                           │    │
│  └──────────┘   │  ┌─────────────┐   ┌──────────────────┐   │    │
│                 │  │  Scheduler  │   │  Celery Worker   │   │    │
│  Rate limit:    │  └─────────────┘   └──────────────────┘   │    │
│  60 req/min     │  ┌─────────────┐   ┌──────────────────┐   │    │
│  (enforced)     │  │  Webserver  │   │      Redis       │   │    │
│                 │  │   :8080     │   │  (Celery broker) │   │    │
│                 │  └─────────────┘   └──────────────────┘   │    │
│                 └───────────────────────┬───────────────────┘    │
│                                         │                        │
│                              ┌──────────▼──────────┐             │
│                              │      PostgreSQL      │            │
│                              │                      │            │
│                              │  stocks_etl DB:      │            │
│                              │  · stock_quotes      │            │
│                              │  · stock_candles     │            │
│                              │  · company_profiles  │            │
│                              │                      │            │
│                              │  airflow DB:         │            │
│                              │  · DAG run metadata  │            │
│                              └──────────┬───────────┘            │
│                                         │                        │
│                    ┌────────────────────┼                        │
│                    │                    │                        │
│           ┌────────▼───────┐   ┌────────▼───────┐                │
│           │   Streamlit    │   │    pgAdmin     │                │
│           │   Dashboard    │   │    :5050       │                │
│           │   :8501        │   └────────────────┘                │
│           └────────────────┘                                     │
└──────────────────────────────────────────────────────────────────┘
```

### ETL Flow (per DAG run)

```text
Airflow DAG Task 1       Task 2                  Task 3
────────────────────────────────────────────────────────────
extract_quotes      ──▶  transform_quotes   ──▶  load_quotes
  Finnhub /quote          rename columns          upsert →
  (60 req/min cap)        type coercion           stock_quotes
  push to XCom            NaN → NULL
                          pull/push XCom

extract_candles     ──▶  transform_candles  ──▶  load_candles
  Finnhub /candle         pivot arrays            upsert →
  data_interval           filter nulls            stock_candles
  aware (backfill)        push to XCom
```

---

## Project Structure

```text
ETL Data pipeline/
├── .env                           # secrets — never commit
├── .env.example                   # template
├── .gitignore
├── docker-compose.yml
│
├── airflow/
│   ├── Dockerfile                 # apache/airflow:2.9.2 + ETL deps
│   ├── requirements.txt           # ETL dependencies for Airflow workers
│   ├── scripts/
│   │   └── init_db.py             # creates Airflow metadata DB on first run
│   └── dags/
│       ├── stock_quotes_dag.py    # */5 * * * *, catchup=False
│       └── stock_candles_dag.py   # 0 1 * * *, catchup=True (backfill-capable)
│
├── etl/                           # shared ETL library — imported by Airflow tasks
│   ├── __init__.py
│   ├── config.py                  # typed settings from env vars
│   ├── extract.py                 # Finnhub client: rate limit + retry + pagination
│   ├── transform.py               # pandas cleaning and normalization
│   ├── load.py                    # SQLAlchemy upserts (INSERT … ON CONFLICT DO UPDATE)
│   ├── models.py                  # ORM table definitions
│   └── requirements.txt
│
├── dashboard/
│   ├── app.py                     # Streamlit: KPIs, table, bar chart, candlestick
│   ├── requirements.txt
│   └── Dockerfile
│
├── db/
│   └── init.sql                   # PostgreSQL schema (3 tables + indexes)
│
└── pgadmin/
    └── servers.json               # pre-configured pgAdmin server connection
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

Set your Finnhub API key and generate the two required Airflow security keys:

```bash
# Set your Finnhub key
FINNHUB_API_KEY=your_real_api_key_here

# Generate Fernet key (encryption for Airflow connections/variables)
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Generate secret key (Airflow webserver sessions)
python -c "import secrets; print(secrets.token_hex(32))"
```

Paste both generated values into `.env`:

```dotenv
FINNHUB_API_KEY=your_real_api_key_here
AIRFLOW_FERNET_KEY=<output of fernet command>
AIRFLOW_SECRET_KEY=<output of secrets command>
```

### 3. Start all services

```bash
docker compose up --build
```

First startup takes ~3–4 minutes: images build, `airflow-init` runs DB migrations and creates the admin user, then all services come online.

| Service             | URL                   | Credentials               |
|---------------------|-----------------------|---------------------------|
| Airflow UI          | http://localhost:8080 | admin / admin             |
| Streamlit Dashboard | http://localhost:8501 | —                         |
| pgAdmin             | http://localhost:5050 | `admin@admin.com` / admin |
| PostgreSQL          | localhost:5432        | see `.env`                |

### 4. Stop

```bash
docker compose down
```

To also remove all stored data and volumes:

```bash
docker compose down -v
```

---

## Services

### Airflow (orchestration)

Apache Airflow with **CeleryExecutor** runs two DAGs:

| DAG | Schedule | `catchup` | What it does |
|---|---|---|---|
| `stock_quotes_dag` | `*/5 * * * *` | `False` | Fetches real-time quotes for all tickers → `stock_quotes` |
| `stock_candles_dag` | `0 1 * * *` | `True` | Fetches OHLCV candles for the day's interval → `stock_candles` |

Each DAG has three tasks: **extract → transform → load**, linked in sequence. Intermediate data is passed between tasks via Airflow **XCom**.

**Key Airflow features in use:**

| Feature | Configuration |
|---|---|
| Per-task retries | `retries=3`, `retry_exponential_backoff=True` |
| SLA monitoring | `sla=timedelta(minutes=10)` on quotes; `sla=timedelta(hours=2)` on candles |
| No concurrent runs | `max_active_runs=1` on each DAG |
| Backfill support | `catchup=True` on `stock_candles_dag` — each run uses `data_interval_start/end` |

#### Running a backfill

```bash
docker compose exec airflow-scheduler \
  airflow dags backfill stock_candles_dag \
  --start-date 2024-01-01 --end-date 2024-01-31
```

### ETL Library (`etl/`)

The `etl/` directory is a shared Python package mounted into all Airflow containers at `/opt/airflow/dags/etl`. DAG tasks import directly from it:

```python
from etl.config import get_settings
from etl.extract import fetch_all_quotes
from etl.transform import transform_quotes
from etl.load import get_engine, upsert_quotes
```

**Rate limiting** is enforced in `etl/extract.py` via `@sleep_and_retry` + `@limits(calls=60, period=60)` from the `ratelimit` library — every Finnhub call across all tasks counts against the shared 60 req/min window. Tenacity `@retry` handles transient network errors with exponential backoff (2 s → 4 s → 8 s → 16 s → 32 s, max 5 attempts).

### Dashboard (`dashboard/`)

Streamlit app with auto-refresh every 60 seconds:

- KPI row: tickers tracked, gainers/losers count, top gainer, top loser
- Market overview table: all tickers with price, change %, high/low
- Daily price change % bar chart (green/red color scale)
- Intraday price trend line chart (selected ticker)
- Candlestick chart with configurable date range (selected ticker)
- Volume bar chart (selected ticker)

### PostgreSQL (`db/`)

Two databases in one container:

| Database     | Purpose                                                                       |
|--------------|-------------------------------------------------------------------------------|
| `stocks_etl` | Application data (created by `db/init.sql`)                                   |
| `airflow`    | Airflow metadata — DAG runs, task instances, XCom (created by `airflow-init`) |

Three application tables:

| Table              | Description                    | Upsert Key             |
|--------------------|--------------------------------|------------------------|
| `stock_quotes`     | Real-time snapshot per DAG run | `(ticker, fetched_at)` |
| `stock_candles`    | Daily OHLCV history            | `(ticker, date)`       |
| `company_profiles` | Static company info            | `ticker`               |

---

## Configuration Reference

| Variable | Default | Description |
|---|---|---|
| `FINNHUB_API_KEY` | — | **Required.** Your Finnhub API key |
| `STOCK_TICKERS` | 14 large-cap US stocks | Comma-separated ticker symbols |
| `HISTORY_DAYS` | `30` | Days of candle history to pre-load |
| `POSTGRES_DB` | `stocks_etl` | Stocks database name |
| `POSTGRES_USER` | `etl_user` | Stocks database user |
| `POSTGRES_PASSWORD` | `etl_secret_password` | Stocks database password |
| `AIRFLOW_DB_NAME` | `airflow` | Airflow metadata database name |
| `AIRFLOW_DB_USER` | `airflow` | Airflow metadata database user |
| `AIRFLOW_DB_PASSWORD` | `airflow_secret` | Airflow metadata database password |
| `AIRFLOW_FERNET_KEY` | — | **Required.** Encrypts Airflow secrets |
| `AIRFLOW_SECRET_KEY` | — | **Required.** Signs Airflow web sessions |
| `AIRFLOW_ADMIN_PASSWORD` | `admin` | Airflow UI admin password |
| `PGADMIN_DEFAULT_EMAIL` | `admin@admin.com` | pgAdmin login email |
| `PGADMIN_DEFAULT_PASSWORD` | `admin` | pgAdmin login password |

---

## Development

### View Airflow task logs

```bash
docker compose logs airflow-worker -f
```

### Trigger a DAG manually via CLI

```bash
docker compose exec airflow-scheduler airflow dags trigger stock_quotes_dag
```

### Connect to the stocks database

```bash
docker compose exec postgres psql -U etl_user -d stocks_etl
```

### Connect to the Airflow metadata database

```bash
docker compose exec postgres psql -U airflow -d airflow
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
| Orchestration | Apache Airflow 2.9 (CeleryExecutor) |
| Message broker | Redis 7 |
| Dashboard | Streamlit + Plotly |
| Containerization | Docker + Docker Compose |
