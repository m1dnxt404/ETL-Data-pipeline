FROM apache/airflow:2.9.2

COPY requirements.txt /airflow-requirements.txt
COPY scripts/ /opt/airflow/scripts/

RUN pip install --no-cache-dir -r /airflow-requirements.txt
