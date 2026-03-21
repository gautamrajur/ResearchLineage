"""Vertex AI Custom Training Job Launcher.

Uses Application Default Credentials (ADC) — no service account key file.

Before running:
    gcloud auth application-default login

Usage:
    python -m temporary.ft_custom_job --launch
    python -m temporary.ft_custom_job --launch --wait
    python -m temporary.ft_custom_job --launch --epochs 5
    python -m temporary.ft_custom_job --status JOB_RESOURCE_NAME
    python -m temporary.ft_custom_job --list
    python -m temporary.ft_custom_job --config
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def launch_custom_training_job(
    epochs: int = 3,
    batch_size: int = 4,
    learning_rate: float = 2e-4,
    lora_r: int = 16,
    lora_alpha: int = 32,
    max_seq_length: int = 2048,
    machine_type: str = "g2-standard-12",
    accelerator_type: str = "NVIDIA_L4",
    accelerator_count: int = 1,
    use_4bit: bool = True,
    wait_for_completion: bool = False,
) -> Any:
    """Submit a Vertex AI CustomJob that runs the custom training container.

    The job:
      1. Pulls the Docker image from Artifact Registry
      2. Mounts the GCS bucket via /gcs/ FUSE
      3. Reads model weights from /gcs/<bucket>/<model-path>
      4. Reads training data from /gcs/<bucket>/<ft-prefix>/train.jsonl
      5. Saves model artifacts to /gcs/<bucket>/<upload-prefix>/...

    Authentication: ADC — no GOOGLE_APPLICATION_CREDENTIALS needed.
    """
    from google.cloud import aiplatform
    from temporary.ft_custom_config import CustomTrainConfig

    cfg = CustomTrainConfig()

    # ADC: aiplatform.init() will use application default credentials automatically
    aiplatform.init(
        project=cfg.project_id,
        location=cfg.region,
        staging_bucket=cfg.staging_bucket_uri(),
    )

    timestamp = int(time.time())
    job_display_name = f"llama3-lora-custom-{timestamp}"
    output_gcs = f"{cfg.output_dir_uri()}/{timestamp}"

    # All paths passed as gs:// URIs; the training script converts to /gcs/ internally
    training_args = [
        f"--train-data={cfg.train_data_uri()}",
        f"--output-dir={output_gcs}",
        f"--model-path={cfg.base_model_uri}",
        f"--epochs={epochs}",
        f"--batch-size={batch_size}",
        f"--learning-rate={learning_rate}",
        f"--lora-r={lora_r}",
        f"--lora-alpha={lora_alpha}",
        f"--max-length={max_seq_length}",
    ]
    if use_4bit:
        training_args.append("--use-4bit")

    # Environment variables set inside the container
    env_vars = [
        # Cache HuggingFace downloads to GCS so they survive container restarts
        {"name": "TRANSFORMERS_CACHE", "value": f"/gcs/{cfg.bucket}/hf_cache"},
        {"name": "HF_HOME",            "value": f"/gcs/{cfg.bucket}/hf_cache"},
        {"name": "PYTHONUNBUFFERED",   "value": "1"},
    ]

    logger.info("=" * 60)
    logger.info("Launching Vertex AI Custom Training Job")
    logger.info("=" * 60)
    logger.info("Job:          %s", job_display_name)
    logger.info("Project:      %s", cfg.project_id)
    logger.info("Region:       %s", cfg.region)
    logger.info("Image:        %s", cfg.artifact_registry_image())
    logger.info("Model (GCS):  %s", cfg.base_model_uri)
    logger.info("Train data:   %s", cfg.train_data_uri())
    logger.info("Output:       %s", output_gcs)
    logger.info("Machine:      %s + %dx %s", machine_type, accelerator_count, accelerator_type)
    logger.info("Auth:         Application Default Credentials (ADC)")
    logger.info("=" * 60)
    logger.info("Hyperparameters:")
    logger.info("  epochs=%d  batch_size=%d  lr=%g  4bit=%s",
                epochs, batch_size, learning_rate, use_4bit)
    logger.info("  lora_r=%d  lora_alpha=%d  max_seq_length=%d",
                lora_r, lora_alpha, max_seq_length)
    logger.info("=" * 60)

    job = aiplatform.CustomJob(
        display_name=job_display_name,
        worker_pool_specs=[
            {
                "machine_spec": {
                    "machine_type": machine_type,
                    "accelerator_type": accelerator_type,
                    "accelerator_count": accelerator_count,
                },
                "replica_count": 1,
                "container_spec": {
                    # ENTRYPOINT in Dockerfile.custom: ["python", "ft_custom_train.py"]
                    # training_args are appended as argv
                    "image_uri": cfg.artifact_registry_image(),
                    "args": training_args,
                    "env": env_vars,
                },
            }
        ],
    )

    if wait_for_completion:
        logger.info("Waiting for job to complete (this may take hours)...")
        job.run(sync=True)
        logger.info("Job completed!")
        logger.info("Model artifacts: %s", output_gcs)
    else:
        job.submit()
        logger.info("Job submitted!")
        logger.info("Resource: %s", job.resource_name)
        logger.info("")
        logger.info("Monitor:")
        logger.info(
            "  python -m temporary.ft_custom_job --status %s", job.resource_name
        )
        logger.info(
            "  https://console.cloud.google.com/vertex-ai/training/custom-jobs?project=%s",
            cfg.project_id,
        )

    return job


def list_custom_jobs(limit: int = 10) -> List[Dict[str, Any]]:
    """List recent llama3-lora custom training jobs."""
    from google.cloud import aiplatform
    from temporary.ft_custom_config import CustomTrainConfig

    cfg = CustomTrainConfig()
    aiplatform.init(project=cfg.project_id, location=cfg.region)

    jobs = aiplatform.CustomJob.list(
        filter='display_name:"llama3-lora"',
        order_by="create_time desc",
    )

    print("\n" + "=" * 80)
    print("Recent Custom Training Jobs")
    print("=" * 80)

    job_list = []
    for i, job in enumerate(jobs):
        if i >= limit:
            break
        info = {
            "name": job.display_name,
            "resource_name": job.resource_name,
            "state": str(job.state),
            "create_time": str(job.create_time),
        }
        job_list.append(info)
        print(f"\n{job.display_name}")
        print(f"  State:    {job.state}")
        print(f"  Created:  {job.create_time}")
        print(f"  Resource: {job.resource_name}")

    return job_list


def get_job_status(job_resource_name: str) -> Dict[str, Any]:
    """Get the status of a specific custom job."""
    from google.cloud import aiplatform
    from temporary.ft_custom_config import CustomTrainConfig

    cfg = CustomTrainConfig()
    aiplatform.init(project=cfg.project_id, location=cfg.region)

    job = aiplatform.CustomJob(resource_name=job_resource_name)

    status: Dict[str, Any] = {
        "name": job.display_name,
        "resource_name": job.resource_name,
        "state": str(job.state),
        "create_time": str(job.create_time),
    }
    if job.end_time:
        status["end_time"] = str(job.end_time)
    if job.error:
        status["error"] = str(job.error)

    print("\n" + "=" * 60)
    print("Job Status")
    print("=" * 60)
    for k, v in status.items():
        print(f"  {k}: {v}")

    return status


def main():
    parser = argparse.ArgumentParser(
        description="Launch / monitor Vertex AI Custom Training for Llama 3 LoRA"
    )

    # Actions
    parser.add_argument("--launch", action="store_true", help="Launch a training job")
    parser.add_argument("--status", type=str, metavar="RESOURCE_NAME",
                        help="Get job status")
    parser.add_argument("--list", action="store_true", help="List recent jobs")
    parser.add_argument("--config", action="store_true", help="Print configuration")

    # Training parameters
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--learning-rate", type=float, default=2e-4)
    parser.add_argument("--lora-r", type=int, default=16)
    parser.add_argument("--lora-alpha", type=int, default=32)
    parser.add_argument("--max-seq-length", type=int, default=2048)

    # Infrastructure
    parser.add_argument("--machine-type", type=str, default="g2-standard-12")
    parser.add_argument("--accelerator-type", type=str, default="NVIDIA_L4")
    parser.add_argument("--accelerator-count", type=int, default=1)

    # Options
    parser.add_argument("--wait", action="store_true",
                        help="Block until job completes")
    parser.add_argument("--no-4bit", action="store_true",
                        help="Disable 4-bit QLoRA (uses bfloat16 instead)")

    args = parser.parse_args()

    if args.config:
        from temporary.ft_custom_config import CustomTrainConfig
        print(CustomTrainConfig())
    elif args.launch:
        launch_custom_training_job(
            epochs=args.epochs,
            batch_size=args.batch_size,
            learning_rate=args.learning_rate,
            lora_r=args.lora_r,
            lora_alpha=args.lora_alpha,
            max_seq_length=args.max_seq_length,
            machine_type=args.machine_type,
            accelerator_type=args.accelerator_type,
            accelerator_count=args.accelerator_count,
            use_4bit=not args.no_4bit,
            wait_for_completion=args.wait,
        )
    elif args.status:
        get_job_status(args.status)
    elif args.list:
        list_custom_jobs()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
