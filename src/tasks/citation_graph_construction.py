"""Citation graph construction task - Build NetworkX graph from papers."""
from typing import Dict, Any, List
import networkx as nx
from src.utils.logging import get_logger

logger = get_logger(__name__)


class CitationGraphConstructionTask:
    """Build citation network graph using NetworkX."""

    def execute(self, cleaned_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Construct citation graph from cleaned data.

        Args:
            cleaned_data: Output from data cleaning task

        Returns:
            Dictionary with graph and metadata
        """
        logger.info("Starting citation graph construction")

        papers = cleaned_data["papers"]
        references = cleaned_data["references"]
        citations = cleaned_data["citations"]

        # Build directed graph
        G = self._build_graph(papers, references, citations)

        # Calculate graph metrics
        metrics = self._calculate_metrics(G)

        # Identify connected components
        components = self._analyze_components(G)

        logger.info(
            f"Graph constructed: {G.number_of_nodes()} nodes, "
            f"{G.number_of_edges()} edges"
        )

        return {
            "target_paper_id": cleaned_data["target_paper_id"],
            "graph": G,
            "papers": papers,
            "references": references,
            "citations": citations,
            "graph_stats": {
                "num_nodes": G.number_of_nodes(),
                "num_edges": G.number_of_edges(),
                "density": nx.density(G),
                "is_directed": G.is_directed(),
            },
            "metrics": metrics,
            "components": components,
        }

    def _build_graph(
        self,
        papers: List[Dict[str, Any]],
        references: List[Dict[str, Any]],
        citations: List[Dict[str, Any]],
    ) -> nx.DiGraph:
        """
        Build directed citation graph.

        Args:
            papers: List of paper dictionaries
            references: List of reference relationships
            citations: List of citation relationships

        Returns:
            NetworkX directed graph
        """
        G = nx.DiGraph()

        # Add nodes (papers) with attributes
        for paper in papers:
            G.add_node(
                paper["paperId"],
                title=paper.get("title", ""),
                year=paper.get("year"),
                citationCount=paper.get("citationCount", 0),
                influentialCitationCount=paper.get("influentialCitationCount", 0),
                referenceCount=paper.get("referenceCount", 0),
                venue=paper.get("venue", ""),
                authors=paper.get("authors", []),
            )

        # Add edges from references (A cites B => edge from A to B)
        for ref in references:
            from_id = ref["fromPaperId"]
            to_id = ref["toPaperId"]

            if G.has_node(from_id) and G.has_node(to_id):
                G.add_edge(
                    from_id,
                    to_id,
                    isInfluential=ref.get("isInfluential", False),
                    contexts=ref.get("contexts", []),
                    intents=ref.get("intents", []),
                )

        # Add edges from citations
        for cit in citations:
            from_id = cit["fromPaperId"]
            to_id = cit["toPaperId"]

            if G.has_node(from_id) and G.has_node(to_id):
                if not G.has_edge(from_id, to_id):
                    G.add_edge(
                        from_id,
                        to_id,
                        isInfluential=cit.get("isInfluential", False),
                        contexts=cit.get("contexts", []),
                        intents=cit.get("intents", []),
                    )

        logger.info(
            f"Graph built: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges"
        )
        return G

    def _calculate_metrics(self, G: nx.DiGraph) -> Dict[str, Any]:
        """
        Calculate graph metrics for all nodes.

        Args:
            G: NetworkX graph

        Returns:
            Dictionary of metrics per node
        """
        logger.info("Calculating graph metrics")

        metrics = {}

        # PageRank (importance based on citation structure)
        try:
            pagerank = nx.pagerank(G, alpha=0.85)
        except Exception:
            pagerank = {node: 0.0 for node in G.nodes()}

        # Betweenness centrality (nodes connecting different parts of graph)
        try:
            betweenness = nx.betweenness_centrality(G)
        except Exception:
            betweenness = {node: 0.0 for node in G.nodes()}

        # In-degree (number of citations received)
        in_degree = dict(G.in_degree())

        # Out-degree (number of references made)
        out_degree = dict(G.out_degree())

        # Combine all metrics
        for node in G.nodes():
            metrics[node] = {
                "pagerank": pagerank.get(node, 0.0),
                "betweenness": betweenness.get(node, 0.0),
                "in_degree": in_degree.get(node, 0),
                "out_degree": out_degree.get(node, 0),
                "total_degree": in_degree.get(node, 0) + out_degree.get(node, 0),
            }

        return metrics

    def _analyze_components(self, G: nx.DiGraph) -> Dict[str, Any]:
        """
        Analyze connected components in the graph.

        Args:
            G: NetworkX graph

        Returns:
            Component analysis
        """
        # For directed graphs, use weakly connected components
        weak_components = list(nx.weakly_connected_components(G))

        return {
            "num_weak_components": len(weak_components),
            "largest_component_size": len(max(weak_components, key=len))
            if weak_components
            else 0,
            "component_sizes": [len(c) for c in weak_components],
        }
