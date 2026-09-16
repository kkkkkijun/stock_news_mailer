"""
daily_briefing DAG

Orchestrates the existing batch pipeline (main.py / fundamentals.py /
econ_results.py / publish_site.py / push_send.py) with Apache Airflow.

This is a portfolio / prototype orchestration layer. The production
pipeline still runs via GitHub Actions + cron-job.org; this DAG shows
the same ETL steps modeled as an Airflow DAG (parallel extract/transform,
fan-in publish, retries, tz-aware scheduling).

Schedule: 06:00 and 17:00 Asia/Seoul, every day.
"""

import os
import sys
from datetime import timedelta

import pendulum

from airflow import DAG
from airflow.operators.python import PythonOperator

# ---------------------------------------------------------------------------
# Repo path setup
# ---------------------------------------------------------------------------

REPO_ROOT = os.environ.get("PIPELINE_REPO", "/opt/airflow/repo")


def _setup_repo_env():
    """Make the pipeline repo importable and set it as the CWD.

    The existing pipeline modules (main.py, fundamentals.py, etc.) assume
    the process CWD is the repo root because they read/write relative
    paths such as data/... and docs/.... Every task callable must call
    this before importing/using those modules.
    """
    if REPO_ROOT not in sys.path:
        sys.path.insert(0, REPO_ROOT)
    os.chdir(REPO_ROOT)


# ---------------------------------------------------------------------------
# Task callables
# ---------------------------------------------------------------------------

def _fetch_quotes(**context):
    _setup_repo_env()
    try:
        import main
        quotes = main.fetch_all_quotes()
        return quotes
    except Exception:
        raise


def _build_earnings(**context):
    _setup_repo_env()
    try:
        import main
        main.build_earnings()
    except Exception:
        raise


def _build_prices(**context):
    _setup_repo_env()
    try:
        import main
        ti = context["ti"]
        quotes = ti.xcom_pull(task_ids="fetch_quotes")
        main.build_prices(quotes=quotes)
    except Exception:
        raise


def _build_reports(**context):
    _setup_repo_env()
    try:
        import main
        main.build_reports(client=main.get_openai_client())
    except Exception:
        raise


def _build_fundamentals(**context):
    _setup_repo_env()
    try:
        import fundamentals
        fundamentals.build_fundamentals()
    except Exception:
        raise


def _build_qualitative(**context):
    _setup_repo_env()
    try:
        import main
        import fundamentals
        fundamentals.build_qualitative(client=main.get_openai_client())
    except Exception:
        raise


def _refresh_econ(**context):
    _setup_repo_env()
    try:
        import econ_results
        econ_results.refresh()
    except Exception:
        raise


def _build_news(**context):
    _setup_repo_env()
    try:
        import main
        body = main.build_body(client=main.get_openai_client())
        return body
    except Exception:
        raise


def _publish(**context):
    _setup_repo_env()
    try:
        import publish_site
        ti = context["ti"]
        quotes = ti.xcom_pull(task_ids="fetch_quotes")
        body = ti.xcom_pull(task_ids="build_news")
        publish_site.publish(body, quotes=quotes)
    except Exception:
        raise


def _send_push(**context):
    _setup_repo_env()
    try:
        import push_send
        now = pendulum.now("Asia/Seoul")
        title = f"{now.month}/{now.day} 브리핑"
        site_url = os.getenv(
            "SITE_URL", "https://kkkkkijun.github.io/stock_news_mailer/"
        )
        push_send.send_push(title, "새 뉴스 브리핑이 준비됐어요.", url=site_url)
    except Exception:
        raise


# ---------------------------------------------------------------------------
# DAG definition
# ---------------------------------------------------------------------------

default_args = {
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}

with DAG(
    dag_id="daily_briefing",
    start_date=pendulum.datetime(2026, 1, 1, tz="Asia/Seoul"),
    schedule="0 6,17 * * *",
    catchup=False,
    default_args=default_args,
    tags=["market-brief", "etl"],
) as dag:

    fetch_quotes = PythonOperator(
        task_id="fetch_quotes",
        python_callable=_fetch_quotes,
    )

    build_earnings = PythonOperator(
        task_id="build_earnings",
        python_callable=_build_earnings,
    )

    build_prices = PythonOperator(
        task_id="build_prices",
        python_callable=_build_prices,
    )

    build_reports = PythonOperator(
        task_id="build_reports",
        python_callable=_build_reports,
    )

    build_fundamentals = PythonOperator(
        task_id="build_fundamentals",
        python_callable=_build_fundamentals,
    )

    build_qualitative = PythonOperator(
        task_id="build_qualitative",
        python_callable=_build_qualitative,
    )

    refresh_econ = PythonOperator(
        task_id="refresh_econ",
        python_callable=_refresh_econ,
    )

    build_news = PythonOperator(
        task_id="build_news",
        python_callable=_build_news,
    )

    publish = PythonOperator(
        task_id="publish",
        python_callable=_publish,
    )

    send_push = PythonOperator(
        task_id="send_push",
        python_callable=_send_push,
    )

    # Extract -> transform branches, fanning in to publish -> push
    fetch_quotes >> build_prices
    build_earnings >> build_reports
    # build_qualitative reads (and augments) the fundamentals.json that
    # build_fundamentals writes, so it must run after it.
    build_fundamentals >> build_qualitative

    [
        build_prices,
        build_reports,
        build_qualitative,
        refresh_econ,
        build_news,
    ] >> publish >> send_push
