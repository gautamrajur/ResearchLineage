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

    # ------------------------------------------------------- Modal (inference)
    modal_endpoint_url: str = Field(
        default="",
        description="Modal web endpoint URL for inference (custom JSON prompt/text). "
        "Ignored if OpenAI-compatible settings are set. "
        "When set, ModalClient is used instead of Vertex AI for inference. "
        "e.g. https://nekkantishiv--researchlineage-qwen-qwenmodel-infer.modal.run",
    )

    # -------------------------------------------- OpenAI-compatible API (inference)
    openai_base_url: str = Field(
        default="",
        description="OpenAI-compatible API base URL including /v1 if required by the server. "
        "When set together with openai_model, OpenAICompatibleClient is used (highest priority). "
        "e.g. https://user--app-name.modal.run/v1",
    )
    openai_api_key: str = Field(
        default="dummy",
        description="API key for the OpenAI-compatible endpoint (often unused by Modal; use dummy).",
    )
    openai_model: str = Field(
        default="",
        description="Model id passed to chat.completions, e.g. /model-cache/v20260320_184258",
    )
    openai_max_tokens: int = Field(
        default=8192,
        description="Max completion tokens for OpenAI-compatible inference.",
    )
    openai_timeout: float = Field(
        default=600.0,
        description="Per-request timeout in seconds for OpenAI-compatible inference.",
    )
    openai_temperature: float = Field(
        default=0.0,
        description="Sampling temperature for OpenAI-compatible inference.",
    )
    openai_max_retries: int = Field(
        default=0,
        description="Retries on the OpenAI SDK client (0 = fail fast).",
    )

    inference_model_name: str = Field(
        default="unknown",
        description="Human-readable model name stamped on GCS output paths. "
        "e.g. qwen2.5-7b, llama-3.1-8b, mistral-7b",
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