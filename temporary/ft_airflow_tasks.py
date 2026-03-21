"""Airflow DAG tasks for Llama 3 LoRA fine-tuning.

This module provides Airflow-compatible task functions for the fine-tuning pipeline.
These can be used in your ResearchLineage DAGs.

Example DAG structure:
    
    prepare_data >> upload_data >> launch_training >> [wait_for_completion] >> register_model

Each task is designed to be:
- Idempotent (can be retried safely)
- Observable (logs progress)
- DAG-friendly (returns XCom-compatible values)
"""
from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path
from typing import Dict, Any, Optional

# Setup path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logger = logging.getLogger(__name__)


def task_prepare_training_data(
    input_dir: Optional[str] = None,
    output_dir: Optional[str] = None,
    max_input_chars: int = 8000,
    max_output_chars: int = 4000,
    **context,
) -> Dict[str, Any]:
    """Airflow task: Prepare training data.
    
    Reads raw pipeline output, truncates to fit token limits,
    and saves prepared data locally.
    
    Args:
        input_dir: Path to raw data (default: pipeline_output/llama_format)
        output_dir: Path for prepared data (default: temporary/ft_data)
        max_input_chars: Maximum input length
        max_output_chars: Maximum output length
        context: Airflow context (optional)
        
    Returns:
        Dict with counts per split
    """
    from dotenv import load_dotenv
    load_dotenv()
    
    from temporary.ft_data_prep import prepare_dataset, DEFAULT_INPUT_DIR, DEFAULT_OUTPUT_DIR
    
    input_path = Path(input_dir) if input_dir else DEFAULT_INPUT_DIR
    output_path = Path(output_dir) if output_dir else DEFAULT_OUTPUT_DIR
    
    logger.info(f"Preparing training data: {input_path} -> {output_path}")
    
    stats = prepare_dataset(
        input_dir=input_path,
        output_dir=output_path,
        max_input_chars=max_input_chars,
        max_output_chars=max_output_chars,
    )
    
    logger.info(f"Prepared data: {stats}")
    return stats


def task_upload_to_gcs(
    local_dir: Optional[str] = None,
    **context,
) -> Dict[str, Any]:
    """Airflow task: Upload prepared data to GCS.
    
    Args:
        local_dir: Local directory with prepared data
        context: Airflow context (optional)
        
    Returns:
        Dict with uploaded URIs
    """
    from dotenv import load_dotenv
    load_dotenv()
    
    from temporary.ft_data_prep import upload_to_gcs, DEFAULT_OUTPUT_DIR
    from temporary.ft_custom_config import CustomTrainConfig
    
    cfg = CustomTrainConfig()
    local_path = Path(local_dir) if local_dir else DEFAULT_OUTPUT_DIR
    
    logger.info(f"Uploading data from {local_path}")
    
    uploaded = upload_to_gcs(local_path, cfg.ft_prefix)
    
    return {
        "uploaded_files": uploaded,
        "train_uri": cfg.train_data_uri(),
        "val_uri": cfg.val_data_uri(),
    }


def task_launch_training(
    epochs: int = 3,
    batch_size: int = 4,
    learning_rate: float = 2e-4,
    lora_r: int = 16,
    lora_alpha: int = 32,
    max_seq_length: int = 2048,
    machine_type: str = "g2-standard-12",
    accelerator_type: str = "NVIDIA_L4",
    accelerator_count: int = 1,
    wait: bool = True,
    **context,
) -> Dict[str, Any]:
    """Airflow task: Launch Vertex AI training job.
    
    Uses Model Garden with GCS-hosted weights.
    NO HuggingFace token required.
    
    Args:
        epochs: Training epochs
        batch_size: Batch size
        learning_rate: Learning rate
        lora_r: LoRA rank
        lora_alpha: LoRA alpha
        max_seq_length: Maximum sequence length
        machine_type: Compute machine type
        accelerator_type: GPU type
        accelerator_count: Number of GPUs
        wait: Whether to wait for completion (recommended for DAGs)
        context: Airflow context (optional)
        
    Returns:
        Dict with job info
    """
    from dotenv import load_dotenv
    load_dotenv()
    
    from temporary.ft_custom_job import launch_custom_training_job
    from temporary.ft_custom_config import CustomTrainConfig
    
    cfg = CustomTrainConfig()
    
    logger.info(f"Launching training job with epochs={epochs}, batch_size={batch_size}")
    
    job = launch_custom_training_job(
        epochs=epochs,
        batch_size=batch_size,
        learning_rate=learning_rate,
        lora_r=lora_r,
        lora_alpha=lora_alpha,
        max_seq_length=max_seq_length,
        machine_type=machine_type,
        accelerator_type=accelerator_type,
        accelerator_count=accelerator_count,
        wait_for_completion=wait,
    )
    
    # Extract job info for XCom
    timestamp = int(time.time())
    output_dir = f"{cfg.output_dir_uri()}/{timestamp}"
    
    return {
        "job_name": job.display_name if hasattr(job, 'display_name') else str(job),
        "job_resource": job.resource_name if hasattr(job, 'resource_name') else None,
        "output_dir": output_dir,
        "model_artifacts": f"{output_dir}/lora_adapter",
    }


def task_check_job_status(
    job_resource: str,
    **context,
) -> Dict[str, Any]:
    """Airflow task: Check training job status.
    
    Use this as a sensor if not waiting for completion in launch task.
    
    Args:
        job_resource: Job resource name from launch task
        context: Airflow context
        
    Returns:
        Dict with job status
    """
    from dotenv import load_dotenv
    load_dotenv()
    
    from temporary.ft_custom_job import get_job_status
    
    status = get_job_status(job_resource)
    
    # Raise exception if job failed (Airflow will mark task as failed)
    if "FAILED" in status.get("state", ""):
        raise RuntimeError(f"Training job failed: {status.get('error', 'Unknown error')}")
    
    return status


def task_register_model(
    model_artifacts_uri: str,
    model_display_name: Optional[str] = None,
    **context,
) -> Dict[str, Any]:
    """Airflow task: Register model in Vertex AI Model Registry.
    
    Args:
        model_artifacts_uri: GCS URI of model artifacts
        model_display_name: Display name for the model
        context: Airflow context
        
    Returns:
        Dict with registered model info
    """
    from dotenv import load_dotenv
    load_dotenv()
    
    from google.cloud import aiplatform
    from google.oauth2 import service_account
    from temporary.ft_custom_config import CustomTrainConfig
    
    cfg = CustomTrainConfig()
    
    credentials = service_account.Credentials.from_service_account_file(
        cfg.service_account_key,
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    
    aiplatform.init(
        project=cfg.project_id,
        location=cfg.region,
        credentials=credentials,
    )
    
    display_name = model_display_name or f"llama3-lora-{int(time.time())}"
    
    logger.info(f"Registering model: {display_name}")
    logger.info(f"Artifacts: {model_artifacts_uri}")
    
    # Upload model to registry
    model = aiplatform.Model.upload(
        display_name=display_name,
        artifact_uri=model_artifacts_uri,
        serving_container_image_uri="us-docker.pkg.dev/vertex-ai/prediction/pytorch-gpu.2-2:latest",
    )
    
    logger.info(f"Model registered: {model.resource_name}")
    
    return {
        "model_name": model.display_name,
        "model_resource": model.resource_name,
        "artifact_uri": model_artifacts_uri,
    }


# =============================================================================
# Example Airflow DAG (copy this to your dags/ folder)
# =============================================================================
"""
from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime, timedelta
import sys
sys.path.insert(0, '/path/to/ResearchLineage')

from temporary.ft_airflow_tasks import (
    task_prepare_training_data,
    task_upload_to_gcs,
    task_launch_training,
    task_register_model,
)

default_args = {
    'owner': 'mlops',
    'depends_on_past': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

with DAG(
    'llama3_lora_finetuning',
    default_args=default_args,
    description='Fine-tune Llama 3 with LoRA on Vertex AI',
    schedule_interval=None,  # Manual trigger
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=['mlops', 'finetuning', 'llama'],
) as dag:
    
    prepare_data = PythonOperator(
        task_id='prepare_training_data',
        python_callable=task_prepare_training_data,
        op_kwargs={
            'max_input_chars': 8000,
            'max_output_chars': 4000,
        },
    )
    
    upload_data = PythonOperator(
        task_id='upload_to_gcs',
        python_callable=task_upload_to_gcs,
    )
    
    train_model = PythonOperator(
        task_id='launch_training',
        python_callable=task_launch_training,
        op_kwargs={
            'epochs': 3,
            'batch_size': 4,
            'wait': True,  # Wait for completion
        },
    )
    
    register = PythonOperator(
        task_id='register_model',
        python_callable=task_register_model,
        op_kwargs={
            'model_artifacts_uri': "{{ ti.xcom_pull(task_ids='launch_training')['model_artifacts'] }}",
        },
    )
    
    prepare_data >> upload_data >> train_model >> register
"""
