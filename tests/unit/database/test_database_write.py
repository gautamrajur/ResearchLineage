"""Unit tests for src.tasks.database_write (DatabaseWriteTask) with mocked session."""
from unittest.mock import MagicMock, patch

import pytest

from src.tasks.database_write import DatabaseWriteTask
from src.utils.errors import DatabaseError


@pytest.fixture
def final_data():
    """Minimal final_data as produced by anomaly detection."""
    return {
        "target_paper_id": "target123",
        "papers_table": [
            {
                "paperId": "p1",
                "arxivId": None,
                "title": "Paper 1",
                "abstract": "",
                "year": 2020,
                "citationCount": 10,
                "influentialCitationCount": 2,
                "referenceCount": 5,
                "venue": "NeurIPS",
                "urls": [],
                "first_queried_at": None,
                "query_count": 1,
                "text_availability": None,
            },
        ],
        "authors_table": [
            {"paper_id": "p1", "author_id": "a1", "author_name": "Alice"},
        ],
        "citations_table": [
            {"fromPaperId": "p1", "toPaperId": "p2", "timestamp": None, "isInfluential": False, "contexts": [], "intents": [], "direction": "out"},
        ],
        "quality_report": {"quality_score": 0.9},
        "anomaly_report": {"anomalies": []},
    }


class TestDatabaseWriteTask:
    def test_execute_returns_write_stats(self, final_data):
        mock_session = MagicMock()
        mock_context = MagicMock()
        mock_context.__enter__ = MagicMock(return_value=mock_session)
        mock_context.__exit__ = MagicMock(return_value=None)

        with patch.object(DatabaseWriteTask, "__init__", lambda self: None):
            task = DatabaseWriteTask()
            task.db = MagicMock()
            task.db.get_session.return_value = mock_context

            # Repositories return counts when execute is called
            with patch("src.tasks.database_write.PaperRepository") as MockPaperRepo:
                with patch("src.tasks.database_write.AuthorRepository") as MockAuthorRepo:
                    with patch("src.tasks.database_write.CitationRepository") as MockCitRepo:
                        MockPaperRepo.return_value.bulk_upsert.return_value = len(final_data["papers_table"])
                        MockAuthorRepo.return_value.bulk_insert.return_value = len(final_data["authors_table"])
                        MockCitRepo.return_value.bulk_upsert.return_value = len(final_data["citations_table"])

                        result = task.execute(final_data)

        assert result["target_paper_id"] == "target123"
        assert result["write_stats"]["papers_written"] == 1
        assert result["write_stats"]["authors_written"] == 1
        assert result["write_stats"]["citations_written"] == 1
        assert result["quality_report"] == final_data["quality_report"]
        assert result["anomaly_report"] == final_data["anomaly_report"]

    def test_execute_uses_session_context(self, final_data):
        mock_session = MagicMock()
        mock_context = MagicMock()
        mock_context.__enter__ = MagicMock(return_value=mock_session)
        mock_context.__exit__ = MagicMock(return_value=None)

        with patch.object(DatabaseWriteTask, "__init__", lambda self: None):
            task = DatabaseWriteTask()
            task.db = MagicMock()
            task.db.get_session.return_value = mock_context

            with patch("src.tasks.database_write.PaperRepository") as MockPaperRepo:
                with patch("src.tasks.database_write.AuthorRepository") as MockAuthorRepo:
                    with patch("src.tasks.database_write.CitationRepository") as MockCitRepo:
                        MockPaperRepo.return_value.bulk_upsert.return_value = 1
                        MockAuthorRepo.return_value.bulk_insert.return_value = 1
                        MockCitRepo.return_value.bulk_upsert.return_value = 1

                        task.execute(final_data)

        task.db.get_session.assert_called_once()
        MockPaperRepo.assert_called_once_with(mock_session)
        MockAuthorRepo.assert_called_once_with(mock_session)
        MockCitRepo.assert_called_once_with(mock_session)

    def test_execute_raises_database_error_on_exception(self, final_data):
        mock_context = MagicMock()
        mock_context.__enter__ = MagicMock(side_effect=RuntimeError("Connection failed"))
        mock_context.__exit__ = MagicMock(return_value=None)

        with patch.object(DatabaseWriteTask, "__init__", lambda self: None):
            task = DatabaseWriteTask()
            task.db = MagicMock()
            task.db.get_session.return_value = mock_context

            with pytest.raises(DatabaseError, match="Failed to write to database"):
                task.execute(final_data)

    def test_execute_empty_tables_still_returns_stats(self, final_data):
        final_data["papers_table"] = []
        final_data["authors_table"] = []
        final_data["citations_table"] = []

        mock_session = MagicMock()
        mock_context = MagicMock()
        mock_context.__enter__ = MagicMock(return_value=mock_session)
        mock_context.__exit__ = MagicMock(return_value=None)

        with patch.object(DatabaseWriteTask, "__init__", lambda self: None):
            task = DatabaseWriteTask()
            task.db = MagicMock()
            task.db.get_session.return_value = mock_context

            with patch("src.tasks.database_write.PaperRepository") as MockPaperRepo:
                with patch("src.tasks.database_write.AuthorRepository") as MockAuthorRepo:
                    with patch("src.tasks.database_write.CitationRepository") as MockCitRepo:
                        MockPaperRepo.return_value.bulk_upsert.return_value = 0
                        MockAuthorRepo.return_value.bulk_insert.return_value = 0
                        MockCitRepo.return_value.bulk_upsert.return_value = 0

                        result = task.execute(final_data)

        assert result["write_stats"]["papers_written"] == 0
        assert result["write_stats"]["authors_written"] == 0
        assert result["write_stats"]["citations_written"] == 0
