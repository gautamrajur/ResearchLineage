"""Data acquisition task - Fetch paper metadata from APIs."""
import logging
from typing import Dict, Any, List, Set, Optional
from src.api.semantic_scholar import SemanticScholarClient
from src.cache.redis_client import RedisCache
from src.utils.errors import APIError, ValidationError
from src.utils.config import settings

logger = logging.getLogger(__name__)


class DataAcquisitionTask:
    """Fetch paper metadata and citation network from Semantic Scholar."""

    def __init__(self):
        """Initialize task with API client and cache."""
        self.cache = RedisCache()
        self.api_client = SemanticScholarClient(cache=self.cache)
        self.fetched_papers: Set[str] = set()

    async def execute(
        self, paper_id: str, max_depth: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Fetch paper and its citation network recursively.

        Args:
            paper_id: Starting paper ID (ArXiv, DOI, or Semantic Scholar ID)
            max_depth: Maximum recursion depth (default from settings)

        Returns:
            Dictionary containing all fetched papers and citations
        """
        max_depth = max_depth or settings.max_citation_depth

        logger.info(
            f"Starting data acquisition for paper {paper_id}, max_depth={max_depth}"
        )

        # Validate inputs
        self._validate_inputs(paper_id, max_depth)

        # Reset state
        self.fetched_papers.clear()

        # Fetch recursively
        all_papers: List[Dict[str, Any]] = []
        all_references: List[Dict[str, Any]] = []
        all_citations: List[Dict[str, Any]] = []

        try:
            await self._fetch_recursive(
                paper_id=paper_id,
                current_depth=0,
                max_depth=max_depth,
                all_papers=all_papers,
                all_references=all_references,
                all_citations=all_citations,
            )

            result = {
                "target_paper_id": paper_id,
                "papers": all_papers,
                "references": all_references,
                "citations": all_citations,
                "total_papers": len(all_papers),
                "total_references": len(all_references),
                "total_citations": len(all_citations),
            }

            # Validate outputs
            self._validate_outputs(result)

            logger.info(
                f"Completed data acquisition: {result['total_papers']} papers, "
                f"{result['total_references']} references, "
                f"{result['total_citations']} citations"
            )

            return result

        except Exception as e:
            logger.error(f"Data acquisition failed: {e}")
            raise
        finally:
            await self.api_client.close()

    async def _fetch_recursive(
        self,
        paper_id: str,
        current_depth: int,
        max_depth: int,
        all_papers: List[Dict[str, Any]],
        all_references: List[Dict[str, Any]],
        all_citations: List[Dict[str, Any]],
    ):
        """
        Recursively fetch paper and its references.

        Args:
            paper_id: Paper to fetch
            current_depth: Current recursion depth
            max_depth: Maximum recursion depth
            all_papers: Accumulator for all papers
            all_references: Accumulator for all references
            all_citations: Accumulator for all citations
        """
        # Skip if already fetched
        if paper_id in self.fetched_papers:
            logger.debug(f"Paper {paper_id} already fetched, skipping")
            return

        # Skip if max depth exceeded
        if current_depth > max_depth:
            logger.debug(f"Max depth {max_depth} reached, stopping recursion")
            return

        self.fetched_papers.add(paper_id)

        try:
            # Fetch paper metadata
            paper_data = await self.api_client.get_paper(paper_id)
            all_papers.append(paper_data)

            # Fetch references (papers cited by this paper)
            references = await self.api_client.get_references(
                paper_id, limit=settings.max_papers_per_level
            )

            for ref in references:
                cited_paper = ref.get("citedPaper", {})
                cited_paper_id = cited_paper.get("paperId")

                if cited_paper_id:
                    # Store reference relationship
                    all_references.append(
                        {
                            "fromPaperId": paper_id,
                            "toPaperId": cited_paper_id,
                            "contexts": ref.get("contexts", []),
                            "intents": ref.get("intents", []),
                            "isInfluential": ref.get("isInfluential", False),
                        }
                    )

                    # Recursively fetch referenced paper
                    if current_depth < max_depth:
                        await self._fetch_recursive(
                            paper_id=cited_paper_id,
                            current_depth=current_depth + 1,
                            max_depth=max_depth,
                            all_papers=all_papers,
                            all_references=all_references,
                            all_citations=all_citations,
                        )

            # Fetch citations (papers citing this paper) - only at depth 0
            if current_depth == 0:
                citations = await self.api_client.get_citations(
                    paper_id, limit=settings.max_papers_per_level
                )

                for cit in citations:
                    citing_paper = cit.get("citingPaper", {})
                    citing_paper_id = citing_paper.get("paperId")

                    if citing_paper_id:
                        all_citations.append(
                            {
                                "fromPaperId": citing_paper_id,
                                "toPaperId": paper_id,
                                "contexts": cit.get("contexts", []),
                                "intents": cit.get("intents", []),
                                "isInfluential": cit.get("isInfluential", False),
                            }
                        )

        except APIError as e:
            logger.warning(f"Failed to fetch paper {paper_id}: {e}")

    def _validate_inputs(self, paper_id: str, max_depth: int):
        """Validate task inputs."""
        if not paper_id or not isinstance(paper_id, str):
            raise ValidationError("Invalid paper_id: must be non-empty string")

        if not isinstance(max_depth, int) or max_depth < 1 or max_depth > 5:
            raise ValidationError("Invalid max_depth: must be integer between 1 and 5")

    def _validate_outputs(self, result: Dict[str, Any]):
        """Validate task outputs."""
        required_keys = ["target_paper_id", "papers", "references", "citations"]
        for key in required_keys:
            if key not in result:
                raise ValidationError(f"Missing required output key: {key}")

        if not result["papers"]:
            raise ValidationError("No papers fetched")
