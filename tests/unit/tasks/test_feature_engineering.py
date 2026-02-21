"""Unit tests for src.tasks.feature_engineering (FeatureEngineeringTask)."""
from datetime import datetime

import pytest

from src.tasks.feature_engineering import FeatureEngineeringTask


def _paper(pid: str, year: int = 2020, cit_count: int = 100, inf_count: int = 5):
    return {
        "paperId": pid,
        "title": f"Paper {pid}",
        "year": year,
        "citationCount": cit_count,
        "influentialCitationCount": inf_count,
    }


@pytest.fixture
def task():
    return FeatureEngineeringTask()


@pytest.fixture
def graph_data():
    return {
        "target_paper_id": "target",
        "papers": [
            _paper("target", 2020, 500, 50),
            _paper("p1", 2015, 1000, 100),
            _paper("p2", 2022, 50, 5),
        ],
        "references": [],
        "citations": [],
        "graph": None,
        "metrics": {
            "target": {"pagerank": 0.5, "betweenness": 0.3, "in_degree": 10, "out_degree": 5},
            "p1": {"pagerank": 0.3, "betweenness": 0.1, "in_degree": 50, "out_degree": 20},
            "p2": {"pagerank": 0.2, "betweenness": 0.0, "in_degree": 2, "out_degree": 10},
        },
        "graph_stats": {},
        "components": {},
    }


class TestFeatureEngineeringExecute:
    def test_adds_graph_metrics_to_papers(self, task, graph_data):
        result = task.execute(graph_data)

        for paper in result["papers"]:
            assert "pagerank" in paper
            assert "betweenness" in paper
            assert "in_degree" in paper
            assert "out_degree" in paper

    def test_computes_paper_age(self, task, graph_data):
        result = task.execute(graph_data)

        current_year = datetime.now().year
        for paper in result["papers"]:
            expected_age = max(1, current_year - paper["year"])
            assert paper["paper_age"] == expected_age

    def test_computes_citation_velocity(self, task, graph_data):
        result = task.execute(graph_data)

        for paper in result["papers"]:
            assert "citation_velocity" in paper
            assert paper["citation_velocity"] >= 0

    def test_computes_temporal_category(self, task, graph_data):
        result = task.execute(graph_data)

        categories = {p["paperId"]: p["temporal_category"] for p in result["papers"]}
        assert categories["p1"] == "recent_predecessor"
        assert categories["p2"] == "subsequent"

    def test_normalizes_influence_scores(self, task, graph_data):
        result = task.execute(graph_data)

        for paper in result["papers"]:
            assert "influence_score_normalized" in paper
            assert 0.0 <= paper["influence_score_normalized"] <= 1.0


class TestFeatureEngineeringHelpers:
    def test_compute_paper_features_foundational(self, task):
        features = task._compute_paper_features(
            {"year": 1990, "citationCount": 5000}, 2020
        )
        assert features["temporal_category"] == "foundational"

    def test_compute_paper_features_contemporary(self, task):
        features = task._compute_paper_features(
            {"year": 2020, "citationCount": 100}, 2020
        )
        assert features["temporal_category"] == "contemporary"

    def test_normalize_empty_papers(self, task):
        result = task._normalize_influence_scores([])
        assert result == []

    def test_normalize_single_paper(self, task):
        papers = [{"influence_score_raw": 100.0}]
        result = task._normalize_influence_scores(papers)
        assert result[0]["influence_score_normalized"] == 0.5


class TestFeatureEngineeringEdgeCases:
    """Edge cases: None year, None citationCount, recency bounds."""

    def test_handles_paper_with_none_year(self, task):
        graph_data = {
            "target_paper_id": "t",
            "papers": [
                {"paperId": "t", "title": "T", "year": None, "citationCount": 100, "influentialCitationCount": 5},
            ],
            "references": [],
            "citations": [],
            "graph": None,
            "metrics": {"t": {"pagerank": 0.5, "betweenness": 0, "in_degree": 0, "out_degree": 0}},
            "graph_stats": {},
            "components": {},
        }
        result = task.execute(graph_data)
        assert len(result["papers"]) == 1
        # paper_age should default to 1 when year is None (see _compute_paper_features: paper_age = ... if year else 1)
        assert result["papers"][0]["paper_age"] >= 1
        assert "temporal_category" in result["papers"][0]

    def test_handles_paper_with_none_citation_count(self, task):
        graph_data = {
            "target_paper_id": "t",
            "papers": [
                {"paperId": "t", "title": "T", "year": 2020, "citationCount": None, "influentialCitationCount": None},
            ],
            "references": [],
            "citations": [],
            "graph": None,
            "metrics": {"t": {"pagerank": 0.5, "betweenness": 0, "in_degree": 0, "out_degree": 0}},
            "graph_stats": {},
            "components": {},
        }
        result = task.execute(graph_data)
        assert len(result["papers"]) == 1
        # Should treat None as 0 (citation_velocity 0, influence_score_raw computed)
        assert result["papers"][0]["citation_velocity"] == 0
        assert "influence_score_normalized" in result["papers"][0]

    def test_recency_score_clamped_between_zero_and_one(self, task):
        # Very old paper: paper_age large -> recency_score could go negative without clamp
        features = task._compute_paper_features({"year": 1990, "citationCount": 0}, 2020)
        assert 0.0 <= features["recency_score"] <= 1.0
