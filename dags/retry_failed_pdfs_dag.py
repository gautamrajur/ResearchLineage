"""Retry Failed PDFs DAG - Standalone DAG to retry failed PDF uploads.

This DAG runs independently from the main research_lineage_pipeline.
It queries the fetch_pdf_failures table for eligible rows and attempts
to re-download and upload PDFs that previously failed.

Trigger: Manual only (no schedule)
"""
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import datetime, timedelta  # noqa: E402
from airflow import DAG  # noqa: E402
from airflow.operators.python import PythonOperator  # noqa: E402
import asyncio  # noqa: E402

from src.tasks.retry_failed_pdfs_task import RetryFailedPdfsTask  # noqa: E402
from src.utils.logging import setup_logging  # noqa: E402

# Configure logging
setup_logging()

# Default arguments
default_args = {
    "owner": "research_lineage",
    "depends_on_past": False,
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
    "execution_timeout": timedelta(minutes=60),
}

# Create DAG
dag = DAG(
    "retry_failed_pdfs",
    default_args=default_args,
    description="Retry failed PDF uploads from fetch_pdf_failures table",
    schedule_interval=None,  # Manual trigger only
    start_date=datetime(2026, 2, 18),
    catchup=False,
    max_active_runs=1,
    tags=["research", "pdfs", "retry"],
)


def run_async_task(async_func):
    """Wrapper to run async functions in Airflow."""
    return asyncio.run(async_func)


# ══════════════════════════════════════════════════════════════════════
# Task: Retry Failed PDFs
# ══════════════════════════════════════════════════════════════════════
def task_retry_failed_pdfs(**context):
    """
    Retry failed PDF uploads.

    Queries fetch_pdf_failures table for eligible rows (retry_after passed),
    attempts to re-download and upload, updates/deletes rows based on result,
    reconciles with GCS, and sends alerts for persistent failures.
    """
    async def retry():
        task = RetryFailedPdfsTask()
        return await task.execute()

    result = run_async_task(retry())

    # Push result to XCom
    context["task_instance"].xcom_push(key="retry_result", value=result)

    # Build return message
    if result.get("status") == "error":
        raise Exception(f"Retry failed: {result.get('error')}")

    return (
        f"Retry complete: {result['succeeded']} succeeded, "
        f"{result['failed']} failed, {result['deleted_403_404']} deleted (403/404), "
        f"{result['reconciled']} reconciled, {result['alerted']} alerted"
    )


# ══════════════════════════════════════════════════════════════════════
# Define Airflow Task
# ══════════════════════════════════════════════════════════════════════

t_retry = PythonOperator(
    task_id="retry_failed_pdfs",
    python_callable=task_retry_failed_pdfs,
    dag=dag,
)


# ══════════════════════════════════════════════════════════════════════
# Visual Representation:
# ══════════════════════════════════════════════════════════════════════
#
# [retry_failed_pdfs]   (single task, manual trigger)
#
# ══════════════════════════════════════════════════════════════════════
