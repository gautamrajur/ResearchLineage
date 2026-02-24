"""Repository for fetch_pdf_failures table — failed PDF fetch tracking and retry."""
import logging
from typing import Any, Dict, List

from sqlalchemy import text

logger = logging.getLogger(__name__)

RETRY_AFTER_SECONDS = 30
TIMEOUT_BUMP_SECONDS = 20


class FetchPdfFailuresRepository:
    """Repository for fetch_pdf_failures table operations."""

    def __init__(self, session: Any) -> None:
        self.session = session

    def get_by_paper_ids(self, paper_ids: List[str]) -> List[Dict[str, Any]]:
        """Return rows for the given paper_ids (e.g. for timeout_sec / retry_after)."""
        if not paper_ids:
            return []
        q = text(
            """
            SELECT paper_id, title, status, fail_runs, fetch_url, reason, timeout_sec,
                   retry_after, first_failed_at, last_attempt_at, alerted, created_at
            FROM fetch_pdf_failures
            WHERE paper_id = ANY(:paper_ids)
            """
        )
        rows = self.session.execute(q, {"paper_ids": paper_ids}).fetchall()
        return [_row_to_dict(r) for r in rows]

    def get_eligible_for_retry(self) -> List[Dict[str, Any]]:
        """Return rows where retry_after has passed and alerted is FALSE.
        Uses index idx_fetch_pdf_failures_retry_after on retry_after.
        """
        q = text(
            """
            SELECT paper_id, title, status, fail_runs, fetch_url, reason, timeout_sec,
                   retry_after, first_failed_at, last_attempt_at, alerted, created_at
            FROM fetch_pdf_failures
            WHERE (retry_after IS NULL OR retry_after <= NOW())
              AND alerted = FALSE
            ORDER BY last_attempt_at
            """
        )
        rows = self.session.execute(q).fetchall()
        return [_row_to_dict(r) for r in rows]

    def insert(self, row: Dict[str, Any]) -> None:
        """Insert one failure row (first time this paper fails)."""
        q = text(
            """
            INSERT INTO fetch_pdf_failures (
                paper_id, title, status, fail_runs, fetch_url, reason, timeout_sec,
                retry_after, alerted
            ) VALUES (
                :paper_id, :title, :status, 1, :fetch_url, :reason, :timeout_sec,
                NOW() + INTERVAL '30 seconds', FALSE
            )
            """
        )
        params = {
            "paper_id": row["paper_id"],
            "title": row.get("title") or "",
            "status": row.get("status") or "download_failed",
            "fetch_url": row.get("fetch_url") or "",
            "reason": row.get("reason") or "",
            "timeout_sec": float(row.get("timeout_sec", 120)),
        }
        self.session.execute(q, params)
        logger.debug("Inserted fetch_pdf_failures row for paper_id=%s", row["paper_id"])

    def upsert(self, row: Dict[str, Any]) -> None:
        """
        Insert or update: if paper_id exists, increment fail_runs and set
        last_attempt_at, retry_after = NOW() + 30s, and update reason/url/timeout.
        """
        q = text(
            """
            INSERT INTO fetch_pdf_failures (
                paper_id, title, status, fail_runs, fetch_url, reason, timeout_sec,
                retry_after, alerted
            ) VALUES (
                :paper_id, :title, :status, 1, :fetch_url, :reason, :timeout_sec,
                NOW() + INTERVAL '30 seconds', FALSE
            )
            ON CONFLICT (paper_id) DO UPDATE SET
                fail_runs = fetch_pdf_failures.fail_runs + 1,
                title = EXCLUDED.title,
                status = EXCLUDED.status,
                fetch_url = EXCLUDED.fetch_url,
                reason = EXCLUDED.reason,
                timeout_sec = EXCLUDED.timeout_sec,
                last_attempt_at = NOW(),
                retry_after = NOW() + INTERVAL '30 seconds'
            """
        )
        params = {
            "paper_id": row["paper_id"],
            "title": row.get("title") or "",
            "status": row.get("status") or "download_failed",
            "fetch_url": row.get("fetch_url") or "",
            "reason": row.get("reason") or "",
            "timeout_sec": float(row.get("timeout_sec", 120)),
        }
        self.session.execute(q, params)
        logger.debug("Upserted fetch_pdf_failures for paper_id=%s", row["paper_id"])

    def update_after_failure(
        self,
        paper_id: str,
        fail_runs: int,
        fetch_url: str,
        reason: str,
        timeout_sec: float,
    ) -> None:
        """
        Update row after a retry run failed: timeout_sec += 20, retry_after = NOW() + 30s.
        """
        q = text(
            """
            UPDATE fetch_pdf_failures
            SET fail_runs = :fail_runs,
                fetch_url = :fetch_url,
                reason = :reason,
                timeout_sec = :timeout_sec,
                last_attempt_at = NOW(),
                retry_after = NOW() + INTERVAL '30 seconds'
            WHERE paper_id = :paper_id
            """
        )
        self.session.execute(
            q,
            {
                "paper_id": paper_id,
                "fail_runs": fail_runs,
                "fetch_url": fetch_url,
                "reason": reason,
                "timeout_sec": timeout_sec + TIMEOUT_BUMP_SECONDS,
            },
        )
        logger.debug("Updated fetch_pdf_failures after failure for paper_id=%s", paper_id)

    def delete(self, paper_id: str) -> None:
        """Remove row (on success or 403/404)."""
        q = text("DELETE FROM fetch_pdf_failures WHERE paper_id = :paper_id")
        self.session.execute(q, {"paper_id": paper_id})
        logger.debug("Deleted fetch_pdf_failures row for paper_id=%s", paper_id)

    def delete_by_paper_ids(self, paper_ids: List[str]) -> int:
        """Delete rows whose paper_id is in the list. Returns number of rows deleted."""
        if not paper_ids:
            return 0
        q = text("DELETE FROM fetch_pdf_failures WHERE paper_id = ANY(:paper_ids)")
        result = self.session.execute(q, {"paper_ids": paper_ids})
        count = result.rowcount if hasattr(result, "rowcount") else 0
        logger.debug("Deleted %d fetch_pdf_failures row(s) by paper_ids", count)
        return count

    def get_alert_pending(self) -> List[Dict[str, Any]]:
        """Return rows where fail_runs > 5 and alerted = FALSE."""
        q = text(
            """
            SELECT paper_id, title, status, fail_runs, fetch_url, reason, timeout_sec,
                   retry_after, first_failed_at, last_attempt_at, alerted, created_at
            FROM fetch_pdf_failures
            WHERE fail_runs > 5 AND alerted = FALSE
            """
        )
        rows = self.session.execute(q).fetchall()
        return [_row_to_dict(r) for r in rows]

    def mark_alerted(self, paper_ids: List[str]) -> None:
        """Set alerted = TRUE for the given paper_ids."""
        if not paper_ids:
            return
        q = text(
            "UPDATE fetch_pdf_failures SET alerted = TRUE WHERE paper_id = ANY(:paper_ids)"
        )
        self.session.execute(q, {"paper_ids": paper_ids})
        logger.info("Marked alerted for %d papers", len(paper_ids))


def _row_to_dict(row: Any) -> Dict[str, Any]:
    """Convert a SQLAlchemy Row to a dict with column names."""
    return dict(row._mapping) if hasattr(row, "_mapping") else dict(row)
