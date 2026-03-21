"""Deploy fine-tuned model to Vertex AI endpoint.

Uses Application Default Credentials (ADC) — no service account key file.

Before running:
    gcloud auth application-default login

Usage:
    python -m temporary.ft_deploy_vertex --deploy MODEL_RESOURCE_NAME
    python -m temporary.ft_deploy_vertex --list-endpoints
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv()

from google.cloud import aiplatform

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def _init_vertex():
    """Initialise Vertex AI using ADC."""
    from temporary.ft_custom_config import CustomTrainConfig
    cfg = CustomTrainConfig()
    aiplatform.init(project=cfg.project_id, location=cfg.region)
    return cfg


def deploy_tuned_model(
    model_name: str,
    endpoint_display_name: str = "llama3-lora-endpoint",
    machine_type: str = "g2-standard-12",
    accelerator_type: str = "NVIDIA_L4",
    accelerator_count: int = 1,
) -> aiplatform.Endpoint:
    """Deploy a registered model to a Vertex AI endpoint.

    Args:
        model_name: Model resource name (from Vertex AI Model Registry)
        endpoint_display_name: Display name for the new endpoint
        machine_type: Compute machine type
        accelerator_type: GPU type
        accelerator_count: Number of GPUs

    Returns:
        Deployed endpoint
    """
    _init_vertex()

    logger.info("Deploying model: %s", model_name)

    model = aiplatform.Model(model_name=model_name)
    endpoint = model.deploy(
        deployed_model_display_name=endpoint_display_name,
        machine_type=machine_type,
        accelerator_type=accelerator_type,
        accelerator_count=accelerator_count,
        traffic_percentage=100,
    )

    logger.info("Model deployed to: %s", endpoint.resource_name)
    return endpoint


def list_endpoints() -> None:
    """List all Vertex AI endpoints in the project."""
    _init_vertex()

    endpoints = aiplatform.Endpoint.list()
    print("\n" + "=" * 70)
    print("Vertex AI Endpoints")
    print("=" * 70)
    for ep in endpoints:
        print(f"\n{ep.display_name}")
        print(f"  Resource: {ep.resource_name}")


def main():
    parser = argparse.ArgumentParser(
        description="Deploy fine-tuned Llama 3 models to Vertex AI"
    )
    parser.add_argument("--deploy", type=str,
                        help="Model resource name to deploy")
    parser.add_argument("--list-endpoints", action="store_true",
                        help="List all endpoints")
    parser.add_argument("--endpoint-name", type=str,
                        default="llama3-lora-endpoint")
    parser.add_argument("--machine-type", type=str, default="g2-standard-12")
    parser.add_argument("--accelerator-type", type=str, default="NVIDIA_L4")
    parser.add_argument("--accelerator-count", type=int, default=1)

    args = parser.parse_args()

    if args.deploy:
        deploy_tuned_model(
            model_name=args.deploy,
            endpoint_display_name=args.endpoint_name,
            machine_type=args.machine_type,
            accelerator_type=args.accelerator_type,
            accelerator_count=args.accelerator_count,
        )
    elif args.list_endpoints:
        list_endpoints()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
