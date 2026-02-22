"""Data acquisition task - Fetch paper metadata from APIs."""
from typing import Dict, Any, List, Set, Optional
from src.api.semantic_scholar import SemanticScholarClient
from src.api.openalex import OpenAlexClient
from src.utils.id_mapper import IDMapper
from src.cache.redis_client import RedisCache
from src.utils.errors import APIError, ValidationError
from src.utils.config import settings
from src.utils.logging import get_logger

logger = get_logger(__name__)


class DataAcquisitionTask:
    """Fetch paper metadata and citation network from Semantic Scholar."""

    def __init__(self):
        """Initialize task with API client and cache."""
        self.cache = RedisCache()
        self.api_client = SemanticScholarClient(cache=self.cache)
        self.openalex_client = OpenAlexClient(cache=self.cache)
        self.id_mapper = IDMapper()
        self.fetched_papers: Set[str] = set()

    async def execute(
        self,
        paper_id: str,
        max_depth: Optional[int] = None,
        direction: str = "backward",
    ) -> Dict[str, Any]:
        """
        Fetch paper and its citation network.

        Args:
            paper_id: Starting paper ID
            max_depth: Maximum recursion depth (default from settings)
            direction: Fetch direction - "backward" (references), "forward" (citations), or "both"

        Returns:
            Dictionary containing all fetched papers and citations
        """
        max_depth = max_depth or settings.max_citation_depth

        logger.info(
            f"Starting data acquisition for paper {paper_id}, "
            f"max_depth={max_depth}, direction={direction}"
        )

        self._validate_inputs(paper_id, max_depth, direction)

        self.fetched_papers.clear()

        all_papers: List[Dict[str, Any]] = []
        all_references: List[Dict[str, Any]] = []
        all_citations: List[Dict[str, Any]] = []

        try:
            if direction in ["backward", "both"]:
                logger.info("Fetching backward lineage (references)...")
                await self._fetch_recursive(
                    paper_id=paper_id,
                    current_depth=0,
                    max_depth=max_depth,
                    all_papers=all_papers,
                    all_references=all_references,
                    all_citations=all_citations,
                    fetch_direction="backward",
                )

            if direction in ["forward", "both"]:
                logger.info("Fetching forward lineage (citations)...")
                if direction == "both":
                    self.fetched_papers.discard(paper_id)

                await self._fetch_recursive(
                    paper_id=paper_id,
                    current_depth=0,
                    max_depth=max_depth,
                    all_papers=all_papers,
                    all_references=all_references,
                    all_citations=all_citations,
                    fetch_direction="forward",
                )

            result = {
                "target_paper_id": paper_id,
                "papers": all_papers,
                "references": all_references,
                "citations": all_citations,
                "total_papers": len(all_papers),
                "total_references": len(all_references),
                "total_citations": len(all_citations),
                "direction": direction,
            }

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

    def _get_max_papers_for_depth(self, current_depth: int) -> int:
        """
        Get maximum papers to fetch based on depth.

        Adaptive strategy:
        - Depth 0 (target): 5 papers
        - Depth 1: 5 papers
        - Depth 2: 3 papers
        - Depth 3+: 2 papers

        Args:
            current_depth: Current recursion depth

        Returns:
            Maximum papers to fetch at this depth
        """
        if current_depth <= 1:
            return settings.max_papers_per_level
        elif current_depth == 2:
            return 3
        else:
            return 2

    def _filter_references_for_recursion(
        self, references: List[Dict[str, Any]], current_depth: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Filter references before recursive fetching to reduce API calls.

        Filters by:
        - Citation intent (methodology, background)
        - Influential citations
        - Citation count of cited paper

        Args:
            references: List of reference dictionaries
            current_depth: Current recursion depth for adaptive limits

        Returns:
            Filtered list of top references to explore
        """
        relevant_refs = []

        for ref in references:
            intents = ref.get("intents", [])
            is_influential = ref.get("isInfluential", False)

            if "methodology" in intents or "background" in intents or is_influential:
                relevant_refs.append(ref)

        scored_refs: List[Dict[str, Any]] = []
        for ref in relevant_refs:
            cited_paper = ref.get("citedPaper", {})
            citation_count = cited_paper.get("citationCount", 0) or 0

            score = citation_count

            if ref.get("isInfluential", False):
                score += 10000

            if "methodology" in ref.get("intents", []):
                score += 5000

            scored_refs.append({"reference": ref, "score": score})

        scored_refs.sort(key=lambda x: float(x["score"]), reverse=True)

        # Adaptive limit based on depth
        max_papers = self._get_max_papers_for_depth(current_depth)

        top_refs: List[Dict[str, Any]] = [
            item["reference"] for item in scored_refs[:max_papers]
        ]

        logger.info(
            f"Filtered references (depth {current_depth}): {len(references)} -> {len(top_refs)} "
            f"(limit: {max_papers})"
        )

        return top_refs

    def _filter_citations_for_recursion(
        self,
        citations: List[Dict[str, Any]],
        paper_data: Dict[str, Any],
        current_depth: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        Filter forward citations before recursive fetching.

        Filters by:
        - Methodology intent (primary)
        - Influential citations (fallback)
        - Remove irrelevant domains (medical, clinical)
        - Citation count of citing paper

        Args:
            citations: List of citation dictionaries from API
            paper_data: Target paper metadata
            current_depth: Current recursion depth for adaptive limits

        Returns:
            Filtered citations for recursion
        """
        # Filter by intent
        methodology_cites = []

        for cit in citations:
            intents = cit.get("intents", [])
            is_influential = cit.get("isInfluential", False)

            if "methodology" in intents or is_influential:
                methodology_cites.append(cit)

        # Filter out irrelevant domains
        irrelevant_keywords = [
            "medical",
            "clinical",
            "disease",
            "patient",
            "diagnosis",
            "ecg",
            "mri",
            "ct scan",
            "imaging",
            "radiology",
            "tooth",
            "dental",
            "retinal",
            "octa",
            "tumor",
            "cancer",
            "segmentation",
            "lung",
            "liver",
            "brain",
            "heart",
        ]

        relevant_cites = []
        for cit in methodology_cites:
            citing_paper = cit.get("citingPaper", {})
            title = citing_paper.get("title", "").lower()

            if not any(keyword in title for keyword in irrelevant_keywords):
                cit["citingPaperId"] = citing_paper.get("paperId")
                relevant_cites.append(cit)
            else:
                logger.debug(f"Filtered irrelevant paper: {title[:50]}")

        # Score by citation count
        scored_cites: List[Dict[str, Any]] = []
        for cit in relevant_cites:
            citing_paper = cit.get("citingPaper", {})
            citation_count = citing_paper.get("citationCount", 0) or 0

            score = citation_count

            if cit.get("isInfluential", False):
                score += 5000

            if "methodology" in cit.get("intents", []):
                score += 2000

            scored_cites.append({"citation": cit, "score": score})

        # Sort and take top N with adaptive limit
        scored_cites.sort(key=lambda x: float(x["score"]), reverse=True)
        max_cites = min(3, self._get_max_papers_for_depth(current_depth))

        top_cites: List[Dict[str, Any]] = [
            item["citation"] for item in scored_cites[:max_cites]
        ]

        logger.info(
            f"Filtered citations (depth {current_depth}): {len(citations)} -> {len(top_cites)} "
            f"(limit: {max_cites}, removed {len(citations) - len(relevant_cites)} irrelevant)"
        )

        return top_cites

    async def _fetch_recursive(
        self,
        paper_id: str,
        current_depth: int,
        max_depth: int,
        all_papers: List[Dict[str, Any]],
        all_references: List[Dict[str, Any]],
        all_citations: List[Dict[str, Any]],
        fetch_direction: str = "backward",
    ):
        """
        Recursively fetch paper and its relationships.

        Args:
            paper_id: Paper to fetch
            current_depth: Current recursion depth
            max_depth: Maximum recursion depth
            all_papers: Accumulator for all papers
            all_references: Accumulator for all references
            all_citations: Accumulator for all citations
            fetch_direction: "backward" (references) or "forward" (citations)
        """
        if paper_id in self.fetched_papers:
            logger.debug(f"Paper {paper_id} already fetched, skipping")
            return

        if current_depth > max_depth:
            logger.debug(f"Max depth {max_depth} reached, stopping recursion")
            return

        self.fetched_papers.add(paper_id)

        try:
            paper_data = await self.api_client.get_paper(paper_id)
            all_papers.append(paper_data)

            if fetch_direction == "backward":
                references = await self.api_client.get_references(
                    paper_id,
                    limit=100,
                )

                # Filter with depth-aware limits
                filtered_refs = self._filter_references_for_recursion(
                    references, current_depth
                )

                for ref in filtered_refs:
                    cited_paper = ref.get("citedPaper", {})
                    cited_paper_id = cited_paper.get("paperId")

                    if cited_paper_id:
                        all_references.append(
                            {
                                "fromPaperId": paper_id,
                                "toPaperId": cited_paper_id,
                                "contexts": ref.get("contexts", []),
                                "intents": ref.get("intents", []),
                                "isInfluential": ref.get("isInfluential", False),
                                "direction": "backward",
                            }
                        )

                        if current_depth < max_depth:
                            await self._fetch_recursive(
                                paper_id=cited_paper_id,
                                current_depth=current_depth + 1,
                                max_depth=max_depth,
                                all_papers=all_papers,
                                all_references=all_references,
                                all_citations=all_citations,
                                fetch_direction="backward",
                            )

            elif fetch_direction == "forward":
                # Use year range filtering at API level
                paper_year = paper_data.get("year")
                year_range = None

                if paper_year:
                    window_years = 3
                    start_year = paper_year + 1
                    end_year = paper_year + window_years
                    year_range = f"{start_year}:{end_year}"
                    logger.info(f"Fetching citations in year range: {year_range}")

                citations = await self.api_client.get_citations(
                    paper_id, limit=1000, year_range=year_range
                )

                # Filter with depth-aware limits
                filtered_cits = self._filter_citations_for_recursion(
                    citations, paper_data, current_depth
                )

                for cit in filtered_cits:
                    citing_paper_id = cit.get("citingPaperId")

                    if citing_paper_id:
                        all_citations.append(
                            {
                                "fromPaperId": citing_paper_id,
                                "toPaperId": paper_id,
                                "contexts": cit.get("contexts", []),
                                "intents": cit.get("intents", []),
                                "isInfluential": cit.get("isInfluential", False),
                                "direction": "forward",
                            }
                        )

                        if current_depth < max_depth:
                            await self._fetch_recursive(
                                paper_id=citing_paper_id,
                                current_depth=current_depth + 1,
                                max_depth=max_depth,
                                all_papers=all_papers,
                                all_references=all_references,
                                all_citations=all_citations,
                                fetch_direction="forward",
                            )

        except APIError as e:
            logger.warning(f"Failed to fetch paper {paper_id}: {e}")

    async def close(self):
        """Close API client connections."""
        await self.api_client.close()
        await self.openalex_client.close()

    def _validate_inputs(self, paper_id: str, max_depth: int, direction: str):
        """Validate task inputs."""
        if not paper_id or not isinstance(paper_id, str):
            raise ValidationError("Invalid paper_id: must be non-empty string")

        if not isinstance(max_depth, int) or max_depth < 1 or max_depth > 5:
            raise ValidationError("Invalid max_depth: must be integer between 1 and 5")

        if direction not in ["backward", "forward", "both"]:
            raise ValidationError(
                "Invalid direction: must be 'backward', 'forward', or 'both'"
            )

    def _validate_outputs(self, result: Dict[str, Any]):
        """Validate task outputs."""
        required_keys = ["target_paper_id", "papers", "references", "citations"]
        for key in required_keys:
            if key not in result:
                raise ValidationError(f"Missing required output key: {key}")

        if not result["papers"]:
            raise ValidationError("No papers fetched")
