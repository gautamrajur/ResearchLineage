"""
compare_models.py
=================
DAG: compare_models

Runs evaluation against 3 models in parallel, then selects the best one
using composite scoring and generates comparison visualizations.

Flow:
                    ┌──→ [eval_model_a] (run_inference >> evaluate) ──┐
    start_comparison├──→ [eval_model_b] (run_inference >> evaluate) ──┼──→ model_selection >> upload_comparison
                    └──→ [eval_model_c] (run_inference >> evaluate) ──┘
"""

import os
import sys
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.utils.task_group import TaskGroup

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from src.utils.config import (
    GCS_BUCKET_NAME,
    GCS_PROJECT_ID,
    EVAL_VERTEX_PROJECT,
    EVAL_VERTEX_LOCATION,
    EVAL_MAX_WORKERS,
    EVAL_FINETUNING_DATA_GCS_PATH,
    EVAL_JUDGE_MODEL,
)
from src.utils.logging import get_logger

logger = get_logger(__name__)

EVAL_TASK_SCRIPT = os.path.join(PROJECT_ROOT, "src", "tasks", "evaluation_task.py")
SELECTION_TASK_SCRIPT = os.path.join(PROJECT_ROOT, "src", "tasks", "model_selection_task.py")
_EVAL_BASE = f"cd {PROJECT_ROOT} && PYTHONPATH={PROJECT_ROOT} python {EVAL_TASK_SCRIPT}"
_SEL_BASE = f"cd {PROJECT_ROOT} && PYTHONPATH={PROJECT_ROOT} python {SELECTION_TASK_SCRIPT}"

# ── Model definitions ────────────────────────────────────────────────────────

MODELS = {
    "model_a": {
        "name": "qwen-7b-finetuned",
        "endpoint": "https://nekkantishiv--researchlineage-qwen-qwenmodel-infer.modal.run",
        "output_dir": "/tmp/eval_qwen7b",
    },
    "model_b": {
        "name": "qwen-72b-base",
        "endpoint": "https://jithinv03--research-lineage-serving-serve.modal.run/v1",
        "output_dir": "/tmp/eval_qwen72b",
    },
    "model_c": {
        "name": "gemini-2.5-pro",
        "endpoint": "gemini-2.5-pro",
        "output_dir": "/tmp/eval_gemini",
    },
}

# ── DAG defaults ─────────────────────────────────────────────────────────────

DEFAULT_ARGS = {
    "owner": "researchlineage",
    "depends_on_past": False,
    "email_on_failure": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=10),
}

# ── DAG ──────────────────────────────────────────────────────────────────────

with DAG(
    dag_id="compare_models",
    default_args=DEFAULT_ARGS,
    description="Parallel 3-model evaluation → selection → visualization → upload",
    schedule_interval=None,
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["researchlineage", "model-comparison", "mlops"],
    params={
        # Model A
        "model_a_endpoint": MODELS["model_a"]["endpoint"],
        "model_a_name": MODELS["model_a"]["name"],
        "model_a_output_dir": MODELS["model_a"]["output_dir"],
        # Model B
        "model_b_endpoint": MODELS["model_b"]["endpoint"],
        "model_b_name": MODELS["model_b"]["name"],
        "model_b_output_dir": MODELS["model_b"]["output_dir"],
        # Model C
        "model_c_endpoint": MODELS["model_c"]["endpoint"],
        "model_c_name": MODELS["model_c"]["name"],
        "model_c_output_dir": MODELS["model_c"]["output_dir"],
        # Shared
        "gcs_input": EVAL_FINETUNING_DATA_GCS_PATH,
        "vertex_project": EVAL_VERTEX_PROJECT,
        "vertex_location": EVAL_VERTEX_LOCATION,
        "max_workers": str(EVAL_MAX_WORKERS),
        "judge_model": EVAL_JUDGE_MODEL,
        "judge_max_tokens": "4096",
        "bucket": GCS_BUCKET_NAME,
        "project": GCS_PROJECT_ID,
        # Selection
        "comparison_output_dir": "/tmp/model_comparison",
    },
) as dag:

    def _make_eval_group(group_id, endpoint_param, output_dir_param):
        """Create a TaskGroup with run_inference >> evaluate for one model."""
        with TaskGroup(group_id=group_id) as tg:
            run_inf = BashOperator(
                task_id="run_inference",
                bash_command=(
                    _EVAL_BASE + " --step run_inference"
                    " --data-source gcs"
                    " --gcs-input '{{ params.gcs_input }}'"
                    " --output-dir '{{ params." + output_dir_param + " }}'"
                    " --model-endpoint '{{ params." + endpoint_param + " }}'"
                    " --vertex-project '{{ params.vertex_project }}'"
                    " --vertex-location '{{ params.vertex_location }}'"
                    " --max-workers {{ params.max_workers }}"
                    " --bucket '{{ params.bucket }}'"
                    " --project '{{ params.project }}'"
                    " "
                ),
                execution_timeout=timedelta(hours=6),
            )

            evaluate = BashOperator(
                task_id="evaluate",
                bash_command=(
                    _EVAL_BASE + " --step evaluate"
                    " --output-dir '{{ params." + output_dir_param + " }}'"
                    " --vertex-project '{{ params.vertex_project }}'"
                    " --vertex-location '{{ params.vertex_location }}'"
                    " --judge-model '{{ params.judge_model }}'"
                    " --judge-max-tokens {{ params.judge_max_tokens }}"
                    " "
                ),
                execution_timeout=timedelta(hours=2),
            )

            run_inf >> evaluate
        return tg

    # ── Parallel evaluation branches ─────────────────────────────────────────

    eval_model_a = _make_eval_group("eval_model_a", "model_a_endpoint", "model_a_output_dir")
    eval_model_b = _make_eval_group("eval_model_b", "model_b_endpoint", "model_b_output_dir")
    eval_model_c = _make_eval_group("eval_model_c", "model_c_endpoint", "model_c_output_dir")

    # ── Model selection + visualization ──────────────────────────────────────

    model_selection = BashOperator(
        task_id="model_selection",
        bash_command=(
            _SEL_BASE +
            " --report-dirs"
            " '{{ params.model_a_output_dir }}'"
            " '{{ params.model_b_output_dir }}'"
            " '{{ params.model_c_output_dir }}'"
            " --model-names"
            " '{{ params.model_a_name }}'"
            " '{{ params.model_b_name }}'"
            " '{{ params.model_c_name }}'"
            " --output-dir '{{ params.comparison_output_dir }}'"
            " --generate-viz"
            " --promote"
            " --bucket '{{ params.bucket }}'"
            " --project '{{ params.project }}'"
            " "
        ),
        execution_timeout=timedelta(minutes=30),
    )

    # ── Upload comparison artifacts to GCS ───────────────────────────────────

    upload_comparison = BashOperator(
        task_id="upload_comparison",
        bash_command=(
            _SEL_BASE +
            " --report-dirs"
            " '{{ params.model_a_output_dir }}'"
            " '{{ params.model_b_output_dir }}'"
            " '{{ params.model_c_output_dir }}'"
            " --model-names"
            " '{{ params.model_a_name }}'"
            " '{{ params.model_b_name }}'"
            " '{{ params.model_c_name }}'"
            " --output-dir '{{ params.comparison_output_dir }}'"
            " --upload"
            " --bucket '{{ params.bucket }}'"
            " --project '{{ params.project }}'"
            " "
        ),
        execution_timeout=timedelta(minutes=15),
    )

    # ── Email notification on completion ──────────────────────────────────────

    _NOTIFY_BASE = f"cd {PROJECT_ROOT} && PYTHONPATH={PROJECT_ROOT} python scripts/notify.py"

    notify_success = BashOperator(
        task_id="notify_success",
        bash_command=(
            _NOTIFY_BASE +
            " --channel email"
            " --event 'Model Comparison Complete (Airflow)'"
            " --status success"
            " --details 'All models evaluated and comparison uploaded to GCS.'"
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
            " --event 'Model Comparison Failed (Airflow)'"
            " --status failure"
            " --details 'One or more evaluation or selection steps failed. Check Airflow logs.'"
            " "
        ),
        trigger_rule="one_failed",
        execution_timeout=timedelta(minutes=5),
    )

    # ── Flow ─────────────────────────────────────────────────────────────────

    [eval_model_a, eval_model_b, eval_model_c] >> model_selection >> upload_comparison
    upload_comparison >> [notify_success, notify_failure]
