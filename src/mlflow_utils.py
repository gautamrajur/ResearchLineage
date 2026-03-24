"""MLflow experiment tracking utilities for ResearchLineage."""

from __future__ import annotations

import logging
import os
from typing import Any

import mlflow
from mlflow.tracking import MlflowClient

from src.utils.config import MLFLOW_EXPERIMENT_NAME, MLFLOW_MODEL_NAME, MLFLOW_TRACKING_URI

logger = logging.getLogger(__name__)


def _ensure_tracking_uri() -> None:
    """Set MLflow tracking URI from config if not already set."""
    current = os.environ.get("MLFLOW_TRACKING_URI", "")
    if not current:
        mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)


def get_or_create_experiment(name: str | None = None) -> str:
    """Get or create an MLflow experiment, returning its ID."""
    _ensure_tracking_uri()
    experiment_name = name or MLFLOW_EXPERIMENT_NAME
    experiment = mlflow.get_experiment_by_name(experiment_name)
    if experiment is not None:
        return experiment.experiment_id
    return mlflow.create_experiment(experiment_name)


def log_training_run(
    params: dict[str, Any],
    metrics: dict[str, float],
    model_uri: str,
    tags: dict[str, str] | None = None,
) -> str:
    """Log a training run to MLflow. Returns the run ID."""
    _ensure_tracking_uri()
    experiment_id = get_or_create_experiment()

    with mlflow.start_run(experiment_id=experiment_id, tags=tags or {}) as run:
        mlflow.log_params(params)
        mlflow.log_metrics(metrics)
        mlflow.set_tag("model_uri", model_uri)
        mlflow.set_tag("pipeline_stage", "training")
        logger.info("Logged training run to MLflow", extra={"run_id": run.info.run_id})
        return run.info.run_id


def log_evaluation_run(
    eval_metrics: dict[str, float],
    model_version: str,
    tags: dict[str, str] | None = None,
) -> str:
    """Log an evaluation run to MLflow. Returns the run ID."""
    _ensure_tracking_uri()
    experiment_id = get_or_create_experiment()

    run_tags = {"pipeline_stage": "evaluation", "model_version": model_version}
    if tags:
        run_tags.update(tags)

    with mlflow.start_run(experiment_id=experiment_id, tags=run_tags) as run:
        mlflow.log_metrics(eval_metrics)
        logger.info(
            "Logged evaluation run to MLflow",
            extra={"run_id": run.info.run_id, "model_version": model_version},
        )
        return run.info.run_id


def log_bias_report(
    bias_metrics: dict[str, float],
    model_version: str,
    passed: bool,
) -> str:
    """Log bias detection results to MLflow. Returns the run ID."""
    _ensure_tracking_uri()
    experiment_id = get_or_create_experiment()

    with mlflow.start_run(experiment_id=experiment_id) as run:
        mlflow.set_tag("pipeline_stage", "bias_detection")
        mlflow.set_tag("model_version", model_version)
        mlflow.set_tag("bias_check_passed", str(passed))
        mlflow.log_metrics(bias_metrics)
        logger.info(
            "Logged bias report to MLflow",
            extra={"run_id": run.info.run_id, "passed": passed},
        )
        return run.info.run_id


def register_model(run_id: str, model_uri: str, model_name: str | None = None) -> Any:
    """Register a model version in the MLflow Model Registry."""
    _ensure_tracking_uri()
    client = MlflowClient()
    name = model_name or MLFLOW_MODEL_NAME

    try:
        client.get_registered_model(name)
    except mlflow.exceptions.MlflowException:
        client.create_registered_model(name)

    result = client.create_model_version(
        name=name,
        source=model_uri,
        run_id=run_id,
    )
    logger.info(
        "Registered model version",
        extra={"model_name": name, "version": result.version},
    )
    return result


def log_model_comparison(
    selection_result: dict[str, Any],
    artifact_dir: str | None = None,
) -> str:
    """Log model comparison run with per-model scores and visualization artifacts.

    Returns the MLflow run ID.
    """
    _ensure_tracking_uri()
    experiment_id = get_or_create_experiment()

    winner = selection_result["winner"]
    scores = selection_result["scores"]

    with mlflow.start_run(experiment_id=experiment_id) as run:
        mlflow.set_tag("pipeline_stage", "model_selection")
        mlflow.set_tag("selected_model", winner)
        mlflow.set_tag("selection_formula", selection_result.get("selection_formula", ""))
        mlflow.set_tag("num_models_compared", str(len(scores)))

        # Log per-model metrics
        for model_name_key, model_scores in scores.items():
            safe_name = model_name_key.replace("-", "_").replace(".", "_")
            for metric_key, value in model_scores.items():
                if isinstance(value, (int, float)) and value is not None:
                    mlflow.log_metric(f"{safe_name}_{metric_key}", value)

        # Log winner's composite as top-level metric
        mlflow.log_metric("winner_composite", scores[winner]["composite"])

        # Log rankings
        for rank, (name, score) in enumerate(selection_result.get("rankings", []), 1):
            mlflow.set_tag(f"rank_{rank}", f"{name} ({score:.4f})")

        # Log visualization artifacts
        if artifact_dir:
            import os
            artifact_path = artifact_dir
            for fname in os.listdir(artifact_path):
                fpath = os.path.join(artifact_path, fname)
                if os.path.isfile(fpath) and (
                    fname.endswith(".png") or fname.endswith(".html") or fname.endswith(".json")
                ):
                    mlflow.log_artifact(fpath, artifact_path="model_comparison")

        logger.info(
            "Logged model comparison to MLflow",
            extra={"run_id": run.info.run_id, "winner": winner},
        )
        return run.info.run_id


def get_latest_production_model(model_name: str | None = None) -> Any | None:
    """Get the latest model version with 'Production' alias."""
    _ensure_tracking_uri()
    client = MlflowClient()
    name = model_name or MLFLOW_MODEL_NAME

    try:
        versions = client.search_model_versions(f"name='{name}'")
        if not versions:
            return None
        # Return the latest version by version number
        return max(versions, key=lambda v: int(v.version))
    except mlflow.exceptions.MlflowException:
        return None
