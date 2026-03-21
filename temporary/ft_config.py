"""Central configuration for Llama 3 LoRA fine-tuning on Vertex AI.

This module provides configuration management for LoRA fine-tuning using
Vertex AI Managed SFT (Supervised Fine-Tuning).

Key Points:
- All training runs on Vertex AI (not locally)
- Uses Model Garden models (no HuggingFace token needed)
- Uses LoRA via PEFT_ADAPTER tuning mode
- Training data must be in GCS bucket

Authentication: Uses Service Account credentials via GOOGLE_APPLICATION_CREDENTIALS.
"""
from dataclasses import dataclass
from typing import Optional
import os


@dataclass
class FineTuneConfig:
    """Fine-tuning configuration for Vertex AI Managed SFT.
    
    This configuration is used to submit LoRA fine-tuning jobs to Vertex AI.
    All training happens on Google's infrastructure, not locally.
    
    Environment Variables Required:
        GCS_PROJECT_ID: GCP project ID
        GCS_BUCKET_NAME: GCS bucket name for data/artifacts
        GCS_FT_PREFIX: Prefix for training data in bucket
        GCS_UPLOAD_PREFIX: Prefix for output artifacts
        LLAMA3_MODEL_ID: Model Garden model ID (e.g., "meta/llama3_1@llama-3.1-8b")
        GOOGLE_APPLICATION_CREDENTIALS: Path to service account JSON key
        
    Optional Environment Variables:
        VERTEX_REGION: GCP region (default: us-central1)
    """

    project_id: Optional[str] = None
    region: str = "us-central1"
    bucket: Optional[str] = None
    ft_prefix: str = ""
    upload_prefix: str = ""
    
    # Base model from Model Garden
    # Supported: meta/llama3_1@llama-3.1-8b, meta/llama3_1@llama-3.1-8b-instruct, etc.
    model_name: Optional[str] = None
    
    # Tuning mode: PEFT_ADAPTER (LoRA) or FULL
    tuning_mode: str = "PEFT_ADAPTER"
    
    # Training hyperparameters
    epochs: int = 3
    learning_rate_multiplier: float = 1.0
    
    # Service account credentials path
    service_account_key: Optional[str] = None

    def __post_init__(self):
        """Load configuration from environment variables."""
        # Project and region
        if self.project_id is None:
            self.project_id = os.getenv("GCS_PROJECT_ID")
        if not self.project_id:
            raise ValueError("GCS_PROJECT_ID environment variable must be set.")
            
        self.region = os.getenv("VERTEX_REGION", self.region)
        
        # Validate region - Managed SFT only supports specific regions
        supported_regions = ["us-central1", "europe-west4"]
        if self.region not in supported_regions:
            raise ValueError(
                f"Region '{self.region}' is not supported for Managed SFT. "
                f"Supported regions: {supported_regions}"
            )
        
        # GCS bucket configuration
        if self.bucket is None:
            self.bucket = os.getenv("GCS_BUCKET_NAME")
        if not self.bucket:
            raise ValueError("GCS_BUCKET_NAME environment variable must be set.")
            
        self.ft_prefix = (os.getenv("GCS_FT_PREFIX") or self.ft_prefix).strip("/")
        self.upload_prefix = (os.getenv("GCS_UPLOAD_PREFIX") or self.upload_prefix).strip("/")
        
        # Model configuration
        if self.model_name is None:
            self.model_name = os.getenv("LLAMA3_MODEL_ID")
        if not self.model_name:
            raise ValueError(
                "LLAMA3_MODEL_ID must be set to a Vertex Model Garden ID. "
                "Supported models:\n"
                "  - meta/llama3_1@llama-3.1-8b\n"
                "  - meta/llama3_1@llama-3.1-8b-instruct\n"
                "  - meta/llama3-2@llama-3.2-1b-instruct\n"
                "  - meta/llama3-2@llama-3.2-3b-instruct\n"
                "  - meta/llama3-3@llama-3.3-70b-instruct"
            )
        
        # Service account credentials
        self.service_account_key = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        if not self.service_account_key:
            raise ValueError(
                "GOOGLE_APPLICATION_CREDENTIALS environment variable must be set "
                "to the path of your service account JSON key file."
            )
        
        if not os.path.isfile(self.service_account_key):
            raise FileNotFoundError(
                f"Service account key file not found: {self.service_account_key}"
            )

    def train_uri(self) -> str:
        """GCS URI for training data (train.jsonl)."""
        if self.ft_prefix:
            return f"gs://{self.bucket}/{self.ft_prefix}/train.jsonl"
        return f"gs://{self.bucket}/train.jsonl"

    def output_uri(self, subdir: str = "llama3_lora_output") -> str:
        """GCS URI for training output.
        
        After training completes, the fine-tuned model artifacts will be at:
        {output_uri}/postprocess/node-0/checkpoints/final
        """
        if self.upload_prefix:
            return f"gs://{self.bucket}/{self.upload_prefix}/{subdir}"
        return f"gs://{self.bucket}/{subdir}"

    def __repr__(self) -> str:
        return (
            f"FineTuneConfig(\n"
            f"  project_id='{self.project_id}',\n"
            f"  region='{self.region}',\n"
            f"  bucket='{self.bucket}',\n"
            f"  model_name='{self.model_name}',\n"
            f"  tuning_mode='{self.tuning_mode}',\n"
            f"  epochs={self.epochs},\n"
            f"  train_uri='{self.train_uri()}',\n"
            f"  output_uri='{self.output_uri()}'\n"
            f")"
        )
