"""
fine_tuning_dag.py - Full ResearchLineage Fine-Tuning Data Pipeline

Uses the self-contained lineage_pipeline.py for all steps.

    seed_generation → batch_run → preprocessing → repair
                                                     ↓
                                              stratified_split
                                                     ↓
                                          convert_to_llama_format
                                                     ↓
                                              pipeline_report
                                                     ↓
                                            upload_to_gcs

Location: dags/fine_tuning_dag.py
Pipeline: src/tasks/lineage_pipeline.py
"""

import os
import sys
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator


# ========================================
# Paths & Config Import
# ========================================

PROJECT_ROOT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
sys.path.insert(0, PROJECT_ROOT)

from src.utils.config import (
    SEED_DEFAULT_COUNT, SEED_DOMAINS, SEED_MIN_CITATIONS,
    SEED_PER_DOMAIN_POOL, SEED_QUERY,
    MAX_DEPTH, MAX_SEEDS_PER_RUN, BATCH_SLEEP_BETWEEN_SEEDS,
    SPLIT_TRAIN_FRAC, SPLIT_VAL_FRAC, SPLIT_TEST_FRAC, SPLIT_RANDOM_SEED,
    GCS_BUCKET_NAME, GCS_PROJECT_ID, GCS_UPLOAD_PREFIX,
)

PIPELINE_SCRIPT = os.path.join(PROJECT_ROOT, "src", "tasks", "lineage_pipeline.py")

# Base command — set PYTHONPATH so src.utils.config is importable
_BASE = f"cd {PROJECT_ROOT} && PYTHONPATH={PROJECT_ROOT} python {PIPELINE_SCRIPT}"

# ========================================
# DAG Definition
# ========================================

DEFAULT_ARGS = {
    "owner": "researchlineage",
    "depends_on_past": False,
    "email_on_failure": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}

with DAG(
    dag_id="fine_tuning_pipeline",
    default_args=DEFAULT_ARGS,
    description="End-to-end: seed generation → lineage tracing → split → convert → report → GCS upload",
    schedule_interval=None,
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["researchlineage", "fine-tuning", "mlops", "end-to-end"],
    params={
        # Step 1: Seed generation
        "n_seeds": str(SEED_DEFAULT_COUNT),
        "domains": ",".join(SEED_DOMAINS),
        "min_citations": str(SEED_MIN_CITATIONS),
        "per_domain_pool": str(SEED_PER_DOMAIN_POOL),
        "seed_query": SEED_QUERY,
        # Step 2: Batch run
        "max_depth": str(MAX_DEPTH),
        "max_seeds": str(MAX_SEEDS_PER_RUN),
        "batch_sleep": str(BATCH_SLEEP_BETWEEN_SEEDS),
        # Step 5: Split
        "train_frac": str(SPLIT_TRAIN_FRAC),
        "val_frac": str(SPLIT_VAL_FRAC),
        "test_frac": str(SPLIT_TEST_FRAC),
        "split_seed": str(SPLIT_RANDOM_SEED),
        # Step 8: GCS
        "bucket": GCS_BUCKET_NAME,
        "project": GCS_PROJECT_ID,
        "gcs_prefix": GCS_UPLOAD_PREFIX,
    },
) as dag:

    # ════════════════════════════════════════
    # STEP 1: SEED GENERATION
    # ════════════════════════════════════════
    seed_generation = BashOperator(
        task_id="seed_generation",
        bash_command=(
            f'{_BASE} --step seed_generation'
            ' --n-seeds {{ params.n_seeds }}'
            ' --domains "{{ params.domains }}"'
            ' --min-citations {{ params.min_citations }}'
            ' --per-domain-pool {{ params.per_domain_pool }}'
            ' --seed-query "{{ params.seed_query }}"'
            ' '
        ),
        execution_timeout=timedelta(minutes=30),
    )

    # ════════════════════════════════════════
    # STEP 2: BATCH LINEAGE TRACING
    # ════════════════════════════════════════
    batch_run = BashOperator(
        task_id="batch_run",
        bash_command=(
            f'{_BASE} --step batch_run'
            ' --max-depth {{ params.max_depth }}'
            ' --max-seeds {{ params.max_seeds }}'
            ' --batch-sleep {{ params.batch_sleep }}'
            ' '
        ),
        execution_timeout=timedelta(hours=12),
    )

    # ════════════════════════════════════════
    # STEP 3: PREPROCESSING / VALIDATION
    # ════════════════════════════════════════
    preprocessing = BashOperator(
        task_id="preprocessing",
        bash_command=f'{_BASE} --step preprocessing ',
        execution_timeout=timedelta(minutes=10),
    )

    # ════════════════════════════════════════
    # STEP 4: REPAIR LINEAGE CHAINS
    # ════════════════════════════════════════
    repair = BashOperator(
        task_id="repair_lineage_chains",
        bash_command=f'{_BASE} --step repair ',
        execution_timeout=timedelta(minutes=10),
    )

    # ════════════════════════════════════════
    # STEP 5: STRATIFIED SPLIT
    # ════════════════════════════════════════
    split = BashOperator(
        task_id="stratified_split",
        bash_command=(
            f'{_BASE} --step split'
            ' --train-frac {{ params.train_frac }}'
            ' --val-frac {{ params.val_frac }}'
            ' --test-frac {{ params.test_frac }}'
            ' --seed {{ params.split_seed }}'
            ' '
        ),
        execution_timeout=timedelta(minutes=10),
    )

    # ════════════════════════════════════════
    # STEP 6: CONVERT TO LLAMA FORMAT
    # ════════════════════════════════════════
    convert = BashOperator(
        task_id="convert_to_llama_format",
        bash_command=f'{_BASE} --step convert ',
        execution_timeout=timedelta(minutes=10),
    )

    # ════════════════════════════════════════
    # STEP 7: PIPELINE REPORT
    # ════════════════════════════════════════
    report = BashOperator(
        task_id="pipeline_report",
        bash_command=f'{_BASE} --step report ',
        execution_timeout=timedelta(minutes=10),
    )

    # ════════════════════════════════════════
    # STEP 8: UPLOAD TO GCS
    # ════════════════════════════════════════
    upload = BashOperator(
        task_id="upload_to_gcs",
        bash_command=(
            f'{_BASE} --step upload'
            ' --bucket {{ params.bucket }}'
            ' --project {{ params.project }}'
            ' --gcs-prefix {{ params.gcs_prefix }}'
            ' '
        ),
        execution_timeout=timedelta(minutes=30),
    )

    # ════════════════════════════════════════
    # DAG FLOW
    # ════════════════════════════════════════
    (
        seed_generation
        >> batch_run
        >> preprocessing
        >> repair
        >> split
        >> convert
        >> report
        >> upload
    )