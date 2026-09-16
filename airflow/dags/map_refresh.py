"""
map_refresh DAG

Hourly refresh of the two "map" style data feeds (RWA map + whale
tracker) that are independent of the twice-daily briefing pipeline.
"""

import os
import sys
from datetime import timedelta

import pendulum

from airflow import DAG
from airflow.operators.python import PythonOperator

REPO_ROOT = os.environ.get("PIPELINE_REPO", "/opt/airflow/repo")


def _setup_repo_env():
    if REPO_ROOT not in sys.path:
        sys.path.insert(0, REPO_ROOT)
    os.chdir(REPO_ROOT)


def _rwa_refresh(**context):
    _setup_repo_env()
    try:
        import rwa
        rwa.build_rwa()
    except Exception:
        raise


def _whales_refresh(**context):
    _setup_repo_env()
    try:
        import whales
        whales.refresh()
    except Exception:
        raise


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
