"""Google Cloud Storage client for file operations."""
import logging
import os
import platform
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Any, List, Optional, Set

import threading

from google.cloud import storage as gcs

logger = logging.getLogger(__name__)

_gcs_client_lock = threading.Lock()
_gcs_client_instance: Optional[gcs.Client] = None


def _get_shared_client() -> gcs.Client:
    """Return a singleton gcs.Client, created once and reused."""
    global _gcs_client_instance
    if _gcs_client_instance is None:
        with _gcs_client_lock:
            if _gcs_client_instance is None:
                _gcs_client_instance = gcs.Client()
                logger.info("Created shared GCS client (singleton)")
    return _gcs_client_instance


class GCSClient:
    """
    Reusable GCS client for file storage operations.

    All files are stored under a configurable prefix (folder) within a bucket.
    Designed to be injected into any task that needs cloud storage.

    The underlying gcs.Client() is a singleton — shared across all
    GCSClient instances to avoid redundant auth and connection setup.
    """

    def __init__(self, bucket_name: Optional[str] = None, prefix: Optional[str] = None):
        bucket_name = bucket_name or os.environ.get("GCS_BUCKET", "research-lineage-pdfs")
        prefix = prefix or os.environ.get("GCS_PREFIX", "pdfs/")

        self.client = _get_shared_client()
        self.bucket = self.client.bucket(bucket_name)
        self.prefix = prefix.rstrip("/") + "/"
        self.bucket_name = bucket_name

    @property
    def base_uri(self) -> str:
        return f"gs://{self.bucket_name}/{self.prefix}"

    def _blob_path(self, filename: str) -> str:
        return f"{self.prefix}{filename}"

    # ── Single-file operations ───────────────────────────────────────

    def exists(self, filename: str) -> bool:
        """Check if a file exists in the bucket."""
        return self.bucket.blob(self._blob_path(filename)).exists()

    def upload(
        self,
        filename: str,
        content: bytes,
        content_type: str = "application/pdf",
        metadata: Optional[Dict[str, str]] = None,
    ) -> str:
        """
        Upload bytes to GCS.

        Returns:
            The gs:// URI of the uploaded file.
        """
        blob = self.bucket.blob(self._blob_path(filename))
        if metadata:
            blob.metadata = metadata
        blob.upload_from_string(content, content_type=content_type)
        uri = f"gs://{self.bucket_name}/{blob.name}"
        logger.info(f"Uploaded {filename} ({len(content)} bytes) → {uri}")
        return uri

    def download(self, filename: str) -> Optional[bytes]:
        """Download a file's content as bytes. Returns None if not found."""
        blob = self.bucket.blob(self._blob_path(filename))
        if not blob.exists():
            logger.warning(f"File not found: {filename}")
            return None
        return blob.download_as_bytes()

    def download_to_file(self, filename: str, local_path: Path) -> bool:
        """Download a file to a local path. Returns False if not found."""
        blob = self.bucket.blob(self._blob_path(filename))
        if not blob.exists():
            logger.warning(f"File not found: {filename}")
            return False
        local_path.parent.mkdir(parents=True, exist_ok=True)
        blob.download_to_filename(str(local_path))
        return True

    def delete(self, filename: str) -> bool:
        """Delete a single file. Returns True if deleted, False if not found."""
        blob = self.bucket.blob(self._blob_path(filename))
        if not blob.exists():
            return False
        blob.delete()
        logger.info(f"Deleted {filename}")
        return True

    # ── Batch operations ─────────────────────────────────────────────

    def exists_batch(self, filenames: List[str]) -> Set[str]:
        """
        Efficiently check which filenames already exist in the bucket.

        Uses a single list_blobs call instead of N individual exists() calls.
        Returns the set of filenames that ARE present.
        """
        existing: Set[str] = set()
        blobs = self.client.list_blobs(self.bucket, prefix=self.prefix)
        remote_names = {blob.name.removeprefix(self.prefix) for blob in blobs}
        for f in filenames:
            if f in remote_names:
                existing.add(f)
        return existing

    def delete_batch(self, filenames: List[str]) -> int:
        """Delete a list of files. Returns count of successfully deleted files."""
        deleted = 0
        for f in filenames:
            if self.delete(f):
                deleted += 1
        return deleted

    def delete_all(self) -> int:
        """Delete every file under the prefix. Returns count deleted."""
        blobs = list(self.client.list_blobs(self.bucket, prefix=self.prefix))
        for blob in blobs:
            blob.delete()
        logger.info(f"Deleted {len(blobs)} files from {self.base_uri}")
        return len(blobs)

    # ── Listing ──────────────────────────────────────────────────────

    def list_files(self) -> List[Dict[str, Any]]:
        """List all files under the prefix with metadata."""
        blobs = self.client.list_blobs(self.bucket, prefix=self.prefix)
        files = []
        for blob in blobs:
            filename = blob.name.removeprefix(self.prefix)
            if not filename:
                continue
            files.append({
                "filename": filename,
                "size_bytes": blob.size,
                "size_mb": round(blob.size / (1024 * 1024), 2),
                "uploaded": blob.updated.strftime("%Y-%m-%d %H:%M:%S") if blob.updated else "unknown",
                "uri": f"gs://{self.bucket_name}/{blob.name}",
                "metadata": blob.metadata or {},
            })
        return files

    # ── Convenience ──────────────────────────────────────────────────

    def open_locally(self, filename: str) -> Optional[Path]:
        """Download to a temp file and open with the system PDF viewer."""
        tmp_dir = Path(tempfile.mkdtemp())
        local_path = tmp_dir / filename

        if not self.download_to_file(filename, local_path):
            return None

        system = platform.system()
        if system == "Darwin":
            subprocess.run(["open", str(local_path)])
        elif system == "Linux":
            subprocess.run(["xdg-open", str(local_path)])
        elif system == "Windows":
            os.startfile(str(local_path))

        return local_path
