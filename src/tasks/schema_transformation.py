"""Schema transformation task - Transform data to database schema format."""
import uuid
from typing import Dict, Any, List
from datetime import datetime
from src.utils.logging import get_logger

logger = get_logger(__name__)


class SchemaTransformationTask:
    """Transform enriched data to database schema format."""

    def execute(self, enriched_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transform data to match database schema.

        Args:
            enriched_data: Output from feature engineering

        Returns:
            Database-ready structured data
        """
        logger.info("Starting schema transformation")

        papers = enriched_data["papers"]
        references = enriched_data["references"]
        citations = enriched_data["citations"]
        target_paper_id = enriched_data["target_paper_id"]

        # Transform to database tables
        papers_table = self._transform_papers(papers)
        authors_table = self._transform_authors(papers)
        citations_table = self._transform_citations(references, citations)

        logger.info(
            f"Schema transformation complete: {len(papers_table)} papers, "
            f"{len(authors_table)} authors, {len(citations_table)} citations"
        )

        return {
            "target_paper_id": target_paper_id,
            "papers_table": papers_table,
            "authors_table": authors_table,
            "citations_table": citations_table,
            "transformation_stats": {
                "papers_transformed": len(papers_table),
                "authors_transformed": len(authors_table),
                "citations_transformed": len(citations_table),
            },
        }

    def _transform_papers(self, papers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Transform papers to papers table format.

        Args:
            papers: List of enriched paper dictionaries

        Returns:
            List of papers in database schema format
        """
        transformed = []

        for paper in papers:
            # Extract external IDs
            external_ids = paper.get("externalIds", {}) or {}
            arxiv_id = external_ids.get("ArXiv", "")

            # Concatenate URLs
            urls = paper.get("url", "")

            transformed_paper = {
                "paperId": paper["paperId"],
                "arxivId": arxiv_id,
                "title": paper.get("title", ""),
                "abstract": paper.get("abstract", ""),
                "year": paper.get("year"),
                "citationCount": paper.get("citationCount", 0) or 0,
                "influentialCitationCount": paper.get("influentialCitationCount", 0)
                or 0,
                "referenceCount": paper.get("referenceCount", 0) or 0,
                "venue": paper.get("venue", ""),
                "urls": urls,
                "first_queried_at": datetime.utcnow(),
                "query_count": 1,
                "text_availability": "full_text"
                if paper.get("abstract")
                else "abstract_only",
            }

            transformed.append(transformed_paper)

        return transformed

    def _transform_authors(self, papers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Transform authors to authors table format.

        Args:
            papers: List of paper dictionaries

        Returns:
            List of author records
        """
        authors = []

        for paper in papers:
            paper_id = paper["paperId"]
            paper_authors = paper.get("authors", [])

            for author in paper_authors:
                authors.append(
                    {
                        "paper_id": paper_id,
                        "author_id": author.get("authorId") or str(uuid.uuid4()),
                        "author_name": author.get("name", ""),
                    }
                )

        return authors

    def _transform_citations(
        self, references: List[Dict[str, Any]], citations: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Transform references and citations to citations table format.

        Args:
            references: List of reference relationships
            citations: List of citation relationships

        Returns:
            Combined list of citation records
        """
        transformed = []

        # Transform references
        for ref in references:
            transformed.append(
                {
                    "fromPaperId": ref["fromPaperId"],
                    "toPaperId": ref["toPaperId"],
                    "timestamp": datetime.utcnow(),
                    "isInfluential": ref.get("isInfluential", False),
                    "contexts": ref.get("contexts", []),
                    "intents": ref.get("intents", []),
                    "direction": ref.get("direction", "backward"),
                }
            )

        # Transform citations
        for cit in citations:
            # Check for duplicates (same relationship might be in both lists)
            existing = any(
                c["fromPaperId"] == cit["fromPaperId"]
                and c["toPaperId"] == cit["toPaperId"]
                for c in transformed
            )

            if not existing:
                transformed.append(
                    {
                        "fromPaperId": cit["fromPaperId"],
                        "toPaperId": cit["toPaperId"],
                        "timestamp": datetime.utcnow(),
                        "isInfluential": cit.get("isInfluential", False),
                        "contexts": cit.get("contexts", []),
                        "intents": cit.get("intents", []),
                        "direction": cit.get("direction", "forward"),
                    }
                )

        return transformed
