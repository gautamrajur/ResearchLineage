"""Unit tests for CitationGraphConstructionTask."""
import pytest
import networkx as nx

from src.tasks.citation_graph_construction import CitationGraphConstructionTask
from tests.conftest import make_paper, make_ref, make_cit


@pytest.fixture
def task():
    return CitationGraphConstructionTask()


def _cleaned(papers=None, references=None, citations=None):
    """Minimal structure that CitationGraphConstructionTask.execute() expects."""
    return {
        "target_paper_id": "p1",
        "papers": papers if papers is not None else [make_paper("p1"), make_paper("p2")],
        "references": references if references is not None else [],
        "citations": citations if citations is not None else [],
        "cleaning_stats": {},
    }


# ─── Graph structure ─────────────────────────────────────────────────────────

class TestGraphStructure:
    def test_nodes_created_for_each_paper(self, task):
        data = _cleaned(papers=[make_paper("p1"), make_paper("p2"), make_paper("p3")])
        result = task.execute(data)
        assert result["graph_stats"]["num_nodes"] == 3

    def test_edge_added_from_reference(self, task):
        papers = [make_paper("p1"), make_paper("p2")]
        data = _cleaned(papers=papers, references=[make_ref("p1", "p2")])
        result = task.execute(data)
        assert result["graph_stats"]["num_edges"] == 1

    def test_edge_added_from_citation(self, task):
        papers = [make_paper("p1"), make_paper("p3")]
        data = _cleaned(papers=papers, citations=[make_cit("p3", "p1")])
        result = task.execute(data)
        assert result["graph_stats"]["num_edges"] == 1

    def test_no_duplicate_edges(self, task):
        """If the same relationship appears in both references and citations, only one edge is added."""
        papers = [make_paper("p1"), make_paper("p2")]
        refs = [make_ref("p1", "p2")]
        cits = [make_cit("p1", "p2")]  # same direction
        data = _cleaned(papers=papers, references=refs, citations=cits)
        result = task.execute(data)
        assert result["graph_stats"]["num_edges"] == 1

    def test_edge_not_added_for_unknown_paper(self, task):
        """Reference involving a paper not in the node list is ignored."""
        papers = [make_paper("p1")]
        refs = [make_ref("p1", "p_missing")]
        data = _cleaned(papers=papers, references=refs)
        result = task.execute(data)
        assert result["graph_stats"]["num_edges"] == 0

    def test_graph_is_directed(self, task):
        result = task.execute(_cleaned())
        assert result["graph_stats"]["is_directed"] is True

    def test_empty_papers_yields_empty_graph(self, task):
        data = _cleaned(papers=[], references=[], citations=[])
        result = task.execute(data)
        assert result["graph_stats"]["num_nodes"] == 0
        assert result["graph_stats"]["num_edges"] == 0


# ─── Node attributes ─────────────────────────────────────────────────────────

class TestNodeAttributes:
    def test_paper_attributes_stored_on_node(self, task):
        paper = make_paper("p1", title="My Paper", year=2021, citation_count=99, venue="ICLR")
        data = _cleaned(papers=[paper])
        result = task.execute(data)
        G = result["graph"]
        node = G.nodes["p1"]
        assert node["title"] == "My Paper"
        assert node["year"] == 2021
        assert node["citationCount"] == 99
        assert node["venue"] == "ICLR"

    def test_edge_attributes_stored(self, task):
        papers = [make_paper("p1"), make_paper("p2")]
        refs = [make_ref("p1", "p2", intents=["methodology"], is_influential=True)]
        data = _cleaned(papers=papers, references=refs)
        result = task.execute(data)
        G = result["graph"]
        edge = G.edges["p1", "p2"]
        assert edge["isInfluential"] is True
        assert "methodology" in edge["intents"]


# ─── Graph metrics ───────────────────────────────────────────────────────────

class TestGraphMetrics:
    def test_metrics_calculated_for_all_nodes(self, task):
        papers = [make_paper("p1"), make_paper("p2"), make_paper("p3")]
        refs = [make_ref("p1", "p2"), make_ref("p2", "p3")]
        data = _cleaned(papers=papers, references=refs)
        result = task.execute(data)
        metrics = result["metrics"]
        assert set(metrics.keys()) == {"p1", "p2", "p3"}

    def test_metric_keys_present(self, task):
        result = task.execute(_cleaned())
        for node_metrics in result["metrics"].values():
            for key in ("pagerank", "betweenness", "in_degree", "out_degree", "total_degree"):
                assert key in node_metrics

    def test_in_degree_reflects_incoming_edges(self, task):
        papers = [make_paper("p1"), make_paper("p2"), make_paper("p3")]
        # p2 is cited by both p1 and p3
        refs = [make_ref("p1", "p2"), make_ref("p3", "p2")]
        data = _cleaned(papers=papers, references=refs)
        result = task.execute(data)
        assert result["metrics"]["p2"]["in_degree"] == 2
        assert result["metrics"]["p1"]["out_degree"] == 1


# ─── Components ──────────────────────────────────────────────────────────────

class TestComponents:
    def test_single_connected_component(self, task):
        papers = [make_paper("p1"), make_paper("p2")]
        refs = [make_ref("p1", "p2")]
        data = _cleaned(papers=papers, references=refs)
        result = task.execute(data)
        assert result["components"]["num_weak_components"] == 1

    def test_two_disconnected_papers_two_components(self, task):
        papers = [make_paper("p1"), make_paper("p2")]
        data = _cleaned(papers=papers, references=[], citations=[])
        result = task.execute(data)
        assert result["components"]["num_weak_components"] == 2

    def test_largest_component_size_correct(self, task):
        papers = [make_paper("p1"), make_paper("p2"), make_paper("p3")]
        refs = [make_ref("p1", "p2")]  # p3 is isolated
        data = _cleaned(papers=papers, references=refs)
        result = task.execute(data)
        assert result["components"]["largest_component_size"] == 2


# ─── Output keys ─────────────────────────────────────────────────────────────

class TestOutputKeys:
    def test_all_required_keys_present(self, task):
        result = task.execute(_cleaned())
        for key in ("target_paper_id", "graph", "papers", "references",
                    "citations", "graph_stats", "metrics", "components"):
            assert key in result

    def test_graph_is_networkx_digraph(self, task):
        result = task.execute(_cleaned())
        assert isinstance(result["graph"], nx.DiGraph)
