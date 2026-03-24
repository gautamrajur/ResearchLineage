"""
evaluate_performance.py
=======================
DAG: evaluate_performance

Runs inference on a test split, computes classification metrics (Flash vs Pro),
and uploads results to GCS under evaluation_metrics/.

Flow:
    run_inference → evaluate → upload_to_gcs

Inputs (set via Airflow params at trigger time):
  local_input   — local path to test.jsonl  (leave empty if using GCS)
  gcs_input     — GCS URI to test.jsonl     (leave empty if using local)
  output_dir    — local working dir for intermediate + final files
  bucket        — GCS bucket for upload
  project       — GCP project ID
"""

import os
import sys
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from src.utils.config import (
    GCS_BUCKET_NAME,
    GCS_PROJECT_ID,
    GCS_UPLOAD_PREFIX,
    EVAL_MODEL_ENDPOINT,
    EVAL_VERTEX_PROJECT,
    EVAL_VERTEX_LOCATION,
    EVAL_MAX_WORKERS,
    EVAL_OUTPUT_DIR,
    EVAL_FINETUNING_DATA_SOURCE,
    EVAL_LOCAL_INPUT,
    EVAL_FINETUNING_DATA_GCS_PATH,
    EVAL_JUDGE_MODEL,
)

TASK_SCRIPT = os.path.join(PROJECT_ROOT, "src", "tasks", "evaluation_task.py")
_BASE = f"cd {PROJECT_ROOT} && PYTHONPATH={PROJECT_ROOT} python {TASK_SCRIPT}"

# ── DAG defaults ──────────────────────────────────────────────────────────────

DEFAULT_ARGS = {
    "owner": "researchlineage",
    "depends_on_past": False,
    "email_on_failure": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=10),
}

# ── DAG ───────────────────────────────────────────────────────────────────────

with DAG(
    dag_id="evaluate_performance",
    default_args=DEFAULT_ARGS,
    description="Inference (Gemini Pro) → classification eval → GCS upload",
    schedule_interval=None,
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["researchlineage", "evaluation", "mlops"],
    params={
        # Input source routing
        "finetuning_data_source":    EVAL_FINETUNING_DATA_SOURCE,   # "local" or "gcs"
        "local_input_path":          EVAL_LOCAL_INPUT,
        "finetuning_data_gcs_path":  EVAL_FINETUNING_DATA_GCS_PATH,
        # Output
        "output_dir":                EVAL_OUTPUT_DIR,
        # GCS (upload)
        "bucket":                    GCS_BUCKET_NAME,
        "project":                   GCS_PROJECT_ID,
        "gcs_output_prefix":         GCS_UPLOAD_PREFIX,
        # Inference
        "model_endpoint":            EVAL_MODEL_ENDPOINT,
        "vertex_project":            EVAL_VERTEX_PROJECT,
        "vertex_location":           EVAL_VERTEX_LOCATION,
        "max_workers":               str(EVAL_MAX_WORKERS),
        # Judge (LLM-as-judge, used in evaluate step)
        "judge_model":               EVAL_JUDGE_MODEL,
        "judge_max_tokens":          "4096",
    },
) as dag:

    # ── STEP 1: Run inference ──────────────────────────────────────────────────
    run_inference = BashOperator(
        task_id="run_inference",
        bash_command=(
            _BASE + " --step run_inference"
            " --data-source '{{ params.finetuning_data_source }}'"
            " --local-input '{{ params.local_input_path }}'"
            "{% if params.finetuning_data_source != 'local' %}"
            " --gcs-input '{{ params.finetuning_data_gcs_path }}'"
            "{% endif %}"
            " --output-dir '{{ params.output_dir }}'"
            " --model-endpoint '{{ params.model_endpoint }}'"
            " --vertex-project '{{ params.vertex_project }}'"
            " --vertex-location '{{ params.vertex_location }}'"
            " --max-workers {{ params.max_workers }}"
            " --bucket '{{ params.bucket }}'"
            " --project '{{ params.project }}'"
            " "
        ),
        execution_timeout=timedelta(hours=6),
    )

    # ── STEP 2: Evaluate ──────────────────────────────────────────────────────
    evaluate = BashOperator(
        task_id="evaluate",
        bash_command=(
            _BASE + " --step evaluate"
            " --output-dir '{{ params.output_dir }}'"
            " --vertex-project '{{ params.vertex_project }}'"
            " --vertex-location '{{ params.vertex_location }}'"
            " --judge-model '{{ params.judge_model }}'"
            " --judge-max-tokens {{ params.judge_max_tokens }}"
            " "
        ),
        execution_timeout=timedelta(hours=2),
    )

    # ── STEP 3: Upload to GCS ─────────────────────────────────────────────────
    upload_to_gcs = BashOperator(
        task_id="upload_to_gcs",
        bash_command=(
            _BASE + " --step upload"
            " --output-dir '{{ params.output_dir }}'"
            " --gcs-input '{{ params.finetuning_data_gcs_path }}'"
            " --bucket '{{ params.bucket }}'"
            " --project '{{ params.project }}'"
            " --gcs-output-prefix '{{ params.gcs_output_prefix }}'"
            " "
        ),
        execution_timeout=timedelta(minutes=15),
    )

    # ── STEP 4: Bias check ──────────────────────────────────────────────────
    bias_check = BashOperator(
        task_id="bias_check",
        bash_command=(
            _BASE + " --step bias_check"
            " --output-dir '{{ params.output_dir }}'"
            " "
        ),
        execution_timeout=timedelta(minutes=5),
    )

    # ── Email notifications ──────────────────────────────────────────────────
    _NOTIFY_BASE = f"cd {PROJECT_ROOT} && PYTHONPATH={PROJECT_ROOT} python scripts/notify.py"

    notify_success = BashOperator(
        task_id="notify_success",
        bash_command=(
            _NOTIFY_BASE +
            " --channel email"
            " --event 'Evaluation Complete (Airflow)'"
            " --status success"
            " --details 'Inference, evaluation, upload, and bias check all passed.'"
            " "
        ),
        trigger_rule="all_success",
        execution_timeout=timedelta(minutes=5),
    )

    notify_failure = BashOperator(
        task_id="notify_failure",
        bash_command=(
            _NOTIFY_BASE +
            " --channel email"
            " --event 'Evaluation Failed (Airflow)'"
            " --status failure"
            " --details 'One or more evaluation steps failed. Check bias check and threshold logs.'"
            " "
        ),
        trigger_rule="one_failed",
        execution_timeout=timedelta(minutes=5),
    )

    # ── Flow ──────────────────────────────────────────────────────────────────
    run_inference >> evaluate >> [upload_to_gcs, bias_check]
    [upload_to_gcs, bias_check] >> [notify_success, notify_failure]
