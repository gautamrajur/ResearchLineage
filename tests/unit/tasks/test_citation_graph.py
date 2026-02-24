"""Unit tests for src.tasks.citation_graph_construction."""
import pytest
from unittest.mock import patch, MagicMock
import networkx as nx

from src.tasks.citation_graph_construction import CitationGraphConstructionTask


@pytest.fixture
def task():
    """Task instance."""
    return CitationGraphConstructionTask()


@pytest.fixture
def minimal_data():
    """Minimal valid cleaned data."""
    return {
        "target_paper_id": "t1",
        "papers": [{"paperId": "t1", "title": "Target"}],
        "references": [],
        "citations": [],
    }


@pytest.fixture
def standard_data():
    """Standard test data with refs and citations."""
    return {
        "target_paper_id": "target",
        "papers": [
            {
                "paperId": "target",
                "title": "Target Paper",
                "year": 2023,
                "citationCount": 50,
                "influentialCitationCount": 5,
                "referenceCount": 30,
                "venue": "NeurIPS",
                "authors": [{"authorId": "a1", "name": "Alice"}],
            },
            {"paperId": "ref1", "title": "Reference 1", "year": 2020, "citationCount": 100},
            {"paperId": "cit1", "title": "Citation 1", "year": 2024, "citationCount": 10},
        ],
        "references": [
            {
                "fromPaperId": "target",
                "toPaperId": "ref1",
                "isInfluential": True,
                "contexts": ["We build upon..."],
                "intents": ["methodology"],
            },
        ],
        "citations": [
            {
                "fromPaperId": "cit1",
                "toPaperId": "target",
                "isInfluential": False,
                "contexts": [],
                "intents": [],
            },
        ],
    }


# ═══════════════════════════════════════════════════════════════════════════
# execute
# ═══════════════════════════════════════════════════════════════════════════


class TestExecute:

    def test_returns_all_keys(self, task, standard_data):
        """Returns dict with all expected keys."""
        out = task.execute(standard_data)

        expected = ["target_paper_id", "graph", "papers", "references",
                    "citations", "graph_stats", "metrics", "components"]
        for key in expected:
            assert key in out

    def test_preserves_input_data(self, task, standard_data):
        """Preserves original papers/refs/citations."""
        out = task.execute(standard_data)

        assert out["papers"] is standard_data["papers"]
        assert out["references"] is standard_data["references"]
        assert out["citations"] is standard_data["citations"]
        assert out["target_paper_id"] == "target"

    def test_creates_digraph(self, task, standard_data):
        """Creates NetworkX DiGraph."""
        out = task.execute(standard_data)

        assert isinstance(out["graph"], nx.DiGraph)

    def test_graph_stats_structure(self, task, standard_data):
        """Graph stats has required fields."""
        out = task.execute(standard_data)
        stats = out["graph_stats"]

        assert stats["num_nodes"] == 3
        assert stats["num_edges"] == 2
        assert 0 <= stats["density"] <= 1
        assert stats["is_directed"] is True

    def test_empty_papers(self, task):
        """Handles empty papers list."""
        data = {"target_paper_id": "t", "papers": [], "references": [], "citations": []}
        out = task.execute(data)

        assert out["graph"].number_of_nodes() == 0
        assert out["graph"].number_of_edges() == 0
        assert out["metrics"] == {}


# ═══════════════════════════════════════════════════════════════════════════
# _build_graph
# ═══════════════════════════════════════════════════════════════════════════


class TestBuildGraph:

    def test_empty(self, task):
        """Empty inputs create empty graph."""
        G = task._build_graph([], [], [])

        assert G.number_of_nodes() == 0
        assert G.number_of_edges() == 0

    def test_nodes_from_papers(self, task):
        """Creates node for each paper."""
        papers = [
            {"paperId": "p1", "title": "Paper 1"},
            {"paperId": "p2", "title": "Paper 2"},
        ]
        G = task._build_graph(papers, [], [])

        assert G.number_of_nodes() == 2
        assert "p1" in G
        assert "p2" in G

    def test_node_attributes(self, task):
        """Nodes have paper attributes."""
        papers = [{
            "paperId": "p1",
            "title": "Test Title",
            "year": 2023,
            "citationCount": 50,
            "influentialCitationCount": 5,
            "referenceCount": 30,
            "venue": "ICML",
            "authors": [{"name": "Alice"}],
        }]
        G = task._build_graph(papers, [], [])

        node = G.nodes["p1"]
        assert node["title"] == "Test Title"
        assert node["year"] == 2023
        assert node["citationCount"] == 50
        assert node["influentialCitationCount"] == 5
        assert node["referenceCount"] == 30
        assert node["venue"] == "ICML"
        assert node["authors"] == [{"name": "Alice"}]

    def test_node_defaults(self, task):
        """Missing attributes get defaults."""
        papers = [{"paperId": "p1"}]
        G = task._build_graph(papers, [], [])

        node = G.nodes["p1"]
        assert node["title"] == ""
        assert node["year"] is None
        assert node["citationCount"] == 0
        assert node["venue"] == ""
        assert node["authors"] == []

    def test_edges_from_refs(self, task):
        """Creates edges from references."""
        papers = [{"paperId": "p1"}, {"paperId": "p2"}]
        refs = [{"fromPaperId": "p1", "toPaperId": "p2"}]

        G = task._build_graph(papers, refs, [])

        assert G.has_edge("p1", "p2")
        assert G.number_of_edges() == 1

    def test_edge_attributes(self, task):
        """Edges have reference attributes."""
        papers = [{"paperId": "p1"}, {"paperId": "p2"}]
        refs = [{
            "fromPaperId": "p1",
            "toPaperId": "p2",
            "isInfluential": True,
            "contexts": ["context1"],
            "intents": ["methodology"],
        }]
        G = task._build_graph(papers, refs, [])

        edge = G.edges["p1", "p2"]
        assert edge["isInfluential"] is True
        assert edge["contexts"] == ["context1"]
        assert edge["intents"] == ["methodology"]

    def test_edge_defaults(self, task):
        """Missing edge attributes get defaults."""
        papers = [{"paperId": "p1"}, {"paperId": "p2"}]
        refs = [{"fromPaperId": "p1", "toPaperId": "p2"}]

        G = task._build_graph(papers, refs, [])

        edge = G.edges["p1", "p2"]
        assert edge["isInfluential"] is False
        assert edge["contexts"] == []
        assert edge["intents"] == []

    def test_edges_from_citations(self, task):
        """Creates edges from citations."""
        papers = [{"paperId": "p1"}, {"paperId": "p2"}]
        cits = [{"fromPaperId": "p2", "toPaperId": "p1"}]

        G = task._build_graph(papers, [], cits)

        assert G.has_edge("p2", "p1")

    def test_skip_missing_from_node(self, task):
        """Skips edge when from_node missing."""
        papers = [{"paperId": "p2"}]
        refs = [{"fromPaperId": "missing", "toPaperId": "p2"}]

        G = task._build_graph(papers, refs, [])

        assert G.number_of_edges() == 0

    def test_skip_missing_to_node(self, task):
        """Skips edge when to_node missing."""
        papers = [{"paperId": "p1"}]
        refs = [{"fromPaperId": "p1", "toPaperId": "missing"}]

        G = task._build_graph(papers, refs, [])

        assert G.number_of_edges() == 0

    def test_no_duplicate_edges(self, task):
        """Same edge in refs and citations not duplicated."""
        papers = [{"paperId": "p1"}, {"paperId": "p2"}]
        refs = [{"fromPaperId": "p1", "toPaperId": "p2"}]
        cits = [{"fromPaperId": "p1", "toPaperId": "p2"}]  # Same edge

        G = task._build_graph(papers, refs, cits)

        assert G.number_of_edges() == 1

    def test_ref_and_cit_different_edges(self, task):
        """Different edges from refs and citations both added."""
        papers = [{"paperId": "p1"}, {"paperId": "p2"}]
        refs = [{"fromPaperId": "p1", "toPaperId": "p2"}]
        cits = [{"fromPaperId": "p2", "toPaperId": "p1"}]  # Reverse

        G = task._build_graph(papers, refs, cits)

        assert G.number_of_edges() == 2
        assert G.has_edge("p1", "p2")
        assert G.has_edge("p2", "p1")

    def test_self_loop(self, task):
        """Handles self-referencing paper."""
        papers = [{"paperId": "p1"}]
        refs = [{"fromPaperId": "p1", "toPaperId": "p1"}]

        G = task._build_graph(papers, refs, [])

        assert G.has_edge("p1", "p1")

    def test_large_graph(self, task):
        """Handles larger graph."""
        papers = [{"paperId": f"p{i}"} for i in range(100)]
        refs = [{"fromPaperId": f"p{i}", "toPaperId": f"p{i+1}"} for i in range(99)]

        G = task._build_graph(papers, refs, [])

        assert G.number_of_nodes() == 100
        assert G.number_of_edges() == 99


# ═══════════════════════════════════════════════════════════════════════════
# _calculate_metrics
# ═══════════════════════════════════════════════════════════════════════════


class TestCalculateMetrics:

    def test_empty_graph(self, task):
        """Empty graph returns empty metrics."""
        G = nx.DiGraph()
        metrics = task._calculate_metrics(G)

        assert metrics == {}

    def test_single_node(self, task):
        """Single node has zero degrees."""
        G = nx.DiGraph()
        G.add_node("p1")

        metrics = task._calculate_metrics(G)

        assert "p1" in metrics
        assert metrics["p1"]["in_degree"] == 0
        assert metrics["p1"]["out_degree"] == 0
        assert metrics["p1"]["total_degree"] == 0

    def test_metrics_keys(self, task):
        """Each node has all metric keys."""
        G = nx.DiGraph()
        G.add_edge("p1", "p2")

        metrics = task._calculate_metrics(G)

        expected = ["pagerank", "betweenness", "in_degree", "out_degree", "total_degree"]
        for node in ["p1", "p2"]:
            for key in expected:
                assert key in metrics[node]

    def test_in_out_degree(self, task):
        """Correct in/out degree calculation."""
        G = nx.DiGraph()
        G.add_edges_from([("p1", "p2"), ("p1", "p3"), ("p3", "p2")])

        metrics = task._calculate_metrics(G)

        # p1: out=2, in=0
        assert metrics["p1"]["out_degree"] == 2
        assert metrics["p1"]["in_degree"] == 0
        # p2: out=0, in=2
        assert metrics["p2"]["out_degree"] == 0
        assert metrics["p2"]["in_degree"] == 2
        # p3: out=1, in=1
        assert metrics["p3"]["out_degree"] == 1
        assert metrics["p3"]["in_degree"] == 1

    def test_total_degree(self, task):
        """Total degree is sum of in + out."""
        G = nx.DiGraph()
        G.add_edges_from([("p1", "p2"), ("p2", "p1")])

        metrics = task._calculate_metrics(G)

        for node in ["p1", "p2"]:
            expected = metrics[node]["in_degree"] + metrics[node]["out_degree"]
            assert metrics[node]["total_degree"] == expected

    def test_pagerank_sums_to_one(self, task):
        """PageRank values sum to ~1."""
        G = nx.DiGraph()
        G.add_edges_from([("p1", "p2"), ("p2", "p3"), ("p3", "p1")])

        metrics = task._calculate_metrics(G)

        total = sum(m["pagerank"] for m in metrics.values())
        assert abs(total - 1.0) < 0.01

    def test_pagerank_exception_fallback(self, task):
        """PageRank exception returns zeros."""
        G = nx.DiGraph()
        G.add_node("p1")

        with patch("networkx.pagerank", side_effect=Exception("fail")):
            metrics = task._calculate_metrics(G)

        assert metrics["p1"]["pagerank"] == 0.0

    def test_betweenness_exception_fallback(self, task):
        """Betweenness exception returns zeros."""
        G = nx.DiGraph()
        G.add_node("p1")

        with patch("networkx.betweenness_centrality", side_effect=Exception("fail")):
            metrics = task._calculate_metrics(G)

        assert metrics["p1"]["betweenness"] == 0.0

    def test_disconnected_nodes(self, task):
        """Handles disconnected nodes."""
        G = nx.DiGraph()
        G.add_nodes_from(["p1", "p2", "p3"])  # No edges

        metrics = task._calculate_metrics(G)

        assert len(metrics) == 3
        for m in metrics.values():
            assert m["in_degree"] == 0
            assert m["out_degree"] == 0

    def test_star_topology(self, task):
        """Hub node has high betweenness."""
        G = nx.DiGraph()
        # Star: hub connects to all others
        for i in range(5):
            G.add_edge("hub", f"leaf{i}")

        metrics = task._calculate_metrics(G)

        # Hub should have higher out_degree
        assert metrics["hub"]["out_degree"] == 5
        assert metrics["hub"]["in_degree"] == 0


# ═══════════════════════════════════════════════════════════════════════════
# _analyze_components
# ═══════════════════════════════════════════════════════════════════════════


class TestAnalyzeComponents:

    def test_empty_graph(self, task):
        """Empty graph has no components."""
        G = nx.DiGraph()
        comp = task._analyze_components(G)

        assert comp["num_weak_components"] == 0
        assert comp["largest_component_size"] == 0
        assert comp["component_sizes"] == []

    def test_single_node(self, task):
        """Single node is one component."""
        G = nx.DiGraph()
        G.add_node("p1")

        comp = task._analyze_components(G)

        assert comp["num_weak_components"] == 1
        assert comp["largest_component_size"] == 1
        assert comp["component_sizes"] == [1]

    def test_connected_graph(self, task):
        """Connected graph has one component."""
        G = nx.DiGraph()
        G.add_edges_from([("p1", "p2"), ("p2", "p3")])

        comp = task._analyze_components(G)

        assert comp["num_weak_components"] == 1
        assert comp["largest_component_size"] == 3

    def test_two_components(self, task):
        """Disconnected graph has multiple components."""
        G = nx.DiGraph()
        G.add_edge("a1", "a2")  # Component 1
        G.add_edge("b1", "b2")  # Component 2

        comp = task._analyze_components(G)

        assert comp["num_weak_components"] == 2
        assert sorted(comp["component_sizes"]) == [2, 2]

    def test_mixed_component_sizes(self, task):
        """Different sized components."""
        G = nx.DiGraph()
        # Component 1: 3 nodes
        G.add_edges_from([("a1", "a2"), ("a2", "a3")])
        # Component 2: 1 node
        G.add_node("b1")

        comp = task._analyze_components(G)

        assert comp["num_weak_components"] == 2
        assert comp["largest_component_size"] == 3
        assert sorted(comp["component_sizes"]) == [1, 3]

    def test_weakly_connected(self, task):
        """Weakly connected components (ignores direction)."""
        G = nx.DiGraph()
        # a -> b and c -> b: weakly connected
        G.add_edge("a", "b")
        G.add_edge("c", "b")

        comp = task._analyze_components(G)

        assert comp["num_weak_components"] == 1
        assert comp["largest_component_size"] == 3

    def test_many_isolated(self, task):
        """Many isolated nodes."""
        G = nx.DiGraph()
        for i in range(10):
            G.add_node(f"p{i}")

        comp = task._analyze_components(G)

        assert comp["num_weak_components"] == 10
        assert comp["largest_component_size"] == 1
        assert comp["component_sizes"] == [1] * 10


# ═══════════════════════════════════════════════════════════════════════════
# Edge Cases & Integration
# ═══════════════════════════════════════════════════════════════════════════


class TestEdgeCases:

    def test_unicode_paper_ids(self, task):
        """Handles Unicode in paper IDs."""
        papers = [{"paperId": "日本語"}, {"paperId": "中文"}]
        refs = [{"fromPaperId": "日本語", "toPaperId": "中文"}]

        G = task._build_graph(papers, refs, [])

        assert "日本語" in G
        assert G.has_edge("日本語", "中文")

    def test_special_char_ids(self, task):
        """Handles special characters in IDs."""
        papers = [{"paperId": "a:b/c"}, {"paperId": "x?y=z"}]
        refs = [{"fromPaperId": "a:b/c", "toPaperId": "x?y=z"}]

        G = task._build_graph(papers, refs, [])

        assert G.has_edge("a:b/c", "x?y=z")

    def test_numeric_paper_id(self, task):
        """Handles numeric-looking paper IDs."""
        papers = [{"paperId": "12345"}, {"paperId": "67890"}]
        refs = [{"fromPaperId": "12345", "toPaperId": "67890"}]

        G = task._build_graph(papers, refs, [])

        assert "12345" in G
        assert G.has_edge("12345", "67890")

    def test_empty_string_id(self, task):
        """Handles empty string paper ID."""
        papers = [{"paperId": ""}, {"paperId": "p1"}]

        G = task._build_graph(papers, [], [])

        assert "" in G
        assert "p1" in G

    def test_very_long_contexts(self, task):
        """Handles very long context strings."""
        papers = [{"paperId": "p1"}, {"paperId": "p2"}]
        refs = [{
            "fromPaperId": "p1",
            "toPaperId": "p2",
            "contexts": ["x" * 10000],
        }]

        G = task._build_graph(papers, refs, [])

        assert len(G.edges["p1", "p2"]["contexts"][0]) == 10000

    def test_many_authors(self, task):
        """Handles paper with many authors."""
        authors = [{"name": f"Author {i}"} for i in range(100)]
        papers = [{"paperId": "p1", "authors": authors}]

        G = task._build_graph(papers, [], [])

        assert len(G.nodes["p1"]["authors"]) == 100

    def test_full_pipeline(self, task, standard_data):
        """Full execute pipeline works correctly."""
        out = task.execute(standard_data)

        # Graph structure
        G = out["graph"]
        assert G.number_of_nodes() == 3
        assert G.has_edge("target", "ref1")
        assert G.has_edge("cit1", "target")

        # Metrics computed
        assert "target" in out["metrics"]
        assert out["metrics"]["target"]["out_degree"] == 1
        assert out["metrics"]["target"]["in_degree"] == 1

        # Components analyzed
        assert out["components"]["num_weak_components"] == 1
        assert out["components"]["largest_component_size"] == 3

    def test_citation_only_no_refs(self, task):
        """Graph with citations but no references."""
        data = {
            "target_paper_id": "t",
            "papers": [{"paperId": "t"}, {"paperId": "c1"}],
            "references": [],
            "citations": [{"fromPaperId": "c1", "toPaperId": "t"}],
        }
        out = task.execute(data)

        assert out["graph"].has_edge("c1", "t")
        assert out["graph"].number_of_edges() == 1

    def test_refs_only_no_citations(self, task):
        """Graph with references but no citations."""
        data = {
            "target_paper_id": "t",
            "papers": [{"paperId": "t"}, {"paperId": "r1"}],
            "references": [{"fromPaperId": "t", "toPaperId": "r1"}],
            "citations": [],
        }
        out = task.execute(data)

        assert out["graph"].has_edge("t", "r1")
        assert out["graph"].number_of_edges() == 1
