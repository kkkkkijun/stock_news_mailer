"""
Shared setup for this repo's Airflow DAGs (daily_briefing, map_refresh).

Both DAGs need the pipeline repo importable and set as the process CWD
before importing any pipeline module (main.py, fundamentals.py, etc.),
since those modules read/write relative paths such as data/... and
docs/.... This module is the single place that logic lives.
"""

import os
import sys

REPO_ROOT = os.environ.get("PIPELINE_REPO", "/opt/airflow/repo")


def setup_repo_env():
    """Make the pipeline repo importable and set it as the CWD.

    The existing pipeline modules (main.py, fundamentals.py, etc.) assume
    the process CWD is the repo root because they read/write relative
    paths such as data/... and docs/.... Every task callable must call
    this before importing/using those modules.
    """
    if REPO_ROOT not in sys.path:
        sys.path.insert(0, REPO_ROOT)
    os.chdir(REPO_ROOT)
