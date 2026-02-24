"""OpenAlex API client."""
from typing import Optional, Dict, Any, List
from src.api.base import BaseAPIClient
from src.utils.config import settings
from src.cache.redis_client import RedisCache
from src.utils.logging import get_logger

logger = get_logger(__name__)


class OpenAlexClient(BaseAPIClient):
    """OpenAlex API client for fallback citation data."""

    # In src/api/openalex.py, __init__ method:
    def __init__(self, cache: Optional[RedisCache] = None):
        """
        Initialize OpenAlex client.

        Args:
            cache: Redis cache instance (optional)
        """
        # No rate limiter for OpenAlex
        super().__init__(base_url=settings.openalex_base_url, rate_limiter=None)
        self.cache = cache

    async def get_paper(self, paper_id: str) -> Dict[str, Any]:
        """
        Get paper metadata by OpenAlex ID.

        Args:
            paper_id: OpenAlex work ID

        Returns:
            Paper metadata dictionary
        """
        cache_key = f"openalex:paper:{paper_id}"

        if self.cache:
            cached = self.cache.get(cache_key)
            if cached:
                return cached

        async def fetch():
            return await self._make_request(method="GET", endpoint=f"works/{paper_id}")

        try:
            result = await self._retry_with_backoff(fetch)

            if self.cache and result:
                self.cache.set(cache_key, result)

            return self.convert_to_semantic_scholar_format(result)
        except Exception as e:
            logger.warning(f"Failed to fetch paper {paper_id}: {e}")
            raise

    async def get_paper_by_doi(self, doi: str) -> Optional[Dict[str, Any]]:
        """
        Get paper by DOI.

        Args:
            doi: DOI identifier

        Returns:
            Paper metadata or None if not found
        """
        cache_key = f"openalex:doi:{doi}"

        if self.cache:
            cached = self.cache.get(cache_key)
            if cached:
                return cached

        async def fetch():
            return await self._make_request(
                method="GET", endpoint=f"works/https://doi.org/{doi}"
            )

        try:
            result = await self._retry_with_backoff(fetch)

            if self.cache and result:
                self.cache.set(cache_key, result)

            return result
        except Exception as e:
            logger.warning(f"Failed to fetch paper by DOI {doi}: {e}")
            return None

    async def search_by_title(self, title: str) -> List[Dict[str, Any]]:
        """
        Search papers by title.

        Args:
            title: Paper title

        Returns:
            List of matching papers
        """
        cache_key = f"openalex:search:{title}"

        if self.cache:
            cached = self.cache.get(cache_key)
            if cached:
                return cached

        async def fetch():
            return await self._make_request(
                method="GET",
                endpoint="works",
                params={"filter": f"title.search:{title}", "per-page": 5},
            )

        try:
            result = await self._retry_with_backoff(fetch)
            papers = result.get("results", []) if result else []

            if self.cache and papers:
                self.cache.set(cache_key, papers)

            return papers
        except Exception as e:
            logger.warning(f"Failed to search by title {title}: {e}")
            return []

    async def get_citations(
        self, openalex_id: str, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get papers citing this work.

        Args:
            openalex_id: OpenAlex work ID
            limit: Maximum citations to retrieve

        Returns:
            List of citing papers
        """
        cache_key = f"openalex:citations:{openalex_id}"

        if self.cache:
            cached = self.cache.get(cache_key)
            if cached:
                return cached

        async def fetch():
            return await self._make_request(
                method="GET",
                endpoint="works",
                params={"filter": f"cites:{openalex_id}", "per-page": min(limit, 200)},
            )

        try:
            result = await self._retry_with_backoff(fetch)
            citations = result.get("results", []) if result else []

            if self.cache and citations:
                self.cache.set(cache_key, citations)

            logger.info(
                f"Fetched {len(citations)} citations from OpenAlex for {openalex_id}"
            )
            return citations
        except Exception as e:
            logger.warning(f"Failed to get citations for {openalex_id}: {e}")
            return []

    def convert_to_semantic_scholar_format(
        self, openalex_paper: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Convert OpenAlex paper format to Semantic Scholar format.

        Args:
            openalex_paper: Paper in OpenAlex format

        Returns:
            Paper in Semantic Scholar-compatible format
        """
        # Extract basic info (id/doi may be None or non-string from API)
        raw_id = openalex_paper.get("id") or ""
        paper_id = raw_id.split("/")[-1] if isinstance(raw_id, str) else ""

        raw_doi = openalex_paper.get("doi") or ""
        doi = raw_doi.replace("https://doi.org/", "") if isinstance(raw_doi, str) else ""

        # Extract authors
        authors = []
        for authorship in openalex_paper.get("authorships", []):
            author = authorship.get("author", {})
            authors.append(
                {
                    "authorId": author.get("id", "").split("/")[-1],
                    "name": author.get("display_name", ""),
                }
            )

        return {
            "paperId": paper_id,
            "title": openalex_paper.get("display_name", ""),
            "abstract": openalex_paper.get("abstract", ""),
            "year": openalex_paper.get("publication_year"),
            "citationCount": openalex_paper.get("cited_by_count", 0),
            "influentialCitationCount": 0,
            "referenceCount": len(openalex_paper.get("referenced_works", [])),
            "authors": authors,
            "externalIds": {"DOI": doi, "OpenAlex": paper_id},
            "venue": openalex_paper.get("primary_location", {})
            .get("source", {})
            .get("display_name", ""),
            "url": openalex_paper.get("id", ""),
        }
