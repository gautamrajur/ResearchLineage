"""Unit tests for src.tasks.pdf_failure_sync."""
import pytest
from unittest.mock import MagicMock, patch
from contextlib import contextmanager

from src.tasks.pdf_failure_sync import sync_failures_to_db, _normalize_failure_row


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


# ═══════════════════════════════════════════════════════════════════════════
# sync_failures_to_db
# ═══════════════════════════════════════════════════════════════════════════


class TestSyncFailuresToDb:

    def test_empty_list(self, get_session):
        """Empty list returns 0."""
        assert sync_failures_to_db([], get_session) == 0

    def test_single(self, get_session):
        """Single failure syncs."""
        failures = [{
            "paper_id": "abc123",
            "title": "Test",
            "status": "download_failed",
            "fetch_url": "https://example.com/p.pdf",
            "reason": "HTTP 404",
            "timeout_sec": 120.0,
        }]

        with patch("src.tasks.pdf_failure_sync.FetchPdfFailuresRepository") as MockRepo:
            repo = MagicMock()
            MockRepo.return_value = repo

            result = sync_failures_to_db(failures, get_session)

            assert result == 1
            repo.upsert.assert_called_once()

    def test_multiple(self, get_session):
        """Multiple failures sync with correct count."""
        failures = [
            {"paper_id": "p1", "status": "download_failed"},
            {"paper_id": "p2", "status": "gcs_upload_failed"},
            {"paper_id": "p3", "status": "error"},
        ]

        with patch("src.tasks.pdf_failure_sync.FetchPdfFailuresRepository") as MockRepo:
            repo = MagicMock()
            MockRepo.return_value = repo

            result = sync_failures_to_db(failures, get_session)

            assert result == 3
            assert repo.upsert.call_count == 3

    def test_normalizes_each(self, get_session):
        """Each item is normalized."""
        failures = [{"paper_id": "p1"}, {"paper_id": "p2"}]

        with patch("src.tasks.pdf_failure_sync.FetchPdfFailuresRepository") as MockRepo:
            repo = MagicMock()
            MockRepo.return_value = repo

            with patch("src.tasks.pdf_failure_sync._normalize_failure_row") as mock_norm:
                mock_norm.side_effect = lambda x: x
                sync_failures_to_db(failures, get_session)
                assert mock_norm.call_count == 2

    def test_logs_count(self, get_session):
        """Logs number synced."""
        failures = [{"paper_id": "p1"}, {"paper_id": "p2"}]

        with patch("src.tasks.pdf_failure_sync.FetchPdfFailuresRepository") as MockRepo:
            MockRepo.return_value = MagicMock()

            with patch("src.tasks.pdf_failure_sync.logger") as logger:
                sync_failures_to_db(failures, get_session)
                logger.info.assert_called_once()
                assert "2" in str(logger.info.call_args)


# ═══════════════════════════════════════════════════════════════════════════
# _normalize_failure_row
# ═══════════════════════════════════════════════════════════════════════════


class TestNormalizeFailureRow:

    def test_complete(self):
        """Complete row normalized correctly."""
        item = {
            "paper_id": "abc123",
            "title": "Test",
            "status": "download_failed",
            "fetch_url": "https://example.com/p.pdf",
            "reason": "HTTP 404",
            "timeout_sec": 150.0,
        }
        r = _normalize_failure_row(item)

        assert r["paper_id"] == "abc123"
        assert r["title"] == "Test"
        assert r["status"] == "download_failed"
        assert r["timeout_sec"] == 150.0

    def test_defaults(self):
        """Missing fields use defaults."""
        r = _normalize_failure_row({"paper_id": "abc123"})

        assert r["title"] == ""
        assert r["status"] == "download_failed"
        assert r["fetch_url"] == ""
        assert r["reason"] == ""
        assert r["timeout_sec"] == 120.0

    def test_download_failed_timeout(self):
        """download_failed gets 120 default timeout."""
        r = _normalize_failure_row({"paper_id": "p1", "status": "download_failed"})
        assert r["timeout_sec"] == 120.0

    def test_gcs_upload_failed_timeout(self):
        """gcs_upload_failed gets 140 default timeout."""
        r = _normalize_failure_row({"paper_id": "p1", "status": "gcs_upload_failed"})
        assert r["timeout_sec"] == 140.0

    def test_explicit_timeout_wins(self):
        """Explicit timeout overrides default."""
        r = _normalize_failure_row({
            "paper_id": "p1",
            "status": "gcs_upload_failed",
            "timeout_sec": 200.0,
        })
        assert r["timeout_sec"] == 200.0

    def test_error_fallback(self):
        """Uses 'error' field when 'reason' missing."""
        r = _normalize_failure_row({"paper_id": "p1", "error": "Connection timeout"})
        assert r["reason"] == "Connection timeout"

    def test_reason_precedence(self):
        """'reason' takes precedence over 'error'."""
        r = _normalize_failure_row({
            "paper_id": "p1",
            "reason": "HTTP 500",
            "error": "Server error",
        })
        assert r["reason"] == "HTTP 500"

    def test_reason_truncated(self):
        """Reason truncated to 64 chars."""
        r = _normalize_failure_row({"paper_id": "p1", "reason": "X" * 100})
        assert len(r["reason"]) == 64

    def test_error_truncated(self):
        """Error fallback also truncated."""
        r = _normalize_failure_row({"paper_id": "p1", "error": "Y" * 100})
        assert len(r["reason"]) == 64

    def test_none_values(self):
        """None values become empty strings."""
        r = _normalize_failure_row({
            "paper_id": "p1",
            "title": None,
            "status": None,
            "fetch_url": None,
            "reason": None,
        })
        assert r["title"] == ""
        assert r["status"] == "download_failed"
        assert r["fetch_url"] == ""
        assert r["reason"] == ""

    def test_paper_id_to_string(self):
        """paper_id converted to string."""
        r = _normalize_failure_row({"paper_id": 12345})
        assert r["paper_id"] == "12345"
        assert isinstance(r["paper_id"], str)


# ═══════════════════════════════════════════════════════════════════════════
# Edge Cases
# ═══════════════════════════════════════════════════════════════════════════


class TestEdgeCases:

    def test_unicode_title(self):
        """Unicode in title."""
        r = _normalize_failure_row({"paper_id": "p1", "title": "日本語論文 🔬"})
        assert "日本語" in r["title"]

    def test_unicode_reason(self):
        """Unicode in reason."""
        r = _normalize_failure_row({"paper_id": "p1", "reason": "エラー: 接続失敗"})
        assert "エラー" in r["reason"]

    def test_empty_paper_id(self):
        """Empty paper_id."""
        r = _normalize_failure_row({"paper_id": ""})
        assert r["paper_id"] == ""

    def test_whitespace_preserved(self):
        """Whitespace-only fields preserved."""
        r = _normalize_failure_row({
            "paper_id": "p1",
            "title": "   ",
            "reason": "\t\n",
        })
        assert r["title"] == "   "
        assert r["reason"] == "\t\n"

    def test_url_special_chars(self):
        """URL special chars preserved."""
        r = _normalize_failure_row({
            "paper_id": "p1",
            "fetch_url": "https://example.com/p?id=1&type=pdf#s1",
        })
        assert all(c in r["fetch_url"] for c in ["?", "&", "#"])

    def test_int_timeout(self):
        """Integer timeout -> float."""
        r = _normalize_failure_row({"paper_id": "p1", "timeout_sec": 100})
        assert r["timeout_sec"] == 100.0
        assert isinstance(r["timeout_sec"], float)

    def test_string_timeout(self):
        """String timeout -> float."""
        r = _normalize_failure_row({"paper_id": "p1", "timeout_sec": "150"})
        assert r["timeout_sec"] == 150.0
