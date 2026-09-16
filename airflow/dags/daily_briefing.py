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
from datetime import timedelta

import pendulum

from _common import setup_repo_env
from airflow import DAG
from airflow.operators.python import PythonOperator

# ---------------------------------------------------------------------------
# Task callables
# ---------------------------------------------------------------------------

def _fetch_quotes(**context):
    setup_repo_env()
    import main
    quotes = main.fetch_all_quotes()
    return quotes


def _build_earnings(**context):
    setup_repo_env()
    import main
    main.build_earnings()


def _build_prices(**context):
    setup_repo_env()
    import main
    ti = context["ti"]
    quotes = ti.xcom_pull(task_ids="fetch_quotes")
    main.build_prices(quotes=quotes)


def _build_reports(**context):
    setup_repo_env()
    import main
    main.build_reports(client=main.get_openai_client())


def _build_fundamentals(**context):
    setup_repo_env()
    import fundamentals
    fundamentals.build_fundamentals()


def _build_qualitative(**context):
    setup_repo_env()
    import main
    import fundamentals
    fundamentals.build_qualitative(client=main.get_openai_client())


def _refresh_econ(**context):
    setup_repo_env()
    import econ_results
    econ_results.refresh()


def _build_news(**context):
    setup_repo_env()
    import main
    body = main.build_body(client=main.get_openai_client())
    return body


def _publish(**context):
    setup_repo_env()
    import publish_site
    ti = context["ti"]
    quotes = ti.xcom_pull(task_ids="fetch_quotes")
    body = ti.xcom_pull(task_ids="build_news")
    publish_site.publish(body, quotes=quotes)


def _send_push(**context):
    setup_repo_env()
    import push_send
    now = pendulum.now("Asia/Seoul")
    title = f"{now.month}/{now.day} 브리핑"
    site_url = os.getenv(
        "SITE_URL", "https://kkkkkijun.github.io/stock_news_mailer/"
    )
    push_send.send_push(title, "새 뉴스 브리핑이 준비됐어요.", url=site_url)


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
