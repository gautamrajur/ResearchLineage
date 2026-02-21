"""Unit tests for src.database.repositories (PaperRepository, AuthorRepository, CitationRepository)."""
from unittest.mock import MagicMock

import pytest

from src.database.repositories import (
    PaperRepository,
    AuthorRepository,
    CitationRepository,
)


@pytest.fixture
def mock_session():
    """Session that records execute calls."""
    session = MagicMock()
    return session


class TestPaperRepository:
    def test_bulk_upsert_empty_returns_zero(self, mock_session):
        repo = PaperRepository(mock_session)
        result = repo.bulk_upsert([])
        assert result == 0
        mock_session.execute.assert_not_called()

    def test_bulk_upsert_calls_execute_per_paper(self, mock_session):
        repo = PaperRepository(mock_session)
        papers = [
            {
                "paperId": "p1",
                "arxivId": None,
                "title": "Paper 1",
                "abstract": "Abstract 1",
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
            {
                "paperId": "p2",
                "arxivId": "2001.00001",
                "title": "Paper 2",
                "abstract": "Abstract 2",
                "year": 2019,
                "citationCount": 5,
                "influentialCitationCount": 0,
                "referenceCount": 3,
                "venue": "ICML",
                "urls": [],
                "first_queried_at": None,
                "query_count": 1,
                "text_availability": None,
            },
        ]
        result = repo.bulk_upsert(papers)
        assert result == 2
        assert mock_session.execute.call_count == 2

    def test_bulk_upsert_returns_count(self, mock_session):
        repo = PaperRepository(mock_session)
        papers = [{"paperId": "p1", "arxivId": None, "title": "T", "abstract": "", "year": 2020,
                   "citationCount": 0, "influentialCitationCount": 0, "referenceCount": 0,
                   "venue": "", "urls": [], "first_queried_at": None, "query_count": 1, "text_availability": None}]
        result = repo.bulk_upsert(papers)
        assert result == 1


class TestAuthorRepository:
    def test_bulk_insert_empty_returns_zero(self, mock_session):
        repo = AuthorRepository(mock_session)
        result = repo.bulk_insert([])
        assert result == 0
        mock_session.execute.assert_not_called()

    def test_bulk_insert_calls_execute_per_author(self, mock_session):
        repo = AuthorRepository(mock_session)
        authors = [
            {"paper_id": "p1", "author_id": "a1", "author_name": "Alice"},
            {"paper_id": "p1", "author_id": "a2", "author_name": "Bob"},
        ]
        result = repo.bulk_insert(authors)
        assert result == 2
        assert mock_session.execute.call_count == 2

    def test_bulk_insert_returns_count(self, mock_session):
        repo = AuthorRepository(mock_session)
        authors = [{"paper_id": "p1", "author_id": "a1", "author_name": "Alice"}]
        result = repo.bulk_insert(authors)
        assert result == 1


class TestCitationRepository:
    def test_bulk_upsert_empty_returns_zero(self, mock_session):
        repo = CitationRepository(mock_session)
        result = repo.bulk_upsert([])
        assert result == 0
        mock_session.execute.assert_not_called()

    def test_bulk_upsert_calls_execute_per_citation(self, mock_session):
        repo = CitationRepository(mock_session)
        citations = [
            {"fromPaperId": "p1", "toPaperId": "p2", "timestamp": None, "isInfluential": False, "contexts": [], "intents": [], "direction": "out"},
            {"fromPaperId": "p2", "toPaperId": "p1", "timestamp": None, "isInfluential": True, "contexts": [], "intents": [], "direction": "in"},
        ]
        result = repo.bulk_upsert(citations)
        assert result == 2
        assert mock_session.execute.call_count == 2

    def test_bulk_upsert_defaults_contexts_and_intents(self, mock_session):
        repo = CitationRepository(mock_session)
        citations = [
            {"fromPaperId": "p1", "toPaperId": "p2"},
        ]
        repo.bulk_upsert(citations)
        call_args = mock_session.execute.call_args[0][1]
        assert call_args.get("contexts") == []
        assert call_args.get("intents") == []

    def test_bulk_upsert_preserves_contexts_and_intents(self, mock_session):
        repo = CitationRepository(mock_session)
        citations = [
            {"fromPaperId": "p1", "toPaperId": "p2", "contexts": ["ctx"], "intents": ["intent"]},
        ]
        repo.bulk_upsert(citations)
        call_args = mock_session.execute.call_args[0][1]
        assert call_args.get("contexts") == ["ctx"]
        assert call_args.get("intents") == ["intent"]
