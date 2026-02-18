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


def task_1_data_acquisition(**context):
    """Task 1: Acquire paper metadata and citation network."""
    # Get paper_id from DAG run config
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

    # Push to XCom (only paper IDs, not full data)
    context["task_instance"].xcom_push(key="raw_data", value=result)
    context["task_instance"].xcom_push(key="paper_count", value=result["total_papers"])

    return f"Acquired {result['total_papers']} papers"


def task_2_data_validation(**context):
    """Task 2: Validate raw data."""
    # Pull from XCom
    raw_data = context["task_instance"].xcom_pull(
        task_ids="data_acquisition", key="raw_data"
    )

    task = DataValidationTask()
    result = task.execute(raw_data)

    # Push to XCom
    context["task_instance"].xcom_push(key="validated_data", value=result)

    error_rate = result["validation_report"]["error_rate"]
    return f"Validated with {error_rate:.2%} error rate"


def task_3_data_cleaning(**context):
    """Task 3: Clean and normalize data."""
    # Pull from XCom
    validated_data = context["task_instance"].xcom_pull(
        task_ids="data_validation", key="validated_data"
    )

    task = DataCleaningTask()
    result = task.execute(validated_data)

    # Push to XCom
    context["task_instance"].xcom_push(key="cleaned_data", value=result)

    stats = result["cleaning_stats"]
    return f"Cleaned {stats['cleaned_papers']} papers, removed {stats['duplicates_removed']} duplicates"


def task_4_graph_construction(**context):
    """Task 4: Build citation graph."""
    # Pull from XCom
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


# Define tasks
t1_acquisition = PythonOperator(
    task_id="data_acquisition",
    python_callable=task_1_data_acquisition,
    dag=dag,
)

t2_validation = PythonOperator(
    task_id="data_validation",
    python_callable=task_2_data_validation,
    dag=dag,
)

t3_cleaning = PythonOperator(
    task_id="data_cleaning",
    python_callable=task_3_data_cleaning,
    dag=dag,
)

t4_graph = PythonOperator(
    task_id="graph_construction",
    python_callable=task_4_graph_construction,
    dag=dag,
)

# Define task dependencies
t1_acquisition >> t2_validation >> t3_cleaning >> t4_graph
