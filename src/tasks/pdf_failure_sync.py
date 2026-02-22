"""Sync in-memory PDF fetch failures to fetch_pdf_failures table.

Called after the main PDF fetch run completes. Uses upsert: insert if paper_id
not present, else update fail_runs, reason, last_attempt_at, retry_after (+30s).
Designed to be callable from script or from a DAG task (pass get_session).
"""
import logging
from typing import Any, Callable, Dict, List

from src.database.fetch_pdf_failures_repository import FetchPdfFailuresRepository

logger = logging.getLogger(__name__)


def sync_failures_to_db(
    failure_list: List[Dict[str, Any]],
    get_session: Callable[..., Any],
) -> int:
    """
    Persist the list of failed PDF fetch results to fetch_pdf_failures.

    Each item should have: paper_id, title, status, fetch_url, reason, timeout_sec.
    If a row for paper_id already exists, it is updated (fail_runs incremented,
    last_attempt_at and retry_after set). Otherwise a new row is inserted.

    Args:
        failure_list: List of dicts with keys paper_id, title, status, fetch_url,
                      reason, timeout_sec (and optionally others).
        get_session: Context manager that yields a DB session (e.g. DatabaseConnection().get_session).

    Returns:
        Number of rows upserted.
    """
    if not failure_list:
        return 0

    with get_session() as session:
        repo = FetchPdfFailuresRepository(session)
        for item in failure_list:
            row = _normalize_failure_row(item)
            repo.upsert(row)
        count = len(failure_list)
        logger.info("Synced %d failure(s) to fetch_pdf_failures", count)
        return count


def _normalize_failure_row(item: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure required keys exist and types are correct for the table."""
    return {
        "paper_id": str(item["paper_id"]),
        "title": str(item.get("title") or ""),
        "status": str(item.get("status") or "download_failed"),
        "fetch_url": str(item.get("fetch_url") or ""),
        "reason": str(item.get("reason") or item.get("error") or "")[:64],
        "timeout_sec": float(item.get("timeout_sec", 120)),
    }
