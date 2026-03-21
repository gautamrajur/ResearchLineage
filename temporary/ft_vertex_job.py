"""Vertex AI Managed SFT: LoRA fine-tuning job launcher.

This is the MAIN file for launching LoRA fine-tuning jobs on Vertex AI.
All training runs on Google's infrastructure (not locally).

Features:
- Uses Vertex AI Managed SFT (no custom container needed)
- Supports LoRA via PEFT_ADAPTER tuning mode
- Models from GCP Model Garden (no HuggingFace token needed)
- Service Account authentication

IMPORTANT: Requires google-cloud-aiplatform >= 1.114.0 for open model tuning.
Run: pip install --upgrade google-cloud-aiplatform

Usage:
    # Launch a training job
    python -m temporary.ft_vertex_job --launch
    
    # Check job status
    python -m temporary.ft_vertex_job --status
    
    # Launch with custom settings
    python -m temporary.ft_vertex_job --launch --epochs 5
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path
from typing import Optional, Dict, Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def check_sdk_version():
    """Check if the SDK version supports open model tuning."""
    try:
        import google.cloud.aiplatform as aiplatform
        version = aiplatform.__version__
        major, minor, *_ = version.split(".")
        if int(major) < 1 or (int(major) == 1 and int(minor) < 114):
            logger.warning(f"SDK version {version} may not support all open model tuning features.")
            logger.warning("Consider upgrading: pip install --upgrade google-cloud-aiplatform")
        return version
    except Exception as e:
        logger.warning(f"Could not determine SDK version: {e}")
        return "unknown"


def launch_managed_sft_job(
    epochs: int = 3,
    tuning_mode: str = "PEFT_ADAPTER",
    wait_for_completion: bool = False,
) -> Any:
    """Launch a Vertex AI Managed SFT job for LoRA fine-tuning.
    
    This function submits a fine-tuning job to Vertex AI. The actual training
    happens entirely on Google's infrastructure using their GPUs.
    
    Args:
        epochs: Number of training epochs (default: 3)
        tuning_mode: "PEFT_ADAPTER" for LoRA or "FULL" for full fine-tuning
        wait_for_completion: If True, wait for job to finish
        
    Returns:
        The SFT tuning job object
    """
    # Check SDK version
    sdk_version = check_sdk_version()
    logger.info(f"google-cloud-aiplatform version: {sdk_version}")
    
    # Import here to avoid issues if vertexai not installed
    import vertexai
    from vertexai.tuning import sft
    from google.oauth2 import service_account
    
    # Try to import SourceModel (available in newer SDK versions)
    try:
        from vertexai.tuning import SourceModel
        has_source_model = True
    except ImportError:
        has_source_model = False
        logger.warning("SourceModel not available. Upgrade SDK: pip install --upgrade google-cloud-aiplatform")
    
    # Load configuration
    from temporary.ft_config import FineTuneConfig
    cfg = FineTuneConfig()
    
    # Setup credentials
    credentials = service_account.Credentials.from_service_account_file(
        cfg.service_account_key,
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    
    # Initialize Vertex AI
    vertexai.init(
        project=cfg.project_id,
        location=cfg.region,
        credentials=credentials,
    )
    
    logger.info("=" * 60)
    logger.info("Launching Vertex AI Managed SFT Job")
    logger.info("=" * 60)
    logger.info(f"Project: {cfg.project_id}")
    logger.info(f"Region: {cfg.region}")
    logger.info(f"Model: {cfg.model_name}")
    logger.info(f"Tuning Mode: {tuning_mode} {'(LoRA)' if tuning_mode == 'PEFT_ADAPTER' else '(Full)'}")
    logger.info(f"Epochs: {epochs}")
    logger.info(f"Training Data: {cfg.train_uri()}")
    logger.info(f"Output: {cfg.output_uri()}")
    logger.info("=" * 60)
    
    # Launch the tuning job
    logger.info("Submitting job to Vertex AI...")
    
    # Build the kwargs dynamically based on what the SDK supports
    train_kwargs = {
        "train_dataset": cfg.train_uri(),
        "tuned_model_display_name": f"llama3-lora-{int(time.time())}",
        "epochs": epochs,
    }
    
    # For Llama/open models, we need SourceModel, output_uri, and tuning_mode
    if has_source_model:
        train_kwargs["source_model"] = SourceModel(base_model=cfg.model_name)
        train_kwargs["output_uri"] = cfg.output_uri()
        train_kwargs["tuning_mode"] = tuning_mode
    else:
        # Fallback for older SDK - this likely won't work for Llama models
        train_kwargs["source_model"] = cfg.model_name
        logger.warning("Using legacy mode - may not work for open models like Llama")
    
    logger.info(f"Train kwargs: {train_kwargs}")
    
    sft_tuning_job = sft.train(**train_kwargs)
    
    logger.info("Job submitted successfully!")
    logger.info(f"Job resource name: {sft_tuning_job.resource_name}")
    
    if wait_for_completion:
        logger.info("Waiting for job to complete (this may take a while)...")
        while not sft_tuning_job.has_ended:
            logger.info(f"Job state: {sft_tuning_job.state}")
            time.sleep(60)
            sft_tuning_job.refresh()
        
        if sft_tuning_job.has_succeeded:
            logger.info("=" * 60)
            logger.info("Job completed successfully!")
            logger.info(f"Tuned model: {sft_tuning_job.tuned_model_name}")
            logger.info(f"Tuned model endpoint: {sft_tuning_job.tuned_model_endpoint_name}")
            logger.info("=" * 60)
        else:
            logger.error(f"Job failed with state: {sft_tuning_job.state}")
            if sft_tuning_job.error:
                logger.error(f"Error: {sft_tuning_job.error}")
    else:
        logger.info("")
        logger.info("Job is running in the background.")
        logger.info("Check status with: python -m temporary.ft_vertex_job --status")
        logger.info(f"Or visit: https://console.cloud.google.com/vertex-ai/tuning?project={cfg.project_id}")
    
    return sft_tuning_job


def list_tuning_jobs() -> None:
    """List all tuning jobs in the project."""
    import vertexai
    from vertexai.tuning import sft
    from google.oauth2 import service_account
    
    from temporary.ft_config import FineTuneConfig
    cfg = FineTuneConfig()
    
    credentials = service_account.Credentials.from_service_account_file(
        cfg.service_account_key,
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    
    vertexai.init(
        project=cfg.project_id,
        location=cfg.region,
        credentials=credentials,
    )
    
    logger.info(f"Fetching tuning jobs for project: {cfg.project_id}")
    
    jobs = sft.SupervisedTuningJob.list()
    
    print("\n" + "=" * 80)
    print("Tuning Jobs")
    print("=" * 80)
    
    for job in jobs:
        print(f"\nJob: {job.resource_name}")
        print(f"  State: {job.state}")
        print(f"  Created: {job.create_time}")
        if job.has_ended:
            print(f"  Ended: {job.end_time}")
        if job.tuned_model_name:
            print(f"  Tuned Model: {job.tuned_model_name}")
        if job.tuned_model_endpoint_name:
            print(f"  Endpoint: {job.tuned_model_endpoint_name}")


def get_job_status(job_name: Optional[str] = None) -> Dict[str, Any]:
    """Get status of a specific job or the most recent job.
    
    Args:
        job_name: Full resource name of the job (optional)
        
    Returns:
        Job status dictionary
    """
    import vertexai
    from vertexai.tuning import sft
    from google.oauth2 import service_account
    
    from temporary.ft_config import FineTuneConfig
    cfg = FineTuneConfig()
    
    credentials = service_account.Credentials.from_service_account_file(
        cfg.service_account_key,
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    
    vertexai.init(
        project=cfg.project_id,
        location=cfg.region,
        credentials=credentials,
    )
    
    if job_name:
        job = sft.SupervisedTuningJob(job_name)
    else:
        # Get the most recent job
        jobs = list(sft.SupervisedTuningJob.list())
        if not jobs:
            print("No tuning jobs found.")
            return {}
        job = jobs[0]
    
    job.refresh()
    
    status = {
        "resource_name": job.resource_name,
        "state": str(job.state),
        "create_time": str(job.create_time),
        "has_ended": job.has_ended,
        "has_succeeded": job.has_succeeded,
    }
    
    if job.tuned_model_name:
        status["tuned_model_name"] = job.tuned_model_name
    if job.tuned_model_endpoint_name:
        status["tuned_model_endpoint_name"] = job.tuned_model_endpoint_name
    if job.error:
        status["error"] = str(job.error)
    
    print("\n" + "=" * 60)
    print("Job Status")
    print("=" * 60)
    for key, value in status.items():
        print(f"  {key}: {value}")
    print("=" * 60)
    
    return status


def main():
    """Main entry point for CLI."""
    parser = argparse.ArgumentParser(
        description="Vertex AI Managed SFT for Llama 3 LoRA fine-tuning"
    )
    
    parser.add_argument(
        "--launch",
        action="store_true",
        help="Launch a new fine-tuning job"
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Check status of the most recent job"
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all tuning jobs"
    )
    parser.add_argument(
        "--epochs",
        type=int,
        default=3,
        help="Number of training epochs (default: 3)"
    )
    parser.add_argument(
        "--tuning-mode",
        type=str,
        default="PEFT_ADAPTER",
        choices=["PEFT_ADAPTER", "FULL"],
        help="Tuning mode: PEFT_ADAPTER (LoRA) or FULL (default: PEFT_ADAPTER)"
    )
    parser.add_argument(
        "--wait",
        action="store_true",
        help="Wait for job to complete"
    )
    parser.add_argument(
        "--config",
        action="store_true",
        help="Show current configuration"
    )
    parser.add_argument(
        "--check-version",
        action="store_true",
        help="Check SDK version"
    )
    
    args = parser.parse_args()
    
    if args.check_version:
        check_sdk_version()
    elif args.config:
        from temporary.ft_config import FineTuneConfig
        cfg = FineTuneConfig()
        print(cfg)
    elif args.launch:
        launch_managed_sft_job(
            epochs=args.epochs,
            tuning_mode=args.tuning_mode,
            wait_for_completion=args.wait,
        )
    elif args.status:
        get_job_status()
    elif args.list:
        list_tuning_jobs()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
