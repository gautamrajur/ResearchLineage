"""Unit tests for FeatureEngineeringTask."""
import pytest
from datetime import datetime

from src.tasks.feature_engineering import FeatureEngineeringTask
from tests.conftest import make_paper, make_ref, make_cit


@pytest.fixture
def task():
    return FeatureEngineeringTask()


def _graph_data(papers=None, target_id="p1", references=None, citations=None):
    """Minimal structure CitationGraphConstructionTask would return."""
    p = papers or [make_paper("p1", year=2017)]
    # Build a fake metrics dict for each paper
    metrics = {
        paper["paperId"]: {
            "pagerank": 0.2,
            "betweenness": 0.1,
            "in_degree": 2,
            "out_degree": 1,
            "total_degree": 3,
        }
        for paper in p
    }
    return {
        "target_paper_id": target_id,
        "papers": p,
        "references": references or [],
        "citations": citations or [],
        "metrics": metrics,
        "graph_stats": {"num_nodes": len(p), "num_edges": 0, "density": 0.0, "is_directed": True},
        "components": {"num_weak_components": 1, "largest_component_size": len(p), "component_sizes": [len(p)]},
    }


# ─── Feature completeness ────────────────────────────────────────────────────

class TestFeatureCompleteness:
    def test_features_added_to_all_papers(self, task):
        data = _graph_data(papers=[make_paper("p1"), make_paper("p2")])
        result = task.execute(data)
        assert len(result["papers"]) == 2

    def test_expected_feature_keys_present(self, task):
        result = task.execute(_graph_data())
        paper = result["papers"][0]
        for key in ("pagerank", "betweenness", "in_degree", "out_degree",
                    "paper_age", "citation_velocity", "recency_score",
                    "temporal_category", "influence_score_raw",
                    "influence_score_normalized"):
            assert key in paper, f"Missing feature key: {key}"

    def test_graph_metrics_copied_onto_paper(self, task):
        result = task.execute(_graph_data())
        paper = result["papers"][0]
        assert paper["pagerank"] == 0.2
        assert paper["in_degree"] == 2


# ─── Temporal category ───────────────────────────────────────────────────────

class TestTemporalCategory:
    def test_foundational_paper(self, task):
        """Paper published >5 years before the target."""
        target = make_paper("target", year=2020)
        old    = make_paper("old",    year=2010)
        data = _graph_data(papers=[target, old], target_id="target")
        result = task.execute(data)
        paper = next(p for p in result["papers"] if p["paperId"] == "old")
        assert paper["temporal_category"] == "foundational"

    def test_recent_predecessor(self, task):
        """Paper published 2–5 years before target."""
        target = make_paper("target", year=2020)
        recent = make_paper("recent", year=2017)
        data = _graph_data(papers=[target, recent], target_id="target")
        result = task.execute(data)
        paper = next(p for p in result["papers"] if p["paperId"] == "recent")
        assert paper["temporal_category"] == "recent_predecessor"

    def test_contemporary_paper(self, task):
        """Paper published within 1 year of target."""
        target = make_paper("target", year=2020)
        same   = make_paper("same",   year=2020)
        data = _graph_data(papers=[target, same], target_id="target")
        result = task.execute(data)
        paper = next(p for p in result["papers"] if p["paperId"] == "same")
        assert paper["temporal_category"] == "contemporary"

    def test_subsequent_paper(self, task):
        """Paper published after the target."""
        target = make_paper("target", year=2020)
        after  = make_paper("after",  year=2023)
        data = _graph_data(papers=[target, after], target_id="target")
        result = task.execute(data)
        paper = next(p for p in result["papers"] if p["paperId"] == "after")
        assert paper["temporal_category"] == "subsequent"


# ─── Citation velocity ───────────────────────────────────────────────────────

class TestCitationVelocity:
    def test_velocity_is_citations_per_year(self, task):
        current_year = datetime.now().year
        paper_year = 2020
        cit_count = 1000
        paper = make_paper("p1", year=paper_year, citation_count=cit_count)
        result = task.execute(_graph_data(papers=[paper]))
        expected_age = max(1, current_year - paper_year)
        expected_velocity = round(cit_count / expected_age, 2)
        assert result["papers"][0]["citation_velocity"] == expected_velocity

    def test_velocity_non_negative(self, task):
        paper = make_paper("p1", year=2022, citation_count=0)
        result = task.execute(_graph_data(papers=[paper]))
        assert result["papers"][0]["citation_velocity"] >= 0


# ─── Influence score normalisation ───────────────────────────────────────────

class TestNormalisation:
    def test_normalised_scores_in_zero_one(self, task):
        papers = [
            make_paper("p1", citation_count=10000),
            make_paper("p2", citation_count=100),
            make_paper("p3", citation_count=10),
        ]
        result = task.execute(_graph_data(papers=papers))
        for p in result["papers"]:
            score = p["influence_score_normalized"]
            assert 0.0 <= score <= 1.0, f"Score out of range: {score}"

    def test_single_paper_gets_midpoint(self, task):
        """With only one paper, score_range == 0 so normalised score is 0.5."""
        result = task.execute(_graph_data(papers=[make_paper("p1")]))
        assert result["papers"][0]["influence_score_normalized"] == 0.5

    def test_highest_cited_gets_score_one(self, task):
        papers = [make_paper("p1", citation_count=9000), make_paper("p2", citation_count=1)]
        result = task.execute(_graph_data(papers=papers))
        scores = {p["paperId"]: p["influence_score_normalized"] for p in result["papers"]}
        assert scores["p1"] > scores["p2"]


# ─── Recency score ───────────────────────────────────────────────────────────

class TestRecencyScore:
    def test_recency_score_clamped_to_zero_one(self, task):
        papers = [make_paper("p1", year=1990), make_paper("p2", year=2025)]
        result = task.execute(_graph_data(papers=papers))
        for p in result["papers"]:
            assert 0.0 <= p["recency_score"] <= 1.0

    def test_newer_paper_has_higher_recency(self, task):
        papers = [make_paper("p1", year=2000), make_paper("p2", year=2022)]
        result = task.execute(_graph_data(papers=papers))
        scores = {p["paperId"]: p["recency_score"] for p in result["papers"]}
        assert scores["p2"] > scores["p1"]
