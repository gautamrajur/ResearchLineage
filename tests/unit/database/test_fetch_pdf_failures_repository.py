"""Unit tests for src.database.fetch_pdf_failures_repository."""
import pytest
from unittest.mock import MagicMock
from datetime import datetime

from src.database.fetch_pdf_failures_repository import (
    FetchPdfFailuresRepository,
    _row_to_dict,
    TIMEOUT_BUMP_SECONDS,
)


@pytest.fixture
def session():
    """Mock database session."""
    return MagicMock()


@pytest.fixture
def repo(session):
    """Repository with mocked session."""
    return FetchPdfFailuresRepository(session)


# ═══════════════════════════════════════════════════════════════════════════
# get_by_paper_ids
# ═══════════════════════════════════════════════════════════════════════════


class TestGetByPaperIds:

    def test_empty_list(self, repo, session):
        """Empty input returns empty without DB call."""
        assert repo.get_by_paper_ids([]) == []
        session.execute.assert_not_called()

    def test_single_id(self, repo, session):
        """Returns row for single paper_id."""
        row = MagicMock()
        row._mapping = {"paper_id": "p1", "fail_runs": 2}
        session.execute.return_value.fetchall.return_value = [row]

        result = repo.get_by_paper_ids(["p1"])

        assert len(result) == 1
        assert result[0]["paper_id"] == "p1"

    def test_multiple_ids(self, repo, session):
        """Handles multiple paper_ids in single call."""
        rows = [MagicMock(_mapping={"paper_id": f"p{i}"}) for i in range(3)]
        session.execute.return_value.fetchall.return_value = rows

        result = repo.get_by_paper_ids(["p0", "p1", "p2"])

        assert len(result) == 3
        session.execute.assert_called_once()


# ═══════════════════════════════════════════════════════════════════════════
# get_eligible_for_retry
# ═══════════════════════════════════════════════════════════════════════════


class TestGetEligibleForRetry:

    def test_returns_eligible(self, repo, session):
        """Returns rows where retry_after passed and alerted=FALSE."""
        row = MagicMock()
        row._mapping = {"paper_id": "p1", "alerted": False}
        session.execute.return_value.fetchall.return_value = [row]

        result = repo.get_eligible_for_retry()

        assert len(result) == 1
        assert result[0]["alerted"] is False

    def test_empty_when_none(self, repo, session):
        """Returns empty when no eligible rows."""
        session.execute.return_value.fetchall.return_value = []
        assert repo.get_eligible_for_retry() == []

    def test_orders_by_last_attempt(self, repo, session):
        """Query orders by last_attempt_at."""
        session.execute.return_value.fetchall.return_value = []
        repo.get_eligible_for_retry()

        query = str(session.execute.call_args[0][0])
        assert "ORDER BY last_attempt_at" in query


# ═══════════════════════════════════════════════════════════════════════════
# insert
# ═══════════════════════════════════════════════════════════════════════════


class TestInsert:

    def test_basic(self, repo, session):
        """Insert creates row with correct params."""
        repo.insert({
            "paper_id": "abc123",
            "title": "Test",
            "status": "download_failed",
            "fetch_url": "https://example.com/p.pdf",
            "reason": "HTTP 404",
            "timeout_sec": 120.0,
        })

        session.execute.assert_called_once()
        params = session.execute.call_args[0][1]
        assert params["paper_id"] == "abc123"
        assert params["timeout_sec"] == 120.0

    def test_defaults(self, repo, session):
        """Missing fields get defaults."""
        repo.insert({"paper_id": "abc123"})

        params = session.execute.call_args[0][1]
        assert params["title"] == ""
        assert params["status"] == "download_failed"
        assert params["fetch_url"] == ""
        assert params["reason"] == ""


# ═══════════════════════════════════════════════════════════════════════════
# upsert
# ═══════════════════════════════════════════════════════════════════════════


class TestUpsert:

    def test_conflict_clause(self, repo, session):
        """Query has ON CONFLICT clause."""
        repo.upsert({"paper_id": "abc123", "title": "T", "status": "download_failed"})

        query = str(session.execute.call_args[0][0])
        assert "ON CONFLICT (paper_id) DO UPDATE" in query
        assert "fail_runs = fetch_pdf_failures.fail_runs + 1" in query

    def test_all_fields(self, repo, session):
        """All fields passed correctly."""
        repo.upsert({
            "paper_id": "p1",
            "title": "Title",
            "status": "gcs_upload_failed",
            "fetch_url": "url",
            "reason": "GCS timeout",
            "timeout_sec": 150.0,
        })

        params = session.execute.call_args[0][1]
        assert params["status"] == "gcs_upload_failed"
        assert params["timeout_sec"] == 150.0

    def test_none_to_defaults(self, repo, session):
        """None values converted to defaults."""
        repo.upsert({"paper_id": "p1", "title": None, "status": None})

        params = session.execute.call_args[0][1]
        assert params["title"] == ""
        assert params["status"] == "download_failed"


# ═══════════════════════════════════════════════════════════════════════════
# update_after_failure
# ═══════════════════════════════════════════════════════════════════════════


class TestUpdateAfterFailure:

    def test_bumps_timeout(self, repo, session):
        """Adds TIMEOUT_BUMP_SECONDS to timeout."""
        repo.update_after_failure(
            paper_id="p1", fail_runs=3, fetch_url="url",
            reason="timeout", timeout_sec=120.0
        )

        params = session.execute.call_args[0][1]
        assert params["timeout_sec"] == 120.0 + TIMEOUT_BUMP_SECONDS

    def test_sets_retry_after(self, repo, session):
        """Sets retry_after = NOW() + 30s."""
        repo.update_after_failure(
            paper_id="p1", fail_runs=5, fetch_url="url",
            reason="err", timeout_sec=100.0
        )

        query = str(session.execute.call_args[0][0])
        assert "retry_after = NOW() + INTERVAL '30 seconds'" in query

    def test_passes_all_params(self, repo, session):
        """All parameters passed correctly."""
        repo.update_after_failure(
            paper_id="p1", fail_runs=4, fetch_url="https://arxiv.org/pdf/1234.pdf",
            reason="HTTP 503", timeout_sec=150.0
        )

        params = session.execute.call_args[0][1]
        assert params["paper_id"] == "p1"
        assert params["fail_runs"] == 4
        assert params["reason"] == "HTTP 503"


# ═══════════════════════════════════════════════════════════════════════════
# delete
# ═══════════════════════════════════════════════════════════════════════════


class TestDelete:

    def test_single(self, repo, session):
        """Deletes by paper_id."""
        repo.delete("abc123")

        session.execute.assert_called_once()
        params = session.execute.call_args[0][1]
        assert params["paper_id"] == "abc123"


# ═══════════════════════════════════════════════════════════════════════════
# delete_by_paper_ids
# ═══════════════════════════════════════════════════════════════════════════


class TestDeleteByPaperIds:

    def test_empty_list(self, repo, session):
        """Empty list returns 0 without DB call."""
        assert repo.delete_by_paper_ids([]) == 0
        session.execute.assert_not_called()

    def test_returns_count(self, repo, session):
        """Returns rowcount."""
        session.execute.return_value.rowcount = 3
        assert repo.delete_by_paper_ids(["p1", "p2", "p3"]) == 3

    def test_uses_any_operator(self, repo, session):
        """Query uses ANY operator."""
        session.execute.return_value.rowcount = 2
        repo.delete_by_paper_ids(["p1", "p2"])

        query = str(session.execute.call_args[0][0])
        assert "paper_id = ANY(:paper_ids)" in query

    def test_missing_rowcount(self, repo, session):
        """Returns 0 when rowcount missing."""
        session.execute.return_value = MagicMock(spec=[])
        assert repo.delete_by_paper_ids(["p1"]) == 0


# ═══════════════════════════════════════════════════════════════════════════
# get_alert_pending
# ═══════════════════════════════════════════════════════════════════════════


class TestGetAlertPending:

    def test_returns_high_fail_runs(self, repo, session):
        """Returns rows where fail_runs > 5 and alerted=FALSE."""
        row = MagicMock()
        row._mapping = {"paper_id": "p1", "fail_runs": 7, "alerted": False}
        session.execute.return_value.fetchall.return_value = [row]

        result = repo.get_alert_pending()

        assert len(result) == 1
        assert result[0]["fail_runs"] == 7

    def test_query_filters(self, repo, session):
        """Query filters by fail_runs > 5 AND alerted = FALSE."""
        session.execute.return_value.fetchall.return_value = []
        repo.get_alert_pending()

        query = str(session.execute.call_args[0][0])
        assert "fail_runs > 5" in query
        assert "alerted = FALSE" in query


# ═══════════════════════════════════════════════════════════════════════════
# mark_alerted
# ═══════════════════════════════════════════════════════════════════════════


class TestMarkAlerted:

    def test_empty_noop(self, repo, session):
        """Empty list does nothing."""
        repo.mark_alerted([])
        session.execute.assert_not_called()

    def test_sets_alerted(self, repo, session):
        """Sets alerted=TRUE for paper_ids."""
        repo.mark_alerted(["p1", "p2"])

        session.execute.assert_called_once()
        params = session.execute.call_args[0][1]
        assert set(params["paper_ids"]) == {"p1", "p2"}


# ═══════════════════════════════════════════════════════════════════════════
# _row_to_dict
# ═══════════════════════════════════════════════════════════════════════════


class TestRowToDict:

    def test_with_mapping(self):
        """Converts row with _mapping."""
        row = MagicMock(_mapping={"paper_id": "p1", "title": "T"})
        assert _row_to_dict(row) == {"paper_id": "p1", "title": "T"}

    def test_without_mapping(self):
        """Handles dict-like row."""
        row = {"paper_id": "p1"}
        assert _row_to_dict(row)["paper_id"] == "p1"


# ═══════════════════════════════════════════════════════════════════════════
# Edge Cases
# ═══════════════════════════════════════════════════════════════════════════


class TestEdgeCases:

    def test_long_paper_id(self, repo, session):
        """Handles very long paper_id."""
        long_id = "a" * 500
        repo.insert({"paper_id": long_id})
        assert session.execute.call_args[0][1]["paper_id"] == long_id

    def test_unicode(self, repo, session):
        """Handles Unicode in title and reason."""
        repo.upsert({
            "paper_id": "p1",
            "title": "日本語論文 🔬",
            "reason": "エラー: タイムアウト",
        })
        params = session.execute.call_args[0][1]
        assert "日本語" in params["title"]

    def test_special_chars_url(self, repo, session):
        """Preserves special chars in URL."""
        repo.upsert({
            "paper_id": "p1",
            "fetch_url": "https://example.com/paper?id=123&type=pdf#s1",
        })
        url = session.execute.call_args[0][1]["fetch_url"]
        assert all(c in url for c in ["?", "&", "#"])

    def test_zero_timeout(self, repo, session):
        """Zero timeout bumps correctly."""
        repo.update_after_failure(
            paper_id="p1", fail_runs=1, fetch_url="",
            reason="", timeout_sec=0.0
        )
        assert session.execute.call_args[0][1]["timeout_sec"] == TIMEOUT_BUMP_SECONDS

    def test_large_paper_ids_list(self, repo, session):
        """Handles 1000 paper_ids."""
        ids = [f"p{i}" for i in range(1000)]
        session.execute.return_value.rowcount = 1000

        assert repo.delete_by_paper_ids(ids) == 1000
        assert len(session.execute.call_args[0][1]["paper_ids"]) == 1000
