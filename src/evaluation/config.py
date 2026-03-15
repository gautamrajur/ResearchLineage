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

    # ------------------------------------------------------------------ GCS
    gcs_input_path: str = Field(
        ...,
        description="GCS URI for evaluation input data. "
        "e.g. gs://my-bucket/eval/inputs/",
    )
    gcs_output_path: str = Field(
        ...,
        description="GCS URI where results are written. "
        "e.g. gs://my-bucket/eval/outputs/",
    )
    gcs_project_id: str = Field(
        ...,
        description="GCP project ID for GCS authentication.",
    )

    # --------------------------------------------------------- Vertex AI (inference)
    vertex_endpoint_id: str = Field(
        ...,
        description="Vertex AI endpoint ID of the fine-tuned model under evaluation.",
    )
    vertex_location: str = Field(
        default="us-central1",
        description="GCP region for the Vertex AI inference endpoint.",
    )

    # --------------------------------------------------------- Vertex AI (judge)
    judge_endpoint_id: str = Field(
        ...,
        description="Vertex AI endpoint ID of the LLM judge model.",
    )
    judge_location: str = Field(
        default="us-central1",
        description="GCP region for the Vertex AI judge endpoint.",
    )
    judge_max_output_tokens: int = Field(
        default=1024,
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
