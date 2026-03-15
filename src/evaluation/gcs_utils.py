# src/evaluation/gcs_utils.py
from __future__ import annotations

import json
import logging
from io import StringIO
from typing import Any

from google.cloud import storage

logger = logging.getLogger(__name__)


def _parse_gcs_uri(uri: str) -> tuple[str, str]:
    """Split 'gs://bucket/path/to/file' into ('bucket', 'path/to/file')."""
    if not uri.startswith("gs://"):
        raise ValueError(f"Expected a GCS URI starting with gs://, got: {uri!r}")
    without_scheme = uri[5:]
    bucket, _, blob_path = without_scheme.partition("/")
    return bucket, blob_path


def load_jsonl_from_gcs(
    gcs_uri: str,
    project_id: str,
) -> list[dict[str, Any]]:
    """
    Read a JSONL file from GCS and return a list of parsed dicts.
    Each line must be a valid JSON object.
    """
    bucket_name, blob_name = _parse_gcs_uri(gcs_uri)
    client = storage.Client(project=project_id)
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)

    logger.info("Loading JSONL from GCS", extra={"uri": gcs_uri})
    content = blob.download_as_text(encoding="utf-8")

    records: list[dict[str, Any]] = []
    for line_num, line in enumerate(content.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as exc:
            logger.warning(
                "Skipping malformed JSONL line",
                extra={"line_num": line_num, "error": str(exc)},
            )

    logger.info(
        "Loaded JSONL records from GCS",
        extra={"uri": gcs_uri, "n_records": len(records)},
    )
    return records


def save_jsonl_to_gcs(
    records: list[dict[str, Any]],
    gcs_uri: str,
    project_id: str,
) -> None:
    """Write a list of dicts to a JSONL file on GCS."""
    bucket_name, blob_name = _parse_gcs_uri(gcs_uri)
    client = storage.Client(project=project_id)
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)

    buf = StringIO()
    for record in records:
        buf.write(json.dumps(record, ensure_ascii=False, default=str))
        buf.write("\n")

    blob.upload_from_string(
        buf.getvalue(),
        content_type="application/json",
    )
    logger.info(
        "Saved JSONL to GCS",
        extra={"uri": gcs_uri, "n_records": len(records)},
    )


def save_json_to_gcs(
    data: dict[str, Any],
    gcs_uri: str,
    project_id: str,
) -> None:
    """Write a single JSON object to GCS."""
    bucket_name, blob_name = _parse_gcs_uri(gcs_uri)
    client = storage.Client(project=project_id)
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)

    blob.upload_from_string(
        json.dumps(data, indent=2, ensure_ascii=False, default=str),
        content_type="application/json",
    )
    logger.info("Saved JSON to GCS", extra={"uri": gcs_uri})


def list_gcs_blobs(
    gcs_prefix: str,
    project_id: str,
    suffix: str = ".jsonl",
) -> list[str]:
    """Return full GCS URIs for all blobs under a prefix matching the suffix."""
    bucket_name, prefix = _parse_gcs_uri(gcs_prefix)
    client = storage.Client(project=project_id)
    blobs = client.list_blobs(bucket_name, prefix=prefix)
    return [f"gs://{bucket_name}/{b.name}" for b in blobs if b.name.endswith(suffix)]
