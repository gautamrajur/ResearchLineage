"""GCP Artifact Registry integration for model versioning."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from google.cloud import storage

logger = logging.getLogger(__name__)

DEFAULT_BUCKET = "researchlineage-gcs"
DEFAULT_PROJECT = "researchlineage"
REGISTRY_PREFIX = "model-registry"
STATE_BLOB = "pipeline_state.json"


def push_model_to_registry(
    model_gcs_uri: str,
    version: str,
    metadata: dict[str, Any] | None = None,
    bucket_name: str = DEFAULT_BUCKET,
    project_id: str = DEFAULT_PROJECT,
) -> str:
    """Register a model version by writing metadata to the registry prefix in GCS.

    The actual model weights stay at model_gcs_uri. The registry stores
    a metadata JSON file per version for tracking and lookup.

    Returns the GCS path of the registry entry.
    """
    client = storage.Client(project=project_id)
    bucket = client.bucket(bucket_name)

    entry = {
        "version": version,
        "model_gcs_uri": model_gcs_uri,
        "registered_at": datetime.now(tz=timezone.utc).isoformat(),
        "stage": "staging",
        **(metadata or {}),
    }

    blob_path = f"{REGISTRY_PREFIX}/{version}/metadata.json"
    bucket.blob(blob_path).upload_from_string(
        json.dumps(entry, indent=2),
        content_type="application/json",
    )

    logger.info(
        "Model registered",
        extra={"version": version, "registry_path": f"gs://{bucket_name}/{blob_path}"},
    )
    return f"gs://{bucket_name}/{blob_path}"


def list_model_versions(
    bucket_name: str = DEFAULT_BUCKET,
    project_id: str = DEFAULT_PROJECT,
) -> list[dict[str, Any]]:
    """List all registered model versions with their metadata."""
    client = storage.Client(project=project_id)
    bucket = client.bucket(bucket_name)

    versions = []
    blobs = bucket.list_blobs(prefix=f"{REGISTRY_PREFIX}/")
    for blob in blobs:
        if blob.name.endswith("/metadata.json"):
            try:
                data = json.loads(blob.download_as_text())
                versions.append(data)
            except Exception as exc:
                logger.warning("Failed to parse registry entry: %s — %s", blob.name, exc)

    versions.sort(key=lambda v: v.get("registered_at", ""), reverse=True)
    return versions


def promote_model(
    version: str,
    stage: str = "production",
    bucket_name: str = DEFAULT_BUCKET,
    project_id: str = DEFAULT_PROJECT,
) -> None:
    """Update a model version's stage (e.g., staging → production)."""
    client = storage.Client(project=project_id)
    bucket = client.bucket(bucket_name)

    blob_path = f"{REGISTRY_PREFIX}/{version}/metadata.json"
    blob = bucket.blob(blob_path)

    if not blob.exists():
        raise ValueError(f"Model version {version} not found in registry")

    entry = json.loads(blob.download_as_text())
    entry["stage"] = stage
    entry["promoted_at"] = datetime.now(tz=timezone.utc).isoformat()

    blob.upload_from_string(
        json.dumps(entry, indent=2),
        content_type="application/json",
    )
    logger.info("Model promoted", extra={"version": version, "stage": stage})
