"""ID mapping utilities for cross-API paper identification."""
from typing import Optional, Dict, Any
from src.utils.logging import get_logger

logger = get_logger(__name__)


class IDMapper:
    """Map paper IDs between different APIs."""

    @staticmethod
    def extract_doi(paper_data: Dict[str, Any]) -> Optional[str]:
        """
        Extract DOI from paper data.

        Args:
            paper_data: Paper metadata from any API

        Returns:
            DOI string or None
        """
        # Semantic Scholar format
        external_ids = paper_data.get("externalIds", {})
        if external_ids and external_ids.get("DOI"):
            return external_ids["DOI"]

        # OpenAlex format
        doi = paper_data.get("doi", "")
        if doi:
            return doi.replace("https://doi.org/", "")

        return None

    @staticmethod
    def extract_arxiv_id(paper_data: Dict[str, Any]) -> Optional[str]:
        """
        Extract ArXiv ID from paper data.

        Args:
            paper_data: Paper metadata from any API

        Returns:
            ArXiv ID or None
        """
        # Semantic Scholar format
        external_ids = paper_data.get("externalIds", {})
        if external_ids and external_ids.get("ArXiv"):
            return external_ids["ArXiv"]

        # OpenAlex format - check IDs list
        for identifier in paper_data.get("ids", {}).get("arxiv", []):
            return identifier

        return None

    @staticmethod
    def get_openalex_id(paper_data: Dict[str, Any]) -> Optional[str]:
        """
        Extract OpenAlex ID from paper data.

        Args:
            paper_data: Paper metadata

        Returns:
            OpenAlex ID or None (never empty string; invalid/missing id handled gracefully).
        """
        # From OpenAlex response: require id to be a non-empty string
        openalex_url = paper_data.get("id")
        if isinstance(openalex_url, str) and openalex_url.startswith("https://openalex.org/"):
            segment = openalex_url.rstrip("/").split("/")[-1]
            if segment and segment != "openalex.org":
                return segment
            return None

        # From Semantic Scholar externalIds
        external_ids = paper_data.get("externalIds", {})
        oa = external_ids.get("OpenAlex") if external_ids else None
        if oa:
            return oa
        return None
