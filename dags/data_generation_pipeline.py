"""
timeline_pipeline_dag.py - Airflow DAG for ResearchLineage Timeline Pipeline

DAG Structure:
    seed_generation → batch_run → preprocessing → upload_to_gcs

Uses BashOperator to run each stage as a shell command.
No import issues — each task runs in its own process.

Location: dags/timeline_pipeline_dag.py
Pipeline code: timeline_view/
"""

import os
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.models import Variable


# ========================================
# Paths
# ========================================

# Path to timeline_view directory (relative to project root)
# Adjust if your Airflow setup has a different working directory
PROJECT_ROOT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
TIMELINE_DIR = os.path.join(PROJECT_ROOT, "timeline_view")
PYTHON = os.path.join(PROJECT_ROOT, ".venv", "Scripts", "python")  # Windows
# PYTHON = os.path.join(PROJECT_ROOT, ".venv", "bin", "python")    # Linux/Mac


# ========================================
# Default Config — override via Airflow Variables or dag_run.conf
# ========================================

def get_var(key, default):
    """Get from Airflow Variable or use default."""
    try:
        return Variable.get(f"rl_{key}")
    except KeyError:
        return default


# ========================================
# DAG Definition
# ========================================

DEFAULT_ARGS = {
    "owner": "researchlineage",
    "depends_on_past": False,
    "email_on_failure": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}


with DAG(
    dag_id="researchlineage_timeline_pipeline",
    default_args=DEFAULT_ARGS,
    description="Generate research lineage timelines and training data",
    schedule_interval=None,  # Manual trigger only
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["researchlineage", "mlops", "timeline"],
    params={
        "domains": "Physics:70,Mathematics:40",
        "min_citations": "3000",
        "per_domain_pool": "5000",
        "query": "",
        "seeds_file": "inputs/seeds.json",
        "max_depth": "5",
        "max_seeds": "110",
        "sleep": "3",
        "gcs_bucket": "researchlineage-data",
        "gcs_project": "mlops-researchlineage",
    },
) as dag:

    # ========================================
    # Stage 1: Seed Generation
    # ========================================
    seed_generation = BashOperator(
        task_id="seed_generation",
        bash_command=f"""
            cd {TIMELINE_DIR} && \
            {PYTHON} seed_picker.py \
                --n {{{{ params.max_seeds }}}} \
                --domains "{{{{ params.domains }}}}" \
                --min-citations {{{{ params.min_citations }}}} \
                --per-domain-pool {{{{ params.per_domain_pool }}}} \
                --query "{{{{ params.query }}}}" \
                --out {{{{ params.seeds_file }}}}
        """,
    )

    # ========================================
    # Stage 2: Batch Run
    # ========================================
    batch_run = BashOperator(
        task_id="batch_run",
        bash_command=f"""
            cd {TIMELINE_DIR} && \
            {PYTHON} batch_run.py \
                --seeds {{{{ params.seeds_file }}}} \
                --depth {{{{ params.max_depth }}}} \
                --max-seeds {{{{ params.max_seeds }}}} \
                --resume \
                --sleep {{{{ params.sleep }}}}
        """,
        execution_timeout=timedelta(hours=12),
    )

    # ========================================
    # Stage 3: Preprocessing
    # ========================================
    # Placeholder — replace with actual preprocessing script later
    preprocessing = BashOperator(
        task_id="preprocessing",
        bash_command=f"""
            cd {TIMELINE_DIR} && \
            {PYTHON} -c "
import json, os
training_file = os.path.join('outputs', 'lineage_training_data.jsonl')
if not os.path.exists(training_file):
    print('No training data found')
    exit(0)
total = valid = 0
with open(training_file, 'r') as f:
    for line in f:
        if not line.strip(): continue
        total += 1
        try:
            e = json.loads(line)
            if e.get('output') and e.get('input'): valid += 1
        except: pass
print(f'Training data: {{total}} total, {{valid}} valid, {{total-valid}} invalid')
"
        """,
    )

    # ========================================
    # Stage 4: Upload to GCS
    # ========================================
    upload_to_gcs = BashOperator(
        task_id="upload_to_gcs",
        bash_command=f"""
            cd {TIMELINE_DIR} && \
            {PYTHON} gcs_upload.py \
                --bucket {{{{ params.gcs_bucket }}}} \
                --project {{{{ params.gcs_project }}}} \
                --sync
        """,
    )

    # ========================================
    # DAG Flow
    # ========================================
    seed_generation >> batch_run >> preprocessing >> upload_to_gcs