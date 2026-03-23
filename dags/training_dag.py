"""
dags/training_dag.py - ResearchLineage Model Fine-Tuning Pipeline (Modal Edition)

Flow:
1. Wait for new formatted data in GCS
2. Check whether enough new samples exist
3. Preprocess / validate train + val data
4. Skip training - using existing model v20260320_184258
5. Always deploy to Modal serving endpoint
6. Update pipeline_state.json
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

from airflow import DAG
from airflow.models import Variable
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator, ShortCircuitOperator
from airflow.providers.google.cloud.sensors.gcs import GCSObjectExistenceSensor

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.config import GCS_PROJECT_ID, GCS_UPLOAD_PREFIX

GCS_BUCKET = Variable.get("GCS_BUCKET", default_var="researchlineage-gcs")
GCP_PROJECT = Variable.get("GCP_PROJECT_ID", default_var=GCS_PROJECT_ID)
MIN_NEW_SAMPLES = int(Variable.get("MIN_NEW_SAMPLES", default_var="50"))

MODAL_SERVE_SCRIPT_PATH = str(PROJECT_ROOT / "scripts" / "modal_serve.py")
MODAL_APP_NAME = Variable.get("MODAL_APP_NAME", default_var="research-lineage-serving")
SERVING_MAX_LEN = 102400
MODEL_VERSION = "v20260320_184258"

GCS_PREFIX = GCS_UPLOAD_PREFIX.rstrip("/")
GCS_QWEN_FORMAT = f"{GCS_PREFIX}/qwen_format"
GCS_TRAINED_MODELS = "models/trained"
GCS_PIPELINE_STATE = "pipeline_state.json"
GCS_SENSOR_OBJECT = f"{GCS_QWEN_FORMAT}/train.jsonl"

LOCAL_TMP = Path("/tmp/lineage_training")


def get_gcs_bucket():
    from google.cloud import storage
    client = storage.Client(project=GCP_PROJECT)
    return client.bucket(GCS_BUCKET)


def check_new_data(**ctx):
    LOCAL_TMP.mkdir(parents=True, exist_ok=True)
    bucket = get_gcs_bucket()
    local_train = LOCAL_TMP / "train.jsonl"

    bucket.blob(f"{GCS_QWEN_FORMAT}/train.jsonl").download_to_filename(str(local_train))

    with open(local_train, "r", encoding="utf-8") as f:
        total_samples = sum(1 for line in f if line.strip())

    last_trained_count = 0
    try:
        state_data = bucket.blob(GCS_PIPELINE_STATE).download_as_text()
        last_trained_count = json.loads(state_data).get("last_trained_sample_count", 0)
    except Exception:
        print("No pipeline_state.json found. Treating this as first run.")

    new_samples = total_samples - last_trained_count
    print(f"Total samples: {total_samples}, New: {new_samples}")

    if new_samples < MIN_NEW_SAMPLES:
        print(f"Skipping: only {new_samples} new samples, need {MIN_NEW_SAMPLES}.")
        return False

    version = f"v{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    ti = ctx["ti"]
    ti.xcom_push(key="total_samples", value=total_samples)
    ti.xcom_push(key="new_samples", value=new_samples)
    ti.xcom_push(key="model_version", value=version)
    ti.xcom_push(key="gcs_output", value=f"{GCS_TRAINED_MODELS}/{version}")
    ti.xcom_push(key="model_gcs_uri", value=f"gs://{GCS_BUCKET}/{GCS_TRAINED_MODELS}/{version}")
    return True


def preprocess_data(**ctx):
    bucket = get_gcs_bucket()
    LOCAL_TMP.mkdir(parents=True, exist_ok=True)

    for split in ["train", "val"]:
        local_path = LOCAL_TMP / f"{split}.jsonl"
        bucket.blob(f"{GCS_QWEN_FORMAT}/{split}.jsonl").download_to_filename(str(local_path))

        valid_count = 0
        with open(local_path, "r", encoding="utf-8") as f:
            for i, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError as e:
                    raise ValueError(f"{split}.jsonl line {i} is invalid JSON: {e}")
                if "text" not in row or not isinstance(row["text"], str) or not row["text"].strip():
                    raise ValueError(f"{split}.jsonl line {i} missing or invalid 'text' field")
                valid_count += 1

        if valid_count == 0:
            raise ValueError(f"{split}.jsonl contains no valid records")
        print(f"Validated {valid_count} rows in {split}.jsonl")


def update_pipeline_state(**ctx):
    ti = ctx["ti"]
    state = {
        "last_trained_sample_count": ti.xcom_pull(key="total_samples", task_ids="check_new_data"),
        "last_new_samples": ti.xcom_pull(key="new_samples", task_ids="check_new_data"),
        "last_model_version": MODEL_VERSION,
        "last_model_gcs_uri": f"gs://{GCS_BUCKET}/{GCS_TRAINED_MODELS}/{MODEL_VERSION}",
        "last_serving_platform": "modal",
        "last_modal_app_name": MODAL_APP_NAME,
        "serving_max_len": SERVING_MAX_LEN,
        "updated_at": datetime.now().isoformat(),
    }
    get_gcs_bucket().blob(GCS_PIPELINE_STATE).upload_from_string(
        json.dumps(state, indent=2), content_type="application/json"
    )
    print("Updated pipeline_state.json")
    print(json.dumps(state, indent=2))


def log_to_mlflow(**ctx):
    """Log training parameters and metrics to MLflow after training."""
    from src.mlflow_utils import log_training_run, register_model

    ti = ctx["ti"]
    model_version = MODEL_VERSION
    model_uri = f"gs://{GCS_BUCKET}/{GCS_TRAINED_MODELS}/{model_version}"

    params = {
        "base_model": "unsloth/Qwen2.5-7B-Instruct",
        "lora_r": 16,
        "lora_alpha": 16,
        "lora_dropout": 0.0,
        "epochs": 3,
        "learning_rate": 2e-4,
        "batch_size": 1,
        "gradient_accumulation_steps": 64,
        "max_seq_length": SERVING_MAX_LEN,
        "optimizer": "paged_adamw_8bit",
    }

    total_samples = ti.xcom_pull(key="total_samples", task_ids="check_new_data") or 0
    metrics = {
        "total_training_samples": float(total_samples),
    }

    # Try to load training_metrics.json from GCS if it exists
    try:
        bucket = get_gcs_bucket()
        metrics_blob = bucket.blob(f"{GCS_TRAINED_MODELS}/{model_version}/training_metrics.json")
        if metrics_blob.exists():
            import json as _json
            train_metrics = _json.loads(metrics_blob.download_as_text())
            metrics.update({
                k: float(v) for k, v in train_metrics.items()
                if isinstance(v, (int, float))
            })
    except Exception as e:
        print(f"Could not load training_metrics.json: {e}")

    run_id = log_training_run(
        params=params,
        metrics=metrics,
        model_uri=model_uri,
        tags={"model_version": model_version},
    )
    print(f"MLflow run logged: {run_id}")

    register_model(run_id=run_id, model_uri=model_uri)
    print(f"Model registered in MLflow: {model_version}")


default_args = {
    "owner": "researchlineage",
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

with DAG(
    dag_id="lineage_training_dag_modal",
    default_args=default_args,
    start_date=datetime(2026, 3, 1),
    schedule=None,
    catchup=False,
    tags=["researchlineage", "training", "modal", "serving"],
) as dag:

    task_sensor = GCSObjectExistenceSensor(
        task_id="wait_for_new_data",
        bucket=GCS_BUCKET,
        object=GCS_SENSOR_OBJECT,
        mode="reschedule",
        poke_interval=300,
        timeout=60 * 60 * 6,
    )

    task_check = ShortCircuitOperator(
        task_id="check_new_data",
        python_callable=check_new_data,
    )

    task_preprocess = PythonOperator(
        task_id="preprocess_data",
        python_callable=preprocess_data,
    )

    task_train = BashOperator(
        task_id="train_on_modal",
        retries=0,
        bash_command="echo 'Training skipped - using existing model " + MODEL_VERSION + "'",
    )

    task_gate = ShortCircuitOperator(
        task_id="should_deploy",
        python_callable=lambda **kwargs: True,
    )

    task_deploy_modal = BashOperator(
    task_id="deploy_modal_endpoint",
    bash_command=(
        "modal secret create serving-config"
        " MODEL_GCS_PATH=gs://" + GCS_BUCKET + "/models/trained/" + MODEL_VERSION +
        " SERVING_MAX_LEN=" + str(SERVING_MAX_LEN) +
        ' HF_MODEL_NAME=""'
        " --force && "
        "MODAL_APP_NAME=research-lineage-serving-test "
        "python -m modal deploy " + MODAL_SERVE_SCRIPT_PATH +
        " | tee /tmp/modal_deploy_output.txt && "
        "grep -o 'https://[^ ]*modal.run[^ ]*' /tmp/modal_deploy_output.txt | head -1"
    ),
    do_xcom_push=True,
)

    task_log_mlflow = PythonOperator(
        task_id="log_to_mlflow",
        python_callable=log_to_mlflow,
    )

    task_update_state = PythonOperator(
        task_id="update_pipeline_state",
        python_callable=update_pipeline_state,
    )

    task_print_endpoint = BashOperator(
        task_id="print_endpoint",
        bash_command=(
            "echo 'Serving endpoint: "
            "{{ ti.xcom_pull(task_ids=\"deploy_modal_endpoint\") }}'"
        ),
    )

    (
        task_sensor
        >> task_check
        >> task_preprocess
        >> task_train
        >> task_log_mlflow
        >> task_gate
        >> task_deploy_modal
        >> task_print_endpoint
        >> task_update_state
    )