from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd
from airflow import DAG
from airflow.operators.python import PythonOperator

default_args = {
    "retries": 3,
    "retry_delay": timedelta(minutes=1),
    "retry_exponential_backoff": True,
    "sla": timedelta(minutes=10),
}

with DAG(
    dag_id="stock_quotes_dag",
    description="Fetch real-time stock quotes from Finnhub every 5 minutes",
    schedule_interval="*/5 * * * *",
    start_date=datetime(2024, 1, 1),
    catchup=False,       # Ephemeral snapshots — no value in back-filling old slots
    max_active_runs=1,   # Never run two quote jobs simultaneously
    tags=["stocks", "quotes", "finnhub"],
    default_args=default_args,
) as dag:

    def extract_task(**context) -> None:
        from etl.config import get_settings
        from etl.extract import fetch_all_quotes

        settings = get_settings()
        raw = fetch_all_quotes(settings.tickers, settings)
        context["ti"].xcom_push(key="raw_quotes", value=raw)

    def transform_task(**context) -> None:
        from etl.transform import transform_quotes

        raw = context["ti"].xcom_pull(key="raw_quotes", task_ids="extract_quotes")
        df = transform_quotes(raw)
        context["ti"].xcom_push(key="quote_records", value=df.to_dict(orient="records"))

    def load_task(**context) -> None:
        from etl.config import get_settings
        from etl.load import get_engine, upsert_quotes

        records = context["ti"].xcom_pull(key="quote_records", task_ids="transform_quotes")
        df = pd.DataFrame(records)
        settings = get_settings()
        engine = get_engine(settings.db_url)
        upsert_quotes(engine, df)

    t_extract   = PythonOperator(task_id="extract_quotes",   python_callable=extract_task)
    t_transform = PythonOperator(task_id="transform_quotes", python_callable=transform_task)
    t_load      = PythonOperator(task_id="load_quotes",      python_callable=load_task)

    t_extract >> t_transform >> t_load
