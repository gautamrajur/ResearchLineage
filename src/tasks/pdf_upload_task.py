"""PDF Upload Task - Upload research paper PDFs to GCS."""
import logging
from typing import Dict, Any, Optional

from src.storage.gcs_client import GCSClient
from src.tasks.pdf_fetcher import PDFFetcher, BatchResult
from src.tasks.pdf_failure_sync import sync_failures_to_db
from src.database.connection import DatabaseConnection

LOG = logging.getLogger(__name__)


class PDFUploadTask:
    """Task to upload PDFs to GCS from acquisition results."""

    def __init__(self):
        self.gcs: Optional[GCSClient] = None
        self.fetcher: Optional[PDFFetcher] = None

    def _initialize(self) -> None:
        """Initialize GCS client and PDF fetcher."""
        if self.gcs is None:
            self.gcs = GCSClient()
            self.fetcher = PDFFetcher(self.gcs)

    def _build_failure_list(self, batch: BatchResult) -> list:
        """Build list of failure dicts for sync to fetch_pdf_failures table."""
        failure_list = []
        for r in batch.results:
            if r.status not in ("download_failed", "error", "gcs_upload_failed"):
                continue
            failure_list.append({
                "paper_id": r.paper_id,
                "title": r.title,
                "status": r.status,
                "fetch_url": getattr(r, "fetch_url", "") or "",
                "reason": r.error or r.status,
                "timeout_sec": self.fetcher.download_timeout if self.fetcher else 30,
            })
        return failure_list

    async def execute(self, acquisition_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Upload PDFs for papers in acquisition result.

        Args:
            acquisition_result: Pre-fetched paper metadata from DataAcquisitionTask.
                Expected format:
                {
                    "target_paper_id": str,
                    "papers": List[Dict],
                    "references": List[Dict],
                    "citations": List[Dict],
                    "total_papers": int,
                    ...
                }

        Returns:
            Dict with upload statistics:
            {
                "status": str,
                "uploaded": int,
                "already_in_gcs": int,
                "download_failed": int,
                "no_pdf_found": int,
                "errors": int,
                "total": int,
            }
        """
        # Validate input
        if not acquisition_result:
            LOG.warning("No acquisition result provided")
            return {
                "status": "no_data",
                "uploaded": 0,
                "already_in_gcs": 0,
                "download_failed": 0,
                "no_pdf_found": 0,
                "errors": 0,
                "total": 0,
            }

        papers = acquisition_result.get("papers", [])
        if not papers:
            LOG.warning("No papers in acquisition result")
            return {
                "status": "no_papers",
                "uploaded": 0,
                "already_in_gcs": 0,
                "download_failed": 0,
                "no_pdf_found": 0,
                "errors": 0,
                "total": 0,
            }

        # Initialize clients
        self._initialize()

        LOG.info(
            "Starting PDF upload for %d papers (target: %s)",
            len(papers),
            acquisition_result.get("target_paper_id", "unknown"),
        )

        # Fetch and upload PDFs
        try:
            batch = await self.fetcher.fetch_batch(papers)
        except Exception as e:
            LOG.error("PDF fetch batch failed: %s", e)
            return {
                "status": "error",
                "error": str(e),
                "uploaded": 0,
                "already_in_gcs": 0,
                "download_failed": 0,
                "no_pdf_found": 0,
                "errors": 1,
                "total": len(papers),
            }

        # Log results
        LOG.info(
            "PDF upload complete: uploaded=%d, already_in_gcs=%d, "
            "download_failed=%d, no_pdf_found=%d, errors=%d, total=%d",
            batch.uploaded,
            batch.already_in_gcs,
            batch.download_failed,
            batch.no_pdf_found,
            batch.errors,
            batch.total,
        )

        # Sync failures to database for retry flow
        failure_list = self._build_failure_list(batch)
        if failure_list:
            try:
                db = DatabaseConnection()
                synced = sync_failures_to_db(failure_list, db.get_session)
                LOG.info("Synced %d failure(s) to fetch_pdf_failures table", synced)
            except Exception as e:
                LOG.warning(
                    "Could not sync failures to database: %s", e
                )

        return {
            "status": "completed",
            "uploaded": batch.uploaded,
            "already_in_gcs": batch.already_in_gcs,
            "download_failed": batch.download_failed,
            "no_pdf_found": batch.no_pdf_found,
            "errors": batch.errors,
            "total": batch.total,
        }
