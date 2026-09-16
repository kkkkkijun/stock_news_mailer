"""
map_refresh DAG

Hourly refresh of the two "map" style data feeds (RWA map + whale
tracker) that are independent of the twice-daily briefing pipeline.
"""

from datetime import timedelta

import pendulum

from _common import setup_repo_env
from airflow import DAG
from airflow.operators.python import PythonOperator


def _rwa_refresh(**context):
    setup_repo_env()
    import rwa
    rwa.build_rwa()


def _whales_refresh(**context):
    setup_repo_env()
    import whales
    whales.refresh()


default_args = {
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}

with DAG(
    dag_id="map_refresh",
    start_date=pendulum.datetime(2026, 1, 1, tz="Asia/Seoul"),
    schedule="0 * * * *",
    catchup=False,
    default_args=default_args,
    tags=["market-brief", "etl"],
) as dag:

    rwa_refresh = PythonOperator(
        task_id="rwa_refresh",
        python_callable=_rwa_refresh,
    )

    whales_refresh = PythonOperator(
        task_id="whales_refresh",
        python_callable=_whales_refresh,
    )

    # No dependency between the two - independent refreshes.
