"""Retry Failed PDFs Task - Wrapper for retry_failed_pdfs flow."""
from typing import Dict, Any

from src.database.connection import CloudSQLConnection
from src.storage.gcs_client import GCSClient
from src.tasks.retry_failed_pdfs import run_retry_failed_pdfs
from src.utils.logging import get_logger

logger = get_logger(__name__)


class RetryFailedPdfsTask:
    """
    Task to retry failed PDF fetches from fetch_pdf_failures table.
    
    Uses CloudSQLConnection to connect to Cloud SQL (GCP) via proxy.
    """

    def __init__(self):
        self.gcs: GCSClient = None
        self.db: CloudSQLConnection = None

    def _initialize(self) -> None:
        """Initialize GCS client and Cloud SQL database connection."""
        if self.gcs is None:
            self.gcs = GCSClient()
        if self.db is None:
            self.db = CloudSQLConnection()
            logger.info("Initialized CloudSQLConnection for retry_failed_pdfs")

    async def execute(self) -> Dict[str, Any]:
        """
        Execute the retry-failed-PDFs flow.

        Queries fetch_pdf_failures for eligible rows, attempts re-download/upload,
        updates or deletes rows based on result, reconciles with GCS, and sends
        alerts for papers with fail_runs > 5.

        Returns:
            Dict with stats:
            {
                "status": str,
                "fetched": int,      # Number of eligible rows found
                "succeeded": int,    # Successfully uploaded
                "failed": int,       # Still failed after retry
                "deleted_403_404": int,  # Removed due to permanent errors
                "reconciled": int,   # Removed because PDF already in GCS
                "alerted": int,      # Papers flagged for alert
            }
        """
        try:
            self._initialize()
        except Exception as e:
            logger.exception("Failed to initialize clients: %s", e)
            return {
                "status": "error",
                "error": str(e),
                "fetched": 0,
                "succeeded": 0,
                "failed": 0,
                "deleted_403_404": 0,
                "reconciled": 0,
                "alerted": 0,
            }

        logger.info("Starting retry-failed-PDFs task")

        try:
            stats = await run_retry_failed_pdfs(
                get_session=self.db.get_session,
                gcs_client=self.gcs,
            )
        except Exception as e:
            logger.exception("Retry failed PDFs task failed: %s", e)
            return {
                "status": "error",
                "error": str(e),
                "fetched": 0,
                "succeeded": 0,
                "failed": 0,
                "deleted_403_404": 0,
                "reconciled": 0,
                "alerted": 0,
            }

        logger.info(
            "Retry failed PDFs complete: fetched=%d, succeeded=%d, failed=%d, "
            "deleted_403_404=%d, reconciled=%d, alerted=%d",
            stats.get("fetched", 0),
            stats.get("succeeded", 0),
            stats.get("failed", 0),
            stats.get("deleted_403_404", 0),
            stats.get("reconciled", 0),
            stats.get("alerted", 0),
        )

        return {
            "status": "completed",
            **stats,
        }
