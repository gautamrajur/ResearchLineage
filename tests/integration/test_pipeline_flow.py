"""
Integration test: DataAcquisition (mocked) → Validation → Cleaning → Graph.

Uses fixture data for acquisition output so no real API calls are made.
Verifies the pipeline flow and data shape through each stage.

Tests that run CitationGraphConstructionTask are skipped unless
RUN_CITATION_GRAPH_TESTS=1 (numpy.linalg can segfault in some envs).
"""
import os
import pytest

from src.tasks.data_validation import DataValidationTask
from src.tasks.data_cleaning import DataCleaningTask
from src.tasks.citation_graph_construction import CitationGraphConstructionTask

RUN_GRAPH_TESTS = os.environ.get("RUN_CITATION_GRAPH_TESTS") == "1"


def _paper(paper_id: str, title: str = "Test", year: int = 2020):
    return {
        "paperId": paper_id,
        "title": title,
        "year": year,
        "citationCount": 10,
        "influentialCitationCount": 1,
        "referenceCount": 5,
        "authors": [{"authorId": "a1", "name": "Author"}],
        "externalIds": {},
        "venue": "NeurIPS",
    }


def _ref(fr: str, to: str):
    return {"fromPaperId": fr, "toPaperId": to, "isInfluential": False, "contexts": [], "intents": []}


def _cit(fr: str, to: str):
    return {"fromPaperId": fr, "toPaperId": to, "isInfluential": False}


@pytest.fixture
def raw_data_from_acquisition():
    """Simulated output of DataAcquisitionTask.execute (mocked APIs)."""
    return {
        "target_paper_id": "target",
        "papers": [
            _paper("target", "Target Paper"),
            _paper("p2", "Paper 2", 2019),
            _paper("p3", "Paper 3", 2021),
        ],
        "references": [_ref("target", "p2")],
        "citations": [_cit("p3", "target")],
    }


class TestPipelineFlow:
    """Run validation → cleaning (and optionally graph) with fixture data."""

    def test_validation_then_cleaning_produces_cleaned_data(self, raw_data_from_acquisition):
        """Validation → Cleaning only (no graph). Always runs."""
        validation = DataValidationTask()
        cleaning = DataCleaningTask()

        validated = validation.execute(raw_data_from_acquisition)
        assert "papers" in validated
        assert "references" in validated
        assert "citations" in validated
        assert validated["target_paper_id"] == "target"

        cleaned = cleaning.execute(validated)
        assert "papers" in cleaned
        assert "references" in cleaned
        assert "citations" in cleaned
        assert "cleaning_stats" in cleaned
        assert cleaned["target_paper_id"] == "target"

    @pytest.mark.skipif(
        not RUN_GRAPH_TESTS,
        reason="Set RUN_CITATION_GRAPH_TESTS=1 to run (numpy.linalg can segfault in some envs)",
    )
    def test_validation_then_cleaning_then_graph_produces_graph(self, raw_data_from_acquisition):
        validation = DataValidationTask()
        cleaning = DataCleaningTask()
        graph_task = CitationGraphConstructionTask()

        validated = validation.execute(raw_data_from_acquisition)
        cleaned = cleaning.execute(validated)
        graph_data = graph_task.execute(cleaned)

        assert "graph" in graph_data
        assert "metrics" in graph_data
        assert "graph_stats" in graph_data
        assert graph_data["target_paper_id"] == "target"
        assert graph_data["graph"].number_of_nodes() >= 2
        assert graph_data["graph"].number_of_edges() >= 1

    @pytest.mark.skipif(
        not RUN_GRAPH_TESTS,
        reason="Set RUN_CITATION_GRAPH_TESTS=1 to run (numpy.linalg can segfault in some envs)",
    )
    def test_pipeline_preserves_target_paper_through_stages(self, raw_data_from_acquisition):
        validation = DataValidationTask()
        cleaning = DataCleaningTask()
        graph_task = CitationGraphConstructionTask()

        validated = validation.execute(raw_data_from_acquisition)
        cleaned = cleaning.execute(validated)
        graph_data = graph_task.execute(cleaned)

        target_id = raw_data_from_acquisition["target_paper_id"]
        assert graph_data["target_paper_id"] == target_id
        assert target_id in graph_data["graph"]
        assert target_id in graph_data["metrics"]
