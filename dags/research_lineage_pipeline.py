"""ResearchLineage Airflow DAG - Data pipeline for citation network analysis."""
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import datetime, timedelta  # noqa: E402
from airflow import DAG  # noqa: E402
from airflow.operators.python import PythonOperator  # noqa: E402
import asyncio  # noqa: E402

from src.tasks.data_acquisition import DataAcquisitionTask  # noqa: E402
from src.tasks.data_validation import DataValidationTask  # noqa: E402
from src.tasks.data_cleaning import DataCleaningTask  # noqa: E402
from src.tasks.citation_graph_construction import CitationGraphConstructionTask  # noqa: E402
from src.tasks.pdf_upload_task import PDFUploadTask  # noqa: E402
from src.utils.logging import setup_logging  # noqa: E402

# Configure logging
setup_logging()

# Default arguments
default_args = {
    "owner": "research_lineage",
    "depends_on_past": False,
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 3,
    "retry_delay": timedelta(minutes=5),
    "execution_timeout": timedelta(minutes=60),
}

# Create DAG
dag = DAG(
    "research_lineage_pipeline",
    default_args=default_args,
    description="Fetch and process research paper citation networks",
    schedule_interval=None,  # Manual trigger only
    start_date=datetime(2026, 2, 18),
    catchup=False,
    max_active_runs=1,
    tags=["research", "citations", "ml"],
)


def run_async_task(async_func):
    """Wrapper to run async functions in Airflow."""
    return asyncio.run(async_func)


# ══════════════════════════════════════════════════════════════════════
# Task 1: Data Acquisition (shared by both branches)
# ══════════════════════════════════════════════════════════════════════
def task_1_data_acquisition(**context):
    """Task 1: Acquire paper metadata and citation network."""
    paper_id = context["dag_run"].conf.get(
        "paper_id", "204e3073870fae3d05bcbc2f6a8e263d9b72e776"
    )
    max_depth = context["dag_run"].conf.get("max_depth", 1)
    direction = context["dag_run"].conf.get("direction", "both")

    async def acquire():
        task = DataAcquisitionTask()
        result = await task.execute(
            paper_id=paper_id, max_depth=max_depth, direction=direction
        )
        await task.close()
        return result

    result = run_async_task(acquire())

    # Push to XCom (used by BOTH branches)
    context["task_instance"].xcom_push(key="raw_data", value=result)
    context["task_instance"].xcom_push(key="paper_count", value=result["total_papers"])

    return f"Acquired {result['total_papers']} papers"


# ══════════════════════════════════════════════════════════════════════
# Branch A: Validation → Cleaning → Graph Construction
# ══════════════════════════════════════════════════════════════════════
def task_1a_data_validation(**context):
    """Task 1a: Validate raw data (Branch A start)."""
    raw_data = context["task_instance"].xcom_pull(
        task_ids="data_acquisition", key="raw_data"
    )

    task = DataValidationTask()
    result = task.execute(raw_data)

    context["task_instance"].xcom_push(key="validated_data", value=result)

    error_rate = result["validation_report"]["error_rate"]
    return f"Validated with {error_rate:.2%} error rate"


def task_2a_data_cleaning(**context):
    """Task 2a: Clean and normalize data."""
    validated_data = context["task_instance"].xcom_pull(
        task_ids="data_validation", key="validated_data"
    )

    task = DataCleaningTask()
    result = task.execute(validated_data)

    context["task_instance"].xcom_push(key="cleaned_data", value=result)

    stats = result["cleaning_stats"]
    return f"Cleaned {stats['cleaned_papers']} papers, removed {stats['duplicates_removed']} duplicates"


def task_3a_graph_construction(**context):
    """Task 3a: Build citation graph."""
    cleaned_data = context["task_instance"].xcom_pull(
        task_ids="data_cleaning", key="cleaned_data"
    )

    task = CitationGraphConstructionTask()
    result = task.execute(cleaned_data)

    # Note: NetworkX graphs can't be serialized to XCom easily
    # So we'll store summary data only
    graph_summary = {
        "target_paper_id": result["target_paper_id"],
        "papers": result["papers"],
        "references": result["references"],
        "citations": result["citations"],
        "graph_stats": result["graph_stats"],
        "metrics": result["metrics"],
        "components": result["components"],
    }

    context["task_instance"].xcom_push(key="graph_data", value=graph_summary)

    stats = result["graph_stats"]
    return f"Built graph: {stats['num_nodes']} nodes, {stats['num_edges']} edges"


# ══════════════════════════════════════════════════════════════════════
# Branch B: PDF Upload (parallel to Branch A)
# ══════════════════════════════════════════════════════════════════════
def task_1b_pdf_upload(**context):
    """
    Task 1b: Upload PDFs to GCS using pre-fetched acquisition data (Branch B).

    Runs in parallel with the validation/cleaning/graph branch.
    Uses the same raw_data from data_acquisition task.
    """
    # Pull acquisition result from data_acquisition task
    acquisition_result = context["task_instance"].xcom_pull(
        task_ids="data_acquisition", key="raw_data"
    )

    if not acquisition_result or not acquisition_result.get("papers"):
        return "No papers to process for PDF upload"

    async def upload():
        task = PDFUploadTask()
        return await task.execute(acquisition_result)

    result = run_async_task(upload())

    # Push result to XCom for potential downstream use
    context["task_instance"].xcom_push(key="pdf_upload_result", value=result)

    return (
        f"PDF upload: {result['uploaded']} uploaded, "
        f"{result['already_in_gcs']} already in GCS, "
        f"{result['download_failed']} failed"
    )


# ══════════════════════════════════════════════════════════════════════
# Define Airflow Tasks
# ══════════════════════════════════════════════════════════════════════

# Task 1: Shared entry point
t1_acquisition = PythonOperator(
    task_id="data_acquisition",
    python_callable=task_1_data_acquisition,
    dag=dag,
)

# Branch A: Validation → Cleaning → Graph
t1a_validation = PythonOperator(
    task_id="data_validation",
    python_callable=task_1a_data_validation,
    dag=dag,
)

t2a_cleaning = PythonOperator(
    task_id="data_cleaning",
    python_callable=task_2a_data_cleaning,
    dag=dag,
)

t3a_graph = PythonOperator(
    task_id="graph_construction",
    python_callable=task_3a_graph_construction,
    dag=dag,
)

# Branch B: PDF Upload (parallel)
t1b_pdf_upload = PythonOperator(
    task_id="pdf_upload",
    python_callable=task_1b_pdf_upload,
    dag=dag,
    # Longer timeout for PDF downloads
    execution_timeout=timedelta(minutes=120),
)


# ══════════════════════════════════════════════════════════════════════
# Define Task Dependencies (Parallel Branches)
# ══════════════════════════════════════════════════════════════════════

# Branch A: data_acquisition → validation → cleaning → graph
t1_acquisition >> t1a_validation >> t2a_cleaning >> t3a_graph

# Branch B: data_acquisition → pdf_upload (runs in parallel with Branch A)
t1_acquisition >> t1b_pdf_upload


# ══════════════════════════════════════════════════════════════════════
# Visual Representation:
# ══════════════════════════════════════════════════════════════════════
#
#                          ┌──→ [t1a_validation] ──→ [t2a_cleaning] ──→ [t3a_graph]
# [t1_acquisition] ────────┤
#                          └──→ [t1b_pdf_upload]
#
# ══════════════════════════════════════════════════════════════════════
