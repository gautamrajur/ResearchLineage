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

    async def _fetch_citations_with_fallback(
        self, paper_id: str, paper_data: Dict[str, Any], limit: int
    ) -> List[Dict[str, Any]]:
        """
        Fetch citations with OpenAlex fallback.

        Args:
            paper_id: Semantic Scholar paper ID
            paper_data: Paper metadata
            limit: Max citations to fetch

        Returns:
            List of citations
        """
        try:
            citations = await self.api_client.get_citations(paper_id, limit=limit)
            if citations:
                return citations
            logger.info(
                f"No citations from Semantic Scholar, trying OpenAlex for {paper_id}"
            )
        except Exception as e:
            logger.warning(f"Semantic Scholar citations failed for {paper_id}: {e}")

        try:
            logger.info(f"Falling back to OpenAlex for citations of {paper_id}")

            doi = self.id_mapper.extract_doi(paper_data)

            if doi:
                openalex_paper = await self.openalex_client.get_paper_by_doi(doi)
                if openalex_paper:
                    openalex_id = self.id_mapper.get_openalex_id(openalex_paper)
                    if openalex_id:
                        openalex_citations = await self.openalex_client.get_citations(
                            openalex_id, limit=limit
                        )

                        converted_citations = []
                        for cit in openalex_citations:
                            converted = (
                                self.openalex_client.convert_to_semantic_scholar_format(
                                    cit
                                )
                            )
                            converted_citations.append(
                                {
                                    "fromPaperId": converted["paperId"],
                                    "toPaperId": paper_id,
                                    "contexts": [],
                                    "intents": [],
                                    "isInfluential": False,
                                    "direction": "forward",
                                }
                            )

                        logger.info(
                            f"Fetched {len(converted_citations)} citations from OpenAlex"
                        )
                        return converted_citations

            title = paper_data.get("title", "")
            if title:
                results = await self.openalex_client.search_by_title(title)
                if results:
                    openalex_id = self.id_mapper.get_openalex_id(results[0])
                    if openalex_id:
                        openalex_citations = await self.openalex_client.get_citations(
                            openalex_id, limit=limit
                        )

                        converted_citations = []
                        for cit in openalex_citations:
                            converted = (
                                self.openalex_client.convert_to_semantic_scholar_format(
                                    cit
                                )
                            )
                            converted_citations.append(
                                {
                                    "fromPaperId": converted["paperId"],
                                    "toPaperId": paper_id,
                                    "contexts": [],
                                    "intents": [],
                                    "isInfluential": False,
                                    "direction": "forward",
                                }
                            )

                        return converted_citations

        except Exception as e:
            logger.error(f"OpenAlex fallback failed for {paper_id}: {e}")

        return []

    def _filter_references_for_recursion(
        self, references: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Filter references before recursive fetching to reduce API calls.

        Filters by:
        - Citation intent (methodology, background)
        - Influential citations
        - Citation count of cited paper

        Args:
            references: List of reference dictionaries

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
        max_papers = settings.max_papers_per_level

        top_refs: List[Dict[str, Any]] = [
            item["reference"] for item in scored_refs[:max_papers]
        ]

        logger.info(
            f"Filtered references: {len(references)} -> {len(top_refs)} "
            f"(kept methodology/background with high impact)"
        )

        return top_refs

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

                filtered_refs = self._filter_references_for_recursion(references)

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
