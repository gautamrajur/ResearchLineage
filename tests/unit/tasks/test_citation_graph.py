"""Unit tests for src.tasks.citation_graph_construction (CitationGraphConstructionTask)."""
import os

import pytest

from src.tasks.citation_graph_construction import CitationGraphConstructionTask

# Conditionally enable: set RUN_CITATION_GRAPH_TESTS=1 to run (some envs segfault in numpy.linalg).
pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_CITATION_GRAPH_TESTS") != "1",
    reason="Set RUN_CITATION_GRAPH_TESTS=1 to run (numpy.linalg can segfault in some envs)",
)


@pytest.fixture
def task():
    return CitationGraphConstructionTask()


@pytest.fixture
def cleaned_data():
    return {
        "target_paper_id": "t",
        "papers": [
            {"paperId": "t", "title": "Target", "year": 2020, "citationCount": 0, "authors": []},
            {"paperId": "p2", "title": "P2", "year": 2019, "citationCount": 1, "authors": []},
            {"paperId": "p3", "title": "P3", "year": 2018, "citationCount": 0, "authors": []},
        ],
        "references": [{"fromPaperId": "t", "toPaperId": "p2"}, {"fromPaperId": "t", "toPaperId": "p3"}],
        "citations": [{"fromPaperId": "p2", "toPaperId": "t"}],
    }


class TestCitationGraphConstructionTask:
    def test_execute_returns_graph_and_metadata(self, task, cleaned_data):
        out = task.execute(cleaned_data)
        assert "graph" in out
        assert "graph_stats" in out
        assert "metrics" in out
        assert "components" in out
        assert out["target_paper_id"] == "t"
        assert out["papers"] is cleaned_data["papers"]

    def test_graph_has_nodes_for_each_paper(self, task, cleaned_data):
        out = task.execute(cleaned_data)
        G = out["graph"]
        assert G.number_of_nodes() == 3
        assert "t" in G
        assert "p2" in G
        assert "p3" in G

    def test_graph_has_edges_from_references_and_citations(self, task, cleaned_data):
        out = task.execute(cleaned_data)
        G = out["graph"]
        # t -> p2, t -> p3 (references), p2 -> t (citation)
        assert G.number_of_edges() >= 2
        assert G.has_edge("t", "p2")
        assert G.has_edge("t", "p3")
        assert G.has_edge("p2", "t")

    def test_graph_stats_contains_num_nodes_edges_density(self, task, cleaned_data):
        out = task.execute(cleaned_data)
        stats = out["graph_stats"]
        assert stats["num_nodes"] == 3
        assert stats["num_edges"] >= 2
        assert "density" in stats
        assert stats["is_directed"] is True

    def test_metrics_per_node(self, task, cleaned_data):
        out = task.execute(cleaned_data)
        metrics = out["metrics"]
        assert "t" in metrics
        assert "p2" in metrics
        for node_metrics in metrics.values():
            assert "pagerank" in node_metrics
            assert "in_degree" in node_metrics
            assert "out_degree" in node_metrics

    def test_components_analysis(self, task, cleaned_data):
        out = task.execute(cleaned_data)
        comp = out["components"]
        assert "num_weak_components" in comp
        assert "largest_component_size" in comp
        assert comp["num_weak_components"] >= 1
        assert comp["largest_component_size"] == 3
