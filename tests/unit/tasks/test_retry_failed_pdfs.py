"""Unit tests for src.tasks.retry_failed_pdfs."""
import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from contextlib import contextmanager

from src.tasks.retry_failed_pdfs import (
    run_retry_failed_pdfs,
    _reconcile_with_gcs,
    _reconcile_and_alert,
    _send_alert_email,
    _default_alert,
)
from src.tasks.pdf_fetcher import FetchResult


def _run(coro):
    """Run async coroutine."""
    return asyncio.run(coro)


@pytest.fixture
def session():
    """Mock database session."""
    return MagicMock()


@pytest.fixture
def get_session(session):
    """Mock session context manager."""
    @contextmanager
    def _get():
        yield session
    return _get


@pytest.fixture
def gcs():
    """Mock GCS client."""
    client = MagicMock()
    client.list_files.return_value = []
    client.base_uri = "gs://test-bucket/pdfs/"
    return client


# ═══════════════════════════════════════════════════════════════════════════
# run_retry_failed_pdfs
# ═══════════════════════════════════════════════════════════════════════════


class TestRunRetryFailedPdfs:

    def test_no_eligible(self, get_session, gcs):
        """No eligible rows returns zero stats."""
        with patch("src.tasks.retry_failed_pdfs.FetchPdfFailuresRepository") as MockRepo:
            repo = MagicMock()
            repo.get_eligible_for_retry.return_value = []
            repo.get_alert_pending.return_value = []
            MockRepo.return_value = repo

            stats = _run(run_retry_failed_pdfs(get_session, gcs))

            assert stats["fetched"] == 0
            assert stats["succeeded"] == 0

    def test_success_deletes(self, get_session, gcs):
        """Successful fetch deletes row."""
        rows = [{"paper_id": "p1", "title": "T", "fetch_url": "url", "timeout_sec": 120, "fail_runs": 1, "status": "download_failed"}]

        with patch("src.tasks.retry_failed_pdfs.FetchPdfFailuresRepository") as MockRepo:
            repo = MagicMock()
            repo.get_eligible_for_retry.return_value = rows
            repo.get_alert_pending.return_value = []
            MockRepo.return_value = repo

            with patch("src.tasks.retry_failed_pdfs.PDFFetcher") as MockFetcher:
                fetcher = MagicMock()
                fetcher.fetch_from_url_and_upload = AsyncMock(
                    return_value=FetchResult(paper_id="p1", title="T", status="uploaded", gcs_uri="gs://b/p1.pdf")
                )
                MockFetcher.return_value = fetcher

                stats = _run(run_retry_failed_pdfs(get_session, gcs))

                assert stats["succeeded"] == 1
                repo.delete.assert_called_once_with("p1")

    def test_failure_updates(self, get_session, gcs):
        """Failed retry updates row with incremented fail_runs."""
        rows = [{"paper_id": "p1", "title": "T", "fetch_url": "url", "timeout_sec": 120, "fail_runs": 2, "status": "download_failed"}]

        with patch("src.tasks.retry_failed_pdfs.FetchPdfFailuresRepository") as MockRepo:
            repo = MagicMock()
            repo.get_eligible_for_retry.return_value = rows
            repo.get_alert_pending.return_value = []
            MockRepo.return_value = repo

            with patch("src.tasks.retry_failed_pdfs.PDFFetcher") as MockFetcher:
                fetcher = MagicMock()
                fetcher.fetch_from_url_and_upload = AsyncMock(
                    return_value=FetchResult(paper_id="p1", title="T", status="download_failed", error="Timeout", response_code=500)
                )
                MockFetcher.return_value = fetcher

                stats = _run(run_retry_failed_pdfs(get_session, gcs))

                assert stats["failed"] == 1
                repo.update_after_failure.assert_called_once()
                assert repo.update_after_failure.call_args.kwargs["fail_runs"] == 3

    def test_404_deletes_normal(self, get_session, gcs):
        """404 deletes non-gcs_upload_failed rows."""
        rows = [{"paper_id": "p1", "title": "T", "fetch_url": "url", "timeout_sec": 120, "fail_runs": 2, "status": "download_failed"}]

        with patch("src.tasks.retry_failed_pdfs.FetchPdfFailuresRepository") as MockRepo:
            repo = MagicMock()
            repo.get_eligible_for_retry.return_value = rows
            repo.get_alert_pending.return_value = []
            MockRepo.return_value = repo

            with patch("src.tasks.retry_failed_pdfs.PDFFetcher") as MockFetcher:
                fetcher = MagicMock()
                fetcher.fetch_from_url_and_upload = AsyncMock(
                    return_value=FetchResult(paper_id="p1", title="T", status="download_failed", response_code=404)
                )
                MockFetcher.return_value = fetcher

                stats = _run(run_retry_failed_pdfs(get_session, gcs))

                assert stats["deleted_403_404"] == 1
                repo.delete.assert_called_once_with("p1")

    def test_403_deletes_normal(self, get_session, gcs):
        """403 also deletes non-gcs_upload_failed rows."""
        rows = [{"paper_id": "p1", "title": "T", "fetch_url": "url", "timeout_sec": 120, "fail_runs": 2, "status": "download_failed"}]

        with patch("src.tasks.retry_failed_pdfs.FetchPdfFailuresRepository") as MockRepo:
            repo = MagicMock()
            repo.get_eligible_for_retry.return_value = rows
            repo.get_alert_pending.return_value = []
            MockRepo.return_value = repo

            with patch("src.tasks.retry_failed_pdfs.PDFFetcher") as MockFetcher:
                fetcher = MagicMock()
                fetcher.fetch_from_url_and_upload = AsyncMock(
                    return_value=FetchResult(paper_id="p1", title="T", status="download_failed", response_code=403)
                )
                MockFetcher.return_value = fetcher

                stats = _run(run_retry_failed_pdfs(get_session, gcs))

                assert stats["deleted_403_404"] == 1

    def test_404_keeps_gcs_failed(self, get_session, gcs):
        """gcs_upload_failed NOT deleted on 404, only updated."""
        rows = [{"paper_id": "p1", "title": "T", "fetch_url": "url", "timeout_sec": 120, "fail_runs": 2, "status": "gcs_upload_failed"}]

        with patch("src.tasks.retry_failed_pdfs.FetchPdfFailuresRepository") as MockRepo:
            repo = MagicMock()
            repo.get_eligible_for_retry.return_value = rows
            repo.get_alert_pending.return_value = []
            MockRepo.return_value = repo

            with patch("src.tasks.retry_failed_pdfs.PDFFetcher") as MockFetcher:
                fetcher = MagicMock()
                fetcher.fetch_from_url_and_upload = AsyncMock(
                    return_value=FetchResult(paper_id="p1", title="T", status="download_failed", response_code=404)
                )
                MockFetcher.return_value = fetcher

                stats = _run(run_retry_failed_pdfs(get_session, gcs))

                assert stats["deleted_403_404"] == 0
                repo.update_after_failure.assert_called_once()

    def test_alerts_high_fail_runs(self, get_session, gcs):
        """Rows with fail_runs > 5 trigger alerts."""
        pending = [{"paper_id": "p1", "fail_runs": 6}, {"paper_id": "p2", "fail_runs": 10}]

        with patch("src.tasks.retry_failed_pdfs.FetchPdfFailuresRepository") as MockRepo:
            repo = MagicMock()
            repo.get_eligible_for_retry.return_value = []
            repo.get_alert_pending.return_value = pending
            MockRepo.return_value = repo

            callback = MagicMock()
            stats = _run(run_retry_failed_pdfs(get_session, gcs, on_alert=callback))

            assert stats["alerted"] == 2
            callback.assert_called_once_with(pending)
            repo.mark_alerted.assert_called_once()

    def test_mixed_results(self, get_session, gcs):
        """Handles batch with mixed results."""
        rows = [
            {"paper_id": "p1", "title": "T1", "fetch_url": "u1", "timeout_sec": 120, "fail_runs": 1, "status": "download_failed"},
            {"paper_id": "p2", "title": "T2", "fetch_url": "u2", "timeout_sec": 120, "fail_runs": 1, "status": "download_failed"},
            {"paper_id": "p3", "title": "T3", "fetch_url": "u3", "timeout_sec": 120, "fail_runs": 1, "status": "download_failed"},
        ]
        results = [
            FetchResult(paper_id="p1", title="T1", status="uploaded"),
            FetchResult(paper_id="p2", title="T2", status="download_failed", response_code=404),
            FetchResult(paper_id="p3", title="T3", status="download_failed", error="timeout"),
        ]

        with patch("src.tasks.retry_failed_pdfs.FetchPdfFailuresRepository") as MockRepo:
            repo = MagicMock()
            repo.get_eligible_for_retry.return_value = rows
            repo.get_alert_pending.return_value = []
            MockRepo.return_value = repo

            idx = [0]
            with patch("src.tasks.retry_failed_pdfs.PDFFetcher") as MockFetcher:
                fetcher = MagicMock()

                async def side_effect(*args, **kwargs):
                    r = results[idx[0]]
                    idx[0] += 1
                    return r

                fetcher.fetch_from_url_and_upload = AsyncMock(side_effect=side_effect)
                MockFetcher.return_value = fetcher

                stats = _run(run_retry_failed_pdfs(get_session, gcs))

                assert stats["succeeded"] == 1
                assert stats["failed"] == 2
                assert stats["deleted_403_404"] == 1


# ═══════════════════════════════════════════════════════════════════════════
# _reconcile_with_gcs
# ═══════════════════════════════════════════════════════════════════════════


class TestReconcileWithGcs:

    def test_deletes_matching(self):
        """Deletes rows whose PDFs exist in GCS."""
        session = MagicMock()
        repo = MagicMock()
        repo.delete_by_paper_ids.return_value = 2

        gcs = MagicMock()
        gcs.list_files.return_value = [{"filename": "p1.pdf"}, {"filename": "p2.pdf"}]

        _reconcile_with_gcs(session, repo, gcs)

        ids = repo.delete_by_paper_ids.call_args[0][0]
        assert "p1" in ids
        assert "p2" in ids

    def test_empty_gcs(self):
        """No files in GCS returns 0."""
        session = MagicMock()
        repo = MagicMock()
        gcs = MagicMock()
        gcs.list_files.return_value = []

        assert _reconcile_with_gcs(session, repo, gcs) == 0
        repo.delete_by_paper_ids.assert_not_called()

    def test_filters_non_pdf(self):
        """Only .pdf files considered."""
        session = MagicMock()
        repo = MagicMock()
        repo.delete_by_paper_ids.return_value = 1

        gcs = MagicMock()
        gcs.list_files.return_value = [{"filename": "p1.pdf"}, {"filename": "p2.txt"}]

        _reconcile_with_gcs(session, repo, gcs)

        ids = repo.delete_by_paper_ids.call_args[0][0]
        assert "p1" in ids
        assert "p2" not in ids


# ═══════════════════════════════════════════════════════════════════════════
# _send_alert_email
# ═══════════════════════════════════════════════════════════════════════════


class TestSendAlertEmail:

    def test_no_smtp(self):
        """Returns False when SMTP not configured."""
        with patch("src.tasks.retry_failed_pdfs.send_alert_email") as mock:
            mock.return_value = False
            assert _send_alert_email([{"paper_id": "p1"}]) is False

    def test_success(self):
        """Returns True on success."""
        with patch("src.tasks.retry_failed_pdfs.settings") as s:
            s.smtp_host = "smtp.example.com"
            s.alert_email_to = "admin@example.com"

            with patch("src.tasks.retry_failed_pdfs.send_alert_email") as mock:
                mock.return_value = True
                assert _send_alert_email([{"paper_id": "p1", "fail_runs": 6}]) is True


# ═══════════════════════════════════════════════════════════════════════════
# _default_alert
# ═══════════════════════════════════════════════════════════════════════════


class TestDefaultAlert:

    def test_logs_on_email_fail(self):
        """Logs when email fails."""
        with patch("src.tasks.retry_failed_pdfs._send_alert_email") as mock_send:
            mock_send.return_value = False

            with patch("src.tasks.retry_failed_pdfs.logger") as logger:
                rows = [{"paper_id": "p1", "title": "T", "fail_runs": 6, "reason": "err", "fetch_url": "url"}]
                _default_alert(rows)
                assert logger.warning.call_count >= 1

    def test_no_log_on_success(self):
        """No warning log when email succeeds."""
        with patch("src.tasks.retry_failed_pdfs._send_alert_email") as mock_send:
            mock_send.return_value = True

            with patch("src.tasks.retry_failed_pdfs.logger") as logger:
                _default_alert([{"paper_id": "p1", "fail_runs": 6}])
                # Should not log "fail_runs > 5" warning
                for call in logger.warning.call_args_list:
                    assert "fail_runs > 5" not in str(call)


# ═══════════════════════════════════════════════════════════════════════════
# _reconcile_and_alert
# ═══════════════════════════════════════════════════════════════════════════


class TestReconcileAndAlert:

    def test_runs_both(self):
        """Runs reconciliation and alerts."""
        session = MagicMock()
        repo = MagicMock()
        repo.get_alert_pending.return_value = []
        gcs = MagicMock()
        gcs.list_files.return_value = []

        stats = {"reconciled": 0, "alerted": 0}
        _reconcile_and_alert(session, repo, gcs, stats, None)

        gcs.list_files.assert_called_once()
        repo.get_alert_pending.assert_called_once()

    def test_uses_callback(self):
        """Uses provided on_alert callback."""
        session = MagicMock()
        repo = MagicMock()
        pending = [{"paper_id": "p1", "fail_runs": 7}]
        repo.get_alert_pending.return_value = pending
        gcs = MagicMock()
        gcs.list_files.return_value = []

        stats = {"reconciled": 0, "alerted": 0}
        callback = MagicMock()

        _reconcile_and_alert(session, repo, gcs, stats, callback)

        callback.assert_called_once_with(pending)
        assert stats["alerted"] == 1


# ═══════════════════════════════════════════════════════════════════════════
# Edge Cases
# ═══════════════════════════════════════════════════════════════════════════


class TestEdgeCases:

    def test_reason_truncated(self, get_session, gcs):
        """Long reason truncated to 64 chars."""
        rows = [{"paper_id": "p1", "title": "T", "fetch_url": "url", "timeout_sec": 120, "fail_runs": 1, "status": "download_failed"}]

        with patch("src.tasks.retry_failed_pdfs.FetchPdfFailuresRepository") as MockRepo:
            repo = MagicMock()
            repo.get_eligible_for_retry.return_value = rows
            repo.get_alert_pending.return_value = []
            MockRepo.return_value = repo

            with patch("src.tasks.retry_failed_pdfs.PDFFetcher") as MockFetcher:
                fetcher = MagicMock()
                fetcher.fetch_from_url_and_upload = AsyncMock(
                    return_value=FetchResult(paper_id="p1", title="T", status="download_failed", error="X" * 200)
                )
                MockFetcher.return_value = fetcher

                _run(run_retry_failed_pdfs(get_session, gcs))

                reason = repo.update_after_failure.call_args.kwargs["reason"]
                assert len(reason) == 64

    def test_empty_fetch_url(self, get_session, gcs):
        """Handles empty fetch_url."""
        rows = [{"paper_id": "p1", "title": "T", "fetch_url": "", "timeout_sec": 120, "fail_runs": 1, "status": "download_failed"}]

        with patch("src.tasks.retry_failed_pdfs.FetchPdfFailuresRepository") as MockRepo:
            repo = MagicMock()
            repo.get_eligible_for_retry.return_value = rows
            repo.get_alert_pending.return_value = []
            MockRepo.return_value = repo

            with patch("src.tasks.retry_failed_pdfs.PDFFetcher") as MockFetcher:
                fetcher = MagicMock()
                fetcher.fetch_from_url_and_upload = AsyncMock(
                    return_value=FetchResult(paper_id="p1", title="T", status="download_failed", fetch_url="resolved")
                )
                MockFetcher.return_value = fetcher

                stats = _run(run_retry_failed_pdfs(get_session, gcs))
                assert stats["failed"] == 1
