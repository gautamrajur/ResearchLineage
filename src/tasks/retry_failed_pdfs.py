"""Retry failed PDF fetches using data from fetch_pdf_failures table.

Designed to be run when the pipeline is idle (e.g. from a DAG). Fetches eligible
rows (retry_after passed, alerted=FALSE), runs PDF fetch with stored URL/timeout,
updates or deletes rows by reason (403/404 -> delete; else update with +20s timeout,
+30s retry_after, fail_runs+1), reconciles with GCS, and sends one alert for
fail_runs > 5. Callable from script or DAG; no Airflow dependency.
"""
import asyncio
import logging
from typing import Any, Callable, Dict, List, Optional

from src.database.fetch_pdf_failures_repository import FetchPdfFailuresRepository
from src.storage.gcs_client import GCSClient
from src.tasks.pdf_fetcher import PDFFetcher, FetchResult
from src.utils.config import settings
from src.utils.email_templates import AlertLevel, EmailTemplate, send_alert_email

logger = logging.getLogger(__name__)


async def run_retry_failed_pdfs(
    get_session: Callable[..., Any],
    gcs_client: GCSClient,
    *,
    on_alert: Optional[Callable[[List[Dict[str, Any]]], None]] = None,
) -> Dict[str, int]:
    """
    Run the retry-failed-PDFs flow: query eligible rows, fetch with DB URL/timeout,
    update or delete by reason, reconcile with GCS, alert if fail_runs > 5.

    Args:
        get_session: Context manager yielding a DB session (e.g. DatabaseConnection().get_session).
        gcs_client: GCS client for upload and list.
        on_alert: Optional callback(list of row dicts) when fail_runs > 5 and alerted=FALSE.
                  If not provided, sends email when SMTP/alert_email_to are set, else logs.

    Returns:
        Dict with keys: fetched, succeeded, failed, deleted_403_404, reconciled, alerted.
    """
    stats = {
        "fetched": 0,
        "succeeded": 0,
        "failed": 0,
        "deleted_403_404": 0,
        "reconciled": 0,
        "alerted": 0,
    }

    with get_session() as session:
        repo = FetchPdfFailuresRepository(session)

        # 1. Fetch eligible rows
        eligible = repo.get_eligible_for_retry()
        if not eligible:
            logger.info("No eligible rows for retry (retry_after not yet passed or alerted)")
            _reconcile_and_alert(session, repo, gcs_client, stats, on_alert)
            return stats

        stats["fetched"] = len(eligible)
        logger.info("Retrying %d failed paper(s) from fetch_pdf_failures", stats["fetched"])

        # 2. Fetch each with stored URL and timeout
        still_failed: List[tuple] = []  # (row, result)
        for row in eligible:
            fetcher = PDFFetcher(
                gcs_client,
                download_timeout=float(row.get("timeout_sec", 120)),
            )
            result = await fetcher.fetch_from_url_and_upload(
                paper_id=row["paper_id"],
                title=row.get("title") or "",
                fetch_url=row.get("fetch_url") or "",
                paper_metadata={"paperId": row["paper_id"], "title": row.get("title")},
            )
            if result.status == "uploaded":
                stats["succeeded"] += 1
                repo.delete(row["paper_id"])
            else:
                stats["failed"] += 1
                still_failed.append((row, result))

        # 3. Process still-failed: 403/404 -> delete; else update
        for row, result in still_failed:
            if result.response_code in (403, 404):
                repo.delete(row["paper_id"])
                stats["deleted_403_404"] += 1
                logger.info("Deleted paper_id=%s (reason=%s)", row["paper_id"], result.response_code)
            else:
                reason = result.error or result.status
                if len(reason) > 64:
                    reason = reason[:64]
                repo.update_after_failure(
                    paper_id=row["paper_id"],
                    fail_runs=row["fail_runs"] + 1,
                    fetch_url=row.get("fetch_url") or result.fetch_url or "",
                    reason=reason,
                    timeout_sec=float(row.get("timeout_sec", 120)),
                )

        # 4. Reconcile with GCS: delete table rows whose paper_id exists in GCS
        stats["reconciled"] = _reconcile_with_gcs(session, repo, gcs_client)

        # 5. Alert for fail_runs > 5 and alerted = FALSE
        pending = repo.get_alert_pending()
        if pending:
            stats["alerted"] = len(pending)
            if on_alert:
                on_alert(pending)
            else:
                _default_alert(pending)
            repo.mark_alerted([r["paper_id"] for r in pending])

    return stats


def _reconcile_with_gcs(session: Any, repo: FetchPdfFailuresRepository, gcs: GCSClient) -> int:
    """Delete fetch_pdf_failures rows whose paper_id has a PDF in GCS."""
    files = gcs.list_files()
    paper_ids_in_gcs = []
    for f in files:
        name = f.get("filename", "")
        if name.endswith(".pdf"):
            paper_ids_in_gcs.append(name[:-4])
    if not paper_ids_in_gcs:
        return 0
    count = repo.delete_by_paper_ids(paper_ids_in_gcs)
    if count:
        logger.info("Reconciled %d row(s) with GCS (deleted)", count)
    return count


def _reconcile_and_alert(
    session: Any,
    repo: FetchPdfFailuresRepository,
    gcs_client: GCSClient,
    stats: Dict[str, int],
    on_alert: Optional[Callable[[List[Dict[str, Any]]], None]],
) -> None:
    """Run reconcile and alert even when no eligible rows (e.g. cleanup + alert)."""
    stats["reconciled"] = _reconcile_with_gcs(session, repo, gcs_client)
    pending = repo.get_alert_pending()
    if pending:
        stats["alerted"] = len(pending)
        if on_alert:
            on_alert(pending)
        else:
            _default_alert(pending)
        repo.mark_alerted([r["paper_id"] for r in pending])


def _send_alert_email(rows: List[Dict[str, Any]]) -> bool:
    """Send alert email for papers with fail_runs > 5. Returns True if sent, False otherwise."""
    template = EmailTemplate(
        title="PDF Fetch Failures",
        alert_level=AlertLevel.ERROR,
        summary=f"{len(rows)} paper(s) have failed PDF fetch more than 5 times (fail_runs > 5)",
        details=rows,
        columns=["paper_id", "title", "fail_runs", "reason", "fetch_url"],
        footer_note="These papers have been marked as alerted and won't trigger duplicate notifications.",
    )
    count = len(rows)
    subject = f"ResearchLineage Alert: {count} Paper{'s' if count != 1 else ''} Require{'s' if count == 1 else ''} Attention"
    if send_alert_email(subject, template):
        logger.info("Alert email sent to %s for %d paper(s)", settings.alert_email_to, count)
        return True
    return False


def _default_alert(rows: List[Dict[str, Any]]) -> None:
    """Send alert by email when SMTP/alert_email_to are set; otherwise log."""
    if _send_alert_email(rows):
        return
    logger.warning(
        "ALERT: %d paper(s) have fail_runs > 5 and have not been alerted yet",
        len(rows),
    )
    for r in rows:
        logger.warning(
            "  paper_id=%s title=%s fail_runs=%s reason=%s fetch_url=%s",
            r.get("paper_id"),
            (r.get("title") or "")[:50],
            r.get("fail_runs"),
            r.get("reason"),
            (r.get("fetch_url") or "")[:60],
        )
