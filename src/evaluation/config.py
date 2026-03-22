# src/evaluation/config.py
from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings


class EvaluationConfig(BaseSettings):
    """
    All evaluation pipeline settings.
    Override via environment variables or a .env file.

    Env var naming: EVAL_<FIELD_NAME_UPPER>
    e.g. EVAL_GCS_INPUT_PATH, EVAL_VERTEX_ENDPOINT_ID
    """

    model_config = {"env_prefix": "EVAL_", "env_file": ".env", "extra": "ignore"}

    # ------------------------------------------------------------------ Input source
    finetuning_data_source: str = Field(
        default="local",
        description="Where to load evaluation input data from: 'local' or 'gcs'.",
    )
    finetuning_data_gcs_path: str = Field(
        default="",
        description="GCS URI for evaluation input data (used when finetuning_data_source='gcs'). "
        "e.g. gs://my-bucket/eval/inputs/test.jsonl",
    )

    # ------------------------------------------------------------------ GCS (output + auth)
    gcs_output_path: str = Field(
        default="",
        description="GCS URI where results are written. "
        "e.g. gs://my-bucket/eval/outputs/",
    )
    gcs_project_id: str = Field(
        default="",
        description="GCP project ID for GCS authentication.",
    )

    # --------------------------------------------------------- Vertex AI (inference)
    vertex_project_id: str = Field(
        default="",
        description="GCP project ID where the inference endpoint is deployed. "
        "Defaults to gcs_project_id if empty.",
    )
    vertex_endpoint_id: str = Field(
        default="",
        description="Vertex AI endpoint ID of the fine-tuned model under evaluation. "
        "Not required when using Modal for inference.",
    )
    vertex_location: str = Field(
        default="us-central1",
        description="GCP region for the Vertex AI inference endpoint.",
    )

    # ---------------------------------------------------------------- Inference model endpoint
    model_endpoint: str = Field(
        default="",
        description="Model endpoint for inference. Routing rules: "
        "  'gemini-*'   → GeminiClient (managed Vertex AI Gemini API); "
        "  'http*'      → ModalClient (Modal web endpoint URL); "
        "  anything else → VertexAIClient (Vertex AI endpoint ID). "
        "e.g. 'gemini-2.5-pro', 'https://...modal.run', '1234567890'",
    )
    inference_model_name: str = Field(
        default="unknown",
        description="Human-readable model name stamped on GCS output paths. "
        "Defaults to model_endpoint value if not set explicitly.",
    )

    # --------------------------------------------------------- Vertex AI (judge)
    judge_project_id: str = Field(
        default="",
        description="GCP project ID for the judge model. "
        "Defaults to gcs_project_id if empty.",
    )
    judge_endpoint_id: str = Field(
        default="",
        description="Vertex AI endpoint ID for a custom judge model. "
        "Leave empty to use the Gemini managed API instead.",
    )
    judge_location: str = Field(
        default="us-central1",
        description="GCP region for the Vertex AI judge endpoint.",
    )
    judge_max_output_tokens: int = Field(
        default=2048,
        description="Max tokens for judge responses.",
    )
    judge_temperature: float = Field(
        default=0.0,
        description="Temperature for judge calls — keep at 0 for determinism.",
    )
    judge_model_name: str = Field(
        default="gemini-2.5-flash",
        description="Gemini model name for judge when not using a custom endpoint.",
    )

    # ------------------------------------------------------- Evaluation behaviour
    max_workers: int = Field(
        default=4,
        description="Concurrent workers for inference and judge calls.",
    )
    inference_batch_size: int = Field(
        default=8,
        description="Number of samples per inference batch.",
    )
    semantic_model_name: str = Field(
        default="all-MiniLM-L6-v2",
        description="Sentence-transformers model for BERTScore-style semantic similarity.",
    )
    run_id: str = Field(
        default="",
        description="Optional run identifier stamped on all output files. "
        "Auto-generated from timestamp if empty.",
    )

    # ------------------------------------------------------- Local input (no GCS)
    local_input_path: str = Field(
        default="",
        description="Local filesystem path to a split JSONL file "
        "(e.g. lineage_llama_format/test.jsonl). "
        "Used when finetuning_data_source='local'. "
        "The paired metadata file is expected at the same directory with "
        "the name <split>_metadata_fixed.jsonl.",
    )