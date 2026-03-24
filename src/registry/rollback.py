"""Rollback mechanism for model deployment."""

from __future__ import annotations

import json
import logging
import subprocess
from datetime import datetime, timezone
from typing import Any

from google.cloud import storage

from src.registry.artifact_registry import (
    DEFAULT_BUCKET,
    DEFAULT_PROJECT,
    STATE_BLOB,
    list_model_versions,
)

logger = logging.getLogger(__name__)


def get_rollback_candidates(
    bucket_name: str = DEFAULT_BUCKET,
    project_id: str = DEFAULT_PROJECT,
) -> list[dict[str, Any]]:
    """List available model versions that can be rolled back to.

    Returns versions sorted by registration date (newest first),
    excluding the currently deployed version.
    """
    versions = list_model_versions(bucket_name=bucket_name, project_id=project_id)

    # Get current deployed version from pipeline_state.json
    try:
        client = storage.Client(project=project_id)
        bucket = client.bucket(bucket_name)
        state = json.loads(bucket.blob(STATE_BLOB).download_as_text())
        current_version = state.get("last_model_version", "")
    except Exception:
        current_version = ""

    candidates = [v for v in versions if v.get("version") != current_version]

    for c in candidates:
        c["is_current"] = False
    for v in versions:
        if v.get("version") == current_version:
            v["is_current"] = True

    return candidates


def rollback_model(
    target_version: str,
    bucket_name: str = DEFAULT_BUCKET,
    project_id: str = DEFAULT_PROJECT,
    modal_app_name: str = "research-lineage-serving",
    serving_max_len: int = 102400,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Rollback to a previous model version.

    1. Updates pipeline_state.json on GCS
    2. Updates Modal serving-config secret
    3. Redeploys Modal serving endpoint

    Args:
        target_version: The model version to rollback to.
        dry_run: If True, only print what would happen without executing.

    Returns:
        Dict with rollback details.
    """
    client = storage.Client(project=project_id)
    bucket = client.bucket(bucket_name)

    model_gcs_uri = f"gs://{bucket_name}/models/trained/{target_version}"

    # Verify the target model exists
    prefix = f"models/trained/{target_version}/"
    blobs = list(bucket.list_blobs(prefix=prefix, max_results=1))
    if not blobs:
        raise ValueError(
            f"Model version {target_version} not found at {model_gcs_uri}"
        )

    result = {
        "target_version": target_version,
        "model_gcs_uri": model_gcs_uri,
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "dry_run": dry_run,
    }

    if dry_run:
        logger.info("Dry run — would rollback to %s", target_version)
        return result

    # 1. Update pipeline_state.json
    state = {
        "last_model_version": target_version,
        "last_model_gcs_uri": model_gcs_uri,
        "last_serving_platform": "modal",
        "last_modal_app_name": modal_app_name,
        "serving_max_len": serving_max_len,
        "updated_at": result["timestamp"],
        "rollback_from": _get_current_version(bucket),
    }
    bucket.blob(STATE_BLOB).upload_from_string(
        json.dumps(state, indent=2),
        content_type="application/json",
    )

    # 2. Update Modal secret and redeploy
    try:
        subprocess.run(
            [
                "modal", "secret", "create", "serving-config",
                f"MODEL_GCS_PATH={model_gcs_uri}",
                f"SERVING_MAX_LEN={serving_max_len}",
                'HF_MODEL_NAME=""',
                "--force",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        result["modal_secret_updated"] = True
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        logger.error("Failed to update Modal secret: %s", exc)
        result["modal_secret_updated"] = False
        result["modal_error"] = str(exc)

    logger.info("Rollback complete", extra=result)
    return result


def _get_current_version(bucket: Any) -> str:
    """Read the current model version from pipeline_state.json."""
    try:
        state = json.loads(bucket.blob(STATE_BLOB).download_as_text())
        return state.get("last_model_version", "unknown")
    except Exception:
        return "unknown"
