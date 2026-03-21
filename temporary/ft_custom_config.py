"""Configuration for Custom Container Training on Vertex AI with Model Garden.

Authentication: Application Default Credentials (ADC).
Run locally:  gcloud auth application-default login
Inside Vertex AI container: credentials are injected automatically.

Required environment variables:
    GCS_PROJECT_ID          GCP project ID
    GCS_BUCKET_NAME         GCS bucket name
    GCS_FT_PREFIX           Prefix for training data (e.g. finetuning/data)
    GCS_UPLOAD_MODEL_ARTIFACTS_PREFIX       Prefix for output artifacts (e.g. finetuning/output)
    MODEL_GARDEN_GCS_URI    Full gs:// path to Model Garden weights
                            e.g. gs://vertex-model-garden-public-us-central1/llama3_1/llama-3.1-8b-instruct

Optional:
    VERTEX_REGION           GCP region (default: us-central1)
    ARTIFACT_REGISTRY_REPO  Artifact Registry repo name (default: training)
"""
from dataclasses import dataclass, field
from typing import Optional, List
import os


# Known model weight paths.
# Llama 3.x weights are no longer in the public bucket — they require license
# acceptance and are accessed via a private restricted bucket, or copied to
# your own bucket (recommended approach).
KNOWN_MODEL_GARDEN_URIS = {
    "llama-3-8b-instruct":
        "gs://researchlineage-gcs/models/llama-3-8b-instruct",
    "llama-2-7b":
        "gs://vertex-model-garden-public-us-central1/llama2/llama-2-7b",
    "llama-2-7b-chat":
        "gs://vertex-model-garden-public-us-central1/llama2/llama-2-7b-chat",
}


@dataclass
class CustomTrainConfig:
    """Configuration for Vertex AI Custom Container Training.

    Uses ADC — no service account key file required.
    """

    # GCP settings
    project_id: Optional[str] = None
    region: str = "us-central1"
    bucket: Optional[str] = None
    ft_prefix: str = ""
    upload_prefix: str = ""

    # Model — GCS URI to Model Garden weights (/gcs/ FUSE mount is used inside container)
    base_model_uri: Optional[str] = None

    # Artifact Registry repo (image is pushed here before submitting the job)
    artifact_registry_repo: str = "training"

    # LoRA settings
    lora_r: int = 16
    lora_alpha: int = 32
    lora_dropout: float = 0.05
    lora_target_modules: List[str] = field(default_factory=lambda: [
        "q_proj", "k_proj", "v_proj", "o_proj",
        "gate_proj", "up_proj", "down_proj",
    ])

    # Training hyperparameters
    epochs: int = 3
    batch_size: int = 4
    gradient_accumulation_steps: int = 4
    learning_rate: float = 2e-4
    warmup_ratio: float = 0.03
    weight_decay: float = 0.01
    max_seq_length: int = 2048

    # Data settings
    max_input_chars: int = 8000
    max_output_chars: int = 4000

    # Training infrastructure
    machine_type: str = "g2-standard-12"   # 1x L4 24 GB
    accelerator_type: str = "NVIDIA_L4"
    accelerator_count: int = 1

    def __post_init__(self):
        if self.project_id is None:
            self.project_id = os.getenv("GCS_PROJECT_ID")
        if not self.project_id:
            raise ValueError("GCS_PROJECT_ID must be set")

        self.region = os.getenv("VERTEX_REGION", self.region)

        if self.bucket is None:
            self.bucket = os.getenv("GCS_BUCKET_NAME")
        if not self.bucket:
            raise ValueError("GCS_BUCKET_NAME must be set")

        self.ft_prefix = (os.getenv("GCS_FT_PREFIX") or self.ft_prefix).strip("/")
        self.upload_prefix = (os.getenv("GCS_UPLOAD_MODEL_ARTIFACTS_PREFIX") or self.upload_prefix).strip("/")

        self.artifact_registry_repo = os.getenv(
            "ARTIFACT_REGISTRY_REPO", self.artifact_registry_repo
        )

        if self.base_model_uri is None:
            self.base_model_uri = os.getenv("MODEL_GARDEN_GCS_URI")
        if not self.base_model_uri:
            raise ValueError(
                "MODEL_GARDEN_GCS_URI must be set to the gs:// path of the model weights.\n"
                "Known paths:\n"
                + "\n".join(f"  {k}: {v}" for k, v in KNOWN_MODEL_GARDEN_URIS.items())
            )

    # ── GCS URIs ──────────────────────────────────────────────────────

    def train_data_uri(self) -> str:
        base = f"gs://{self.bucket}"
        return f"{base}/{self.ft_prefix}/train.jsonl" if self.ft_prefix else f"{base}/train.jsonl"

    def val_data_uri(self) -> str:
        base = f"gs://{self.bucket}"
        return f"{base}/{self.ft_prefix}/val.jsonl" if self.ft_prefix else f"{base}/val.jsonl"

    def output_dir_uri(self) -> str:
        base = f"gs://{self.bucket}"
        return (
            f"{base}/{self.upload_prefix}/custom_training_output"
            if self.upload_prefix
            else f"{base}/custom_training_output"
        )

    def staging_bucket_uri(self) -> str:
        return f"gs://{self.bucket}/vertex_staging"

    # ── Artifact Registry ─────────────────────────────────────────────

    def artifact_registry_image(self, tag: str = "latest") -> str:
        """Full Artifact Registry image path."""
        return (
            f"{self.region}-docker.pkg.dev/{self.project_id}"
            f"/{self.artifact_registry_repo}/llama3-lora:{tag}"
        )

    def __repr__(self) -> str:
        return (
            f"CustomTrainConfig(\n"
            f"  project_id='{self.project_id}',\n"
            f"  region='{self.region}',\n"
            f"  bucket='{self.bucket}',\n"
            f"  base_model_uri='{self.base_model_uri}',\n"
            f"  lora_r={self.lora_r}, lora_alpha={self.lora_alpha},\n"
            f"  epochs={self.epochs}, batch_size={self.batch_size},\n"
            f"  max_seq_length={self.max_seq_length},\n"
            f"  machine_type='{self.machine_type}',\n"
            f"  train_data='{self.train_data_uri()}',\n"
            f"  output_dir='{self.output_dir_uri()}'\n"
            f")"
        )
