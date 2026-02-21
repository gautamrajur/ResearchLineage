"""Unit tests for src.tasks.data_acquisition (DataAcquisitionTask)."""
import asyncio
from unittest.mock import AsyncMock

import pytest

from src.tasks.data_acquisition import DataAcquisitionTask
from src.utils.errors import APIError, ValidationError


def _run(coro):
    return asyncio.run(coro)


def _mock_paper(pid: str, title: str = "Test", refs: int = 5, cits: int = 10):
    return {
        "paperId": pid,
        "title": title,
        "year": 2020,
        "citationCount": cits,
        "influentialCitationCount": 2,
        "referenceCount": refs,
        "authors": [{"authorId": "a1", "name": "Author"}],
        "externalIds": {"DOI": f"10.1234/{pid}"},
        "venue": "NeurIPS",
    }


@pytest.fixture
def task():
    t = DataAcquisitionTask()
    t.api_client = AsyncMock()
    t.openalex_client = AsyncMock()
    return t


class TestDataAcquisitionInputValidation:
    def test_empty_paper_id_raises(self, task):
        with pytest.raises(ValidationError, match="Invalid paper_id"):
            _run(task.execute("", max_depth=1, direction="backward"))

    def test_invalid_direction_raises(self, task):
        with pytest.raises(ValidationError, match="Invalid direction"):
            _run(task.execute("abc", max_depth=1, direction="invalid"))

    def test_max_depth_zero_raises(self, task):
        # execute() does max_depth = max_depth or settings.max_citation_depth, so 0 becomes default; validate _validate_inputs directly
        with pytest.raises(ValidationError, match="Invalid max_depth"):
            task._validate_inputs("abc", 0, "backward")

    def test_max_depth_over_5_raises(self, task):
        with pytest.raises(ValidationError, match="Invalid max_depth"):
            _run(task.execute("abc", max_depth=6, direction="backward"))


class TestDataAcquisitionExecute:
    def test_backward_fetches_references(self, task):
        task.api_client.get_paper = AsyncMock(return_value=_mock_paper("p1"))
        task.api_client.get_references = AsyncMock(
            return_value=[
                {
                    "citedPaper": {"paperId": "ref1"},
                    "isInfluential": True,
                    "intents": ["methodology"],
                }
            ]
        )

        result = _run(task.execute("p1", max_depth=1, direction="backward"))

        assert result["target_paper_id"] == "p1"
        assert len(result["papers"]) >= 1
        assert result["direction"] == "backward"
        task.api_client.get_references.assert_called()

    def test_forward_fetches_citations(self, task):
        task.api_client.get_paper = AsyncMock(return_value=_mock_paper("p1"))
        task.api_client.get_citations = AsyncMock(
            return_value=[{"citingPaper": {"paperId": "cit1"}, "isInfluential": False}]
        )

        result = _run(task.execute("p1", max_depth=1, direction="forward"))

        assert result["direction"] == "forward"
        task.api_client.get_citations.assert_called()

    def test_both_fetches_references_and_citations(self, task):
        task.api_client.get_paper = AsyncMock(return_value=_mock_paper("p1"))
        task.api_client.get_references = AsyncMock(return_value=[])
        task.api_client.get_citations = AsyncMock(return_value=[])

        result = _run(task.execute("p1", max_depth=1, direction="both"))

        assert result["direction"] == "both"
        task.api_client.get_references.assert_called()
        task.api_client.get_citations.assert_called()

    def test_no_papers_fetched_raises(self, task):
        task.api_client.get_paper = AsyncMock(side_effect=APIError("404"))

        with pytest.raises(ValidationError, match="No papers fetched"):
            _run(task.execute("nonexistent", max_depth=1, direction="backward"))

    def test_deduplication_skips_already_fetched(self, task):
        task.api_client.get_paper = AsyncMock(
            side_effect=[_mock_paper("p1"), _mock_paper("p2")]
        )
        task.api_client.get_references = AsyncMock(
            side_effect=[
                [
                    {
                        "citedPaper": {"paperId": "p2"},
                        "isInfluential": True,
                        "intents": ["methodology"],
                    }
                ],
                [
                    {
                        "citedPaper": {"paperId": "p1"},
                        "isInfluential": True,
                        "intents": ["methodology"],
                    }
                ],
            ]
        )

        result = _run(task.execute("p1", max_depth=2, direction="backward"))

        assert task.api_client.get_paper.call_count == 2


class TestDataAcquisitionFilterReferences:
    def test_filters_by_intent_and_influence(self, task):
        refs = [
            {
                "citedPaper": {"paperId": "p1", "citationCount": 10},
                "intents": ["methodology"],
                "isInfluential": False,
            },
            {
                "citedPaper": {"paperId": "p2", "citationCount": 5},
                "intents": ["result"],
                "isInfluential": False,
            },
            {
                "citedPaper": {"paperId": "p3", "citationCount": 1},
                "intents": [],
                "isInfluential": True,
            },
            {
                "citedPaper": {"paperId": "p4", "citationCount": 100},
                "intents": [],
                "isInfluential": False,
            },
        ]

        filtered = task._filter_references_for_recursion(refs)

        pids = [r["citedPaper"]["paperId"] for r in filtered]
        assert "p1" in pids
        assert "p3" in pids
        assert "p4" not in pids


class TestDataAcquisitionClose:
    def test_close_closes_both_clients(self, task):
        task.api_client.close = AsyncMock()
        task.openalex_client.close = AsyncMock()

        _run(task.close())

        task.api_client.close.assert_called_once()
        task.openalex_client.close.assert_called_once()
