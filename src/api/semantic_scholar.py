"""Semantic Scholar API client."""
import logging
from typing import Optional, Dict, Any, List
from src.api.base import BaseAPIClient, RateLimiter
from src.models.api_models import PaperResponse
from src.utils.config import settings
from src.cache.redis_client import RedisCache

logger = logging.getLogger(__name__)


class SemanticScholarClient(BaseAPIClient):
    """Semantic Scholar API client with caching."""

    def __init__(self, cache: Optional[RedisCache] = None):
        """
        Initialize Semantic Scholar client.

        Args:
            cache: Redis cache instance (optional)
        """
        rate_limiter = RateLimiter(
            rate_limit=settings.semantic_scholar_rate_limit, time_window=300
        )
        super().__init__(
            base_url=settings.semantic_scholar_base_url, rate_limiter=rate_limiter
        )
        self.cache = cache
        self.api_key = settings.semantic_scholar_api_key

    def _get_headers(self) -> Dict[str, str]:
        """Get request headers with API key if available."""
        headers = {}
        if self.api_key:
            headers["x-api-key"] = self.api_key
        return headers

    async def get_paper(
        self, paper_id: str, fields: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get paper metadata by ID.

        Args:
            paper_id: Paper ID (ArXiv ID, DOI, Semantic Scholar ID, etc.)
            fields: Comma-separated fields to retrieve

        Returns:
            Paper metadata dictionary
        """
        cache_key = f"paper:{paper_id}"

        # Check cache first
        if self.cache:
            cached = self.cache.get(cache_key)
            if cached:
                logger.info(f"Cache hit for paper {paper_id}")
                return cached

        # Default fields to retrieve
        if not fields:
            fields = (
                "paperId,title,abstract,year,citationCount,"
                "influentialCitationCount,referenceCount,authors,"
                "externalIds,venue,publicationDate,url"
            )

        # Make API request
        async def fetch():
            return await self._make_request(
                method="GET",
                endpoint=f"paper/{paper_id}",
                params={"fields": fields},
                headers=self._get_headers(),
            )

        result = await self._retry_with_backoff(fetch)

        # Validate with Pydantic
        PaperResponse(**result)

        # Cache result
        if self.cache:
            self.cache.set(cache_key, result)

        logger.info(f"Fetched paper {paper_id}: {result.get('title', 'N/A')}")
        return result

    async def get_references(
        self, paper_id: str, limit: int = 100, offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Get papers referenced by this paper.

        Args:
            paper_id: Paper ID
            limit: Maximum number of references to retrieve
            offset: Pagination offset

        Returns:
            List of reference dictionaries
        """
        cache_key = f"references:{paper_id}:{offset}"

        # Check cache
        if self.cache:
            cached = self.cache.get(cache_key)
            if cached:
                logger.info(f"Cache hit for references of {paper_id}")
                return cached

        # Make API request
        async def fetch():
            return await self._make_request(
                method="GET",
                endpoint=f"paper/{paper_id}/references",
                params={
                    "fields": (
                        "contexts,intents,isInfluential,"
                        "citedPaper.paperId,citedPaper.title,citedPaper.year,"
                        "citedPaper.citationCount,citedPaper.influentialCitationCount"
                    ),
                    "limit": limit,
                    "offset": offset,
                },
                headers=self._get_headers(),
            )

        result = await self._retry_with_backoff(fetch)
        references = (result or {}).get("data") or []

        # Cache result
        if self.cache:
            self.cache.set(cache_key, references)

        logger.info(f"Fetched {len(references)} references for paper {paper_id}")
        return references

    async def get_citations(
        self, paper_id: str, limit: int = 100, offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Get papers citing this paper.

        Args:
            paper_id: Paper ID
            limit: Maximum number of citations to retrieve
            offset: Pagination offset

        Returns:
            List of citation dictionaries
        """
        cache_key = f"citations:{paper_id}:{offset}"

        # Check cache
        if self.cache:
            cached = self.cache.get(cache_key)
            if cached:
                logger.info(f"Cache hit for citations of {paper_id}")
                return cached

        # Make API request
        async def fetch():
            return await self._make_request(
                method="GET",
                endpoint=f"paper/{paper_id}/citations",
                params={
                    "fields": (
                        "contexts,intents,isInfluential,"
                        "citingPaper.paperId,citingPaper.title,citingPaper.year,"
                        "citingPaper.citationCount,citingPaper.influentialCitationCount"
                    ),
                    "limit": limit,
                    "offset": offset,
                },
                headers=self._get_headers(),
            )

        result = await self._retry_with_backoff(fetch)
        citations = (result or {}).get("data") or []

        # Cache result
        if self.cache:
            self.cache.set(cache_key, citations)

        logger.info(f"Fetched {len(citations)} citations for paper {paper_id}")
        return citations
