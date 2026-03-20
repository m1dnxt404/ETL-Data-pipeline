from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd
from airflow import DAG
from airflow.operators.python import PythonOperator

default_args = {
    "retries": 3,
    "retry_delay": timedelta(minutes=5),
    "retry_exponential_backoff": True,
    "sla": timedelta(hours=2),
}

with DAG(
    dag_id="stock_candles_dag",
    description="Fetch daily OHLCV candle data from Finnhub (backfill-capable)",
    schedule_interval="0 1 * * *",   # Daily at 01:00 UTC — after US market close
    start_date=datetime(2024, 1, 1),
    catchup=True,        # Historical OHLCV is meaningful — backfill fetches real prices
    max_active_runs=1,
    tags=["stocks", "candles", "finnhub"],
    default_args=default_args,
) as dag:

    def extract_task(**context) -> None:
        from etl.config import get_settings
        from etl.extract import fetch_all_candles

        # Airflow injects data_interval_start/end — each run covers exactly one day.
        # Backfill runs use the correct historical window automatically.
        from_ts = int(context["data_interval_start"].timestamp())
        to_ts   = int(context["data_interval_end"].timestamp())

        settings = get_settings()
        raw = fetch_all_candles(settings.tickers, from_ts, to_ts, settings)
        context["ti"].xcom_push(key="raw_candles", value=raw)

    def transform_task(**context) -> None:
        from etl.transform import transform_candles

        raw = context["ti"].xcom_pull(key="raw_candles", task_ids="extract_candles")
        df = transform_candles(raw)
        context["ti"].xcom_push(key="candle_records", value=df.to_dict(orient="records"))

    def load_task(**context) -> None:
        from etl.config import get_settings
        from etl.load import get_engine, upsert_candles

        records = context["ti"].xcom_pull(key="candle_records", task_ids="transform_candles")
        df = pd.DataFrame(records)
        settings = get_settings()
        engine = get_engine(settings.db_url)
        upsert_candles(engine, df)

    t_extract   = PythonOperator(task_id="extract_candles",   python_callable=extract_task)
    t_transform = PythonOperator(task_id="transform_candles", python_callable=transform_task)
    t_load      = PythonOperator(task_id="load_candles",      python_callable=load_task)

    t_extract >> t_transform >> t_load
