"""
Run once during airflow-init to create the Airflow metadata database and user
inside the shared PostgreSQL instance, if they do not already exist.
"""
import os
import sys

import psycopg2


def create_airflow_db() -> None:
    db_name = os.environ["AIRFLOW_DB_NAME"]
    db_user = os.environ["AIRFLOW_DB_USER"]
    db_pass = os.environ["AIRFLOW_DB_PASSWORD"]

    try:
        conn = psycopg2.connect(
            host=os.environ.get("POSTGRES_HOST", "postgres"),
            port=int(os.environ.get("POSTGRES_PORT", 5432)),
            user=os.environ["POSTGRES_USER"],
            password=os.environ["POSTGRES_PASSWORD"],
            dbname="postgres",
        )
        conn.autocommit = True
        cur = conn.cursor()

        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,))
        if not cur.fetchone():
            cur.execute(f'CREATE DATABASE "{db_name}"')
            print(f"Created database: {db_name}")
        else:
            print(f"Database already exists: {db_name}")

        cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (db_user,))
        if not cur.fetchone():
            cur.execute(f"CREATE USER {db_user} WITH PASSWORD %s", (db_pass,))
            cur.execute(f'GRANT ALL PRIVILEGES ON DATABASE "{db_name}" TO {db_user}')
            print(f"Created user: {db_user}")
        else:
            print(f"User already exists: {db_user}")

        conn.close()
        print("Airflow DB initialisation complete.")

    except Exception as exc:
        print(f"Airflow DB init failed: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    create_airflow_db()
