"""Feature engineering task - Compute derived features for papers."""
from typing import Dict, Any, List
from datetime import datetime
from src.utils.logging import get_logger

logger = get_logger(__name__)


class FeatureEngineeringTask:
    """Compute derived features for papers and citations."""

    def execute(self, graph_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Compute derived features from graph data.

        Args:
            graph_data: Output from citation graph construction

        Returns:
            Graph data enriched with features
        """
        logger.info("Starting feature engineering")

        papers = graph_data["papers"]
        target_paper_id = graph_data["target_paper_id"]
        metrics = graph_data["metrics"]

        # Get target paper for reference
        target_paper = next(
            (p for p in papers if p["paperId"] == target_paper_id), None
        )
        target_year = (
            target_paper.get("year", datetime.now().year)
            if target_paper
            else datetime.now().year
        )

        # Compute features for each paper
        enriched_papers = []
        for paper in papers:
            enriched_paper = paper.copy()

            # Add graph metrics
            paper_metrics = metrics.get(paper["paperId"], {})
            enriched_paper["pagerank"] = paper_metrics.get("pagerank", 0.0)
            enriched_paper["betweenness"] = paper_metrics.get("betweenness", 0.0)
            enriched_paper["in_degree"] = paper_metrics.get("in_degree", 0)
            enriched_paper["out_degree"] = paper_metrics.get("out_degree", 0)

            # Compute derived features
            enriched_paper.update(self._compute_paper_features(paper, target_year))

            enriched_papers.append(enriched_paper)

        # Normalize influence scores across all papers
        enriched_papers = self._normalize_influence_scores(enriched_papers)

        logger.info(
            f"Feature engineering complete: added features to {len(enriched_papers)} papers"
        )

        return {
            "target_paper_id": target_paper_id,
            "papers": enriched_papers,
            "references": graph_data["references"],
            "citations": graph_data["citations"],
            "graph": graph_data["graph"],
            "metrics": metrics,
            "graph_stats": graph_data["graph_stats"],
            "components": graph_data["components"],
        }

    def _compute_paper_features(
        self, paper: Dict[str, Any], target_year: int
    ) -> Dict[str, Any]:
        """
        Compute derived features for a single paper.

        Args:
            paper: Paper dictionary
            target_year: Year of target paper

        Returns:
            Dictionary of computed features
        """
        year = paper.get("year", target_year)
        citation_count = paper.get("citationCount", 0) or 0
        influential_count = paper.get("influentialCitationCount", 0) or 0

        # Paper age (years since publication)
        current_year = datetime.now().year
        paper_age = max(1, current_year - year) if year else 1

        # Citation velocity (citations per year)
        citation_velocity = citation_count / paper_age if paper_age > 0 else 0

        # Recency score (0-1, newer = higher)
        max_age = current_year - 1990
        recency_score = 1.0 - (paper_age / max_age) if max_age > 0 else 0.5
        recency_score = max(0.0, min(1.0, recency_score))

        # Era relative to target
        years_from_target = year - target_year if year else 0

        # Temporal category
        if years_from_target < -5:
            temporal_category = "foundational"
        elif -5 <= years_from_target < -1:
            temporal_category = "recent_predecessor"
        elif -1 <= years_from_target <= 1:
            temporal_category = "contemporary"
        else:
            temporal_category = "subsequent"

        # Raw influence score (will be normalized later)
        influence_score = (
            citation_count + (influential_count * 10) + (citation_velocity * 100)
        )

        return {
            "paper_age": paper_age,
            "citation_velocity": round(citation_velocity, 2),
            "recency_score": round(recency_score, 3),
            "years_from_target": years_from_target,
            "temporal_category": temporal_category,
            "influence_score_raw": round(influence_score, 2),
        }

    def _normalize_influence_scores(
        self, papers: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Normalize influence scores to 0-1 range.

        Args:
            papers: List of papers with raw influence scores

        Returns:
            Papers with normalized influence scores
        """
        # Get all raw scores
        raw_scores = [p.get("influence_score_raw", 0.0) for p in papers]

        if not raw_scores:
            return papers

        min_score = min(raw_scores)
        max_score = max(raw_scores)
        score_range = max_score - min_score

        # Normalize
        for paper in papers:
            raw = paper.get("influence_score_raw", 0.0)

            if score_range > 0:
                normalized = (raw - min_score) / score_range
            else:
                normalized = 0.5

            paper["influence_score_normalized"] = round(normalized, 3)

        return papers
