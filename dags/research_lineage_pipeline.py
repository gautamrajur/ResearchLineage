"""ResearchLineage Airflow DAG - Data pipeline for citation network analysis."""
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import datetime, timedelta  # noqa: E402
from airflow import DAG  # noqa: E402
from airflow.operators.python import PythonOperator  # noqa: E402
import asyncio  # noqa: E402
from src.tasks.schema_validation import SchemaValidationTask  # noqa: E402
from src.tasks.report_generation import ReportGenerationTask  # noqa: E402
from src.tasks.feature_engineering import FeatureEngineeringTask  # noqa: E402
from src.tasks.schema_transformation import SchemaTransformationTask  # noqa: E402
from src.tasks.quality_validation import QualityValidationTask  # noqa: E402
from src.tasks.anomaly_detection import AnomalyDetectionTask  # noqa: E402
from src.tasks.database_write import DatabaseWriteTask  # noqa: E402
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


def task_0_schema_validation(**context):
    """Task 0: Validate database schema exists."""
    task = SchemaValidationTask()
    result = task.execute()

    context["task_instance"].xcom_push(key="schema_validation", value=result)

    return f"Schema validated: {result['tables_found']}/{result['tables_checked']} tables found"


def task_1_data_acquisition(**context):
    """Task 1: Acquire paper metadata and citation network."""
    paper_id = context["dag_run"].conf.get(
        "paper_id", "204e3073870fae3d05bcbc2f6a8e263d9b72e776"
    )
    max_depth = context["dag_run"].conf.get("max_depth", 3)
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


def task_5_feature_engineering(**context):
    """Task 5: Compute derived features."""
    graph_data = context["task_instance"].xcom_pull(
        task_ids="graph_construction", key="graph_data"
    )

    task = FeatureEngineeringTask()
    result = task.execute(graph_data)

    context["task_instance"].xcom_push(key="enriched_data", value=result)

    return f"Added features to {len(result['papers'])} papers"


def task_7_schema_transformation(**context):
    """Task 7: Transform to database schema."""
    enriched_data = context["task_instance"].xcom_pull(
        task_ids="feature_engineering", key="enriched_data"
    )

    task = SchemaTransformationTask()
    result = task.execute(enriched_data)

    context["task_instance"].xcom_push(key="db_data", value=result)

    stats = result["transformation_stats"]
    return f"Transformed {stats['papers_transformed']} papers to DB schema"


def task_8_quality_validation(**context):
    """Task 8: Validate data quality."""
    db_data = context["task_instance"].xcom_pull(
        task_ids="schema_transformation", key="db_data"
    )

    task = QualityValidationTask()
    result = task.execute(db_data)

    context["task_instance"].xcom_push(key="validated_db_data", value=result)

    quality_score = result["quality_report"]["quality_score"]
    return f"Quality validation: {quality_score:.1%} score"


def task_9_anomaly_detection(**context):
    """Task 9: Detect anomalies."""
    validated_db_data = context["task_instance"].xcom_pull(
        task_ids="quality_validation", key="validated_db_data"
    )

    task = AnomalyDetectionTask()
    result = task.execute(validated_db_data)

    context["task_instance"].xcom_push(key="final_data", value=result)

    anomaly_count = result["anomaly_report"]["total_anomalies"]
    return f"Detected {anomaly_count} anomalies"


def task_10_database_write(**context):
    """Task 10: Write to database."""
    final_data = context["task_instance"].xcom_pull(
        task_ids="anomaly_detection", key="final_data"
    )

    task = DatabaseWriteTask()
    result = task.execute(final_data)

    stats = result["write_stats"]
    return (
        f"Wrote to DB: {stats['papers_written']} papers, "
        f"{stats['authors_written']} authors, {stats['citations_written']} citations"
    )


def task_11_report_generation(**context):
    """Task 11: Generate database statistics report."""
    write_result = context["task_instance"].xcom_pull(
        task_ids="database_write", key="return_value"
    )

    # If write_result is string, get the actual data
    final_data = context["task_instance"].xcom_pull(
        task_ids="anomaly_detection", key="final_data"
    )

    # Reconstruct write_result
    if isinstance(write_result, str):
        write_result = {
            "target_paper_id": final_data["target_paper_id"],
            "write_stats": {
                "papers_written": 0,
                "authors_written": 0,
                "citations_written": 0,
            },
            "quality_report": final_data["quality_report"],
            "anomaly_report": final_data["anomaly_report"],
        }

    task = ReportGenerationTask()
    result = task.execute(write_result)

    stats = result["database_stats"]
    return (
        f"Report: {stats['total_papers']} papers, "
        f"{stats['total_authors']} authors, {stats['total_citations']} citations"
    )


# Define tasks

t0_schema = PythonOperator(
    task_id="schema_validation",
    python_callable=task_0_schema_validation,
    dag=dag,
)

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
t2_validation = PythonOperator(
    task_id="data_validation",
    python_callable=task_1a_data_validation,
    dag=dag,
)

t3_cleaning = PythonOperator(
    task_id="data_cleaning",
    python_callable=task_2a_data_cleaning,
    dag=dag,
)

t4_graph = PythonOperator(
    task_id="graph_construction",
    python_callable=task_3a_graph_construction,
    dag=dag,
)

t5_features = PythonOperator(
    task_id="feature_engineering",
    python_callable=task_5_feature_engineering,
    dag=dag,
)

t7_transform = PythonOperator(
    task_id="schema_transformation",
    python_callable=task_7_schema_transformation,
    dag=dag,
)

t8_quality = PythonOperator(
    task_id="quality_validation",
    python_callable=task_8_quality_validation,
    dag=dag,
)

t9_anomaly = PythonOperator(
    task_id="anomaly_detection",
    python_callable=task_9_anomaly_detection,
    dag=dag,
)

t10_db_write = PythonOperator(
    task_id="database_write",
    python_callable=task_10_database_write,
    dag=dag,
)

t11_report = PythonOperator(
    task_id="report_generation",
    python_callable=task_11_report_generation,
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
t0_schema >> t1_acquisition >> t2_validation >> t3_cleaning >> t4_graph >> t5_features >> t7_transform >> t8_quality >> t9_anomaly >> t10_db_write >> t11_report


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
