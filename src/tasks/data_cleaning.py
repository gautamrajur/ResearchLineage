"""Data cleaning task - Clean and normalize validated data."""
import re
from typing import Dict, Any, List, Set
from src.utils.logging import get_logger

logger = get_logger(__name__)


class DataCleaningTask:
    """Clean and normalize validated paper data."""

    def execute(self, validated_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Clean and normalize validated data.

        Args:
            validated_data: Output from data validation task

        Returns:
            Cleaned data dictionary
        """
        logger.info("Starting data cleaning")

        # Extract data
        papers = validated_data["papers"]
        references = validated_data["references"]
        citations = validated_data["citations"]

        # Clean papers
        cleaned_papers = self._clean_papers(papers)

        # Remove duplicates
        unique_papers = self._deduplicate_papers(cleaned_papers)

        # Clean references and citations (remove self-citations, deduplicate)
        cleaned_refs = self._clean_references(references)
        cleaned_cits = self._clean_citations(citations)

        # Get valid paper IDs for referential integrity
        valid_paper_ids = {p["paperId"] for p in unique_papers}

        # Filter references/citations to only include valid papers
        filtered_refs = self._filter_references(cleaned_refs, valid_paper_ids)
        filtered_cits = self._filter_citations(cleaned_cits, valid_paper_ids)

        logger.info(
            f"Cleaning complete: {len(unique_papers)} unique papers, "
            f"{len(filtered_refs)} references, {len(filtered_cits)} citations"
        )

        return {
            "target_paper_id": validated_data["target_paper_id"],
            "papers": unique_papers,
            "references": filtered_refs,
            "citations": filtered_cits,
            "cleaning_stats": {
                "original_papers": len(papers),
                "cleaned_papers": len(unique_papers),
                "duplicates_removed": len(papers) - len(unique_papers),
                "original_references": len(references),
                "cleaned_references": len(filtered_refs),
                "references_removed": len(references) - len(filtered_refs),
                "original_citations": len(citations),
                "cleaned_citations": len(filtered_cits),
                "citations_removed": len(citations) - len(filtered_cits),
            },
        }

    def _clean_papers(self, papers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Clean individual paper records."""
        cleaned = []

        for paper in papers:
            cleaned_paper = paper.copy()

            # Clean title
            if cleaned_paper.get("title"):
                cleaned_paper["title"] = self._clean_text(cleaned_paper["title"])

            # Clean abstract
            if cleaned_paper.get("abstract"):
                cleaned_paper["abstract"] = self._clean_text(cleaned_paper["abstract"])

            # Clean venue
            if cleaned_paper.get("venue"):
                cleaned_paper["venue"] = self._normalize_venue(cleaned_paper["venue"])

            # Clean author names
            if cleaned_paper.get("authors"):
                cleaned_paper["authors"] = [
                    {**author, "name": self._clean_text(author.get("name", ""))}
                    for author in cleaned_paper["authors"]
                ]

            # Ensure citationCount is not negative
            if cleaned_paper.get("citationCount", 0) < 0:
                cleaned_paper["citationCount"] = 0

            if cleaned_paper.get("influentialCitationCount", 0) < 0:
                cleaned_paper["influentialCitationCount"] = 0

            cleaned.append(cleaned_paper)

        return cleaned

    def _clean_text(self, text: str) -> str:
        """Clean and normalize text."""
        if not text:
            return ""

        # Remove extra whitespace
        text = re.sub(r"\s+", " ", text)

        # Trim
        text = text.strip()

        # Remove control characters
        text = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", text)

        return text

    def _normalize_venue(self, venue: str) -> str:
        """Normalize venue names."""
        if not venue:
            return ""

        # Common abbreviations
        venue = venue.strip()

        # Normalize common conference/journal variations
        replacements = {
            "conf": "Conference",
            "proc": "Proceedings",
            "int'l": "International",
            "intl": "International",
            "symp": "Symposium",
            "trans": "Transactions",
        }

        for abbr, full in replacements.items():
            venue = re.sub(rf"\b{abbr}\b", full, venue, flags=re.IGNORECASE)

        return self._clean_text(venue)

    def _deduplicate_papers(self, papers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove duplicate papers based on paperId."""
        seen_ids: Set[str] = set()
        unique_papers = []

        for paper in papers:
            paper_id = paper.get("paperId")
            if paper_id and paper_id not in seen_ids:
                seen_ids.add(paper_id)
                unique_papers.append(paper)
            else:
                logger.debug(f"Duplicate paper removed: {paper_id}")

        return unique_papers

    def _clean_references(
        self, references: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Clean reference records."""
        cleaned = []
        seen = set()

        for ref in references:
            from_id = ref.get("fromPaperId")
            to_id = ref.get("toPaperId")

            # Skip self-citations
            if from_id == to_id:
                logger.debug(f"Self-citation removed: {from_id}")
                continue

            # Skip duplicates
            key = (from_id, to_id)
            if key in seen:
                continue

            seen.add(key)
            cleaned.append(ref)

        return cleaned

    def _clean_citations(self, citations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Clean citation records."""
        cleaned = []
        seen = set()

        for cit in citations:
            from_id = cit.get("fromPaperId")
            to_id = cit.get("toPaperId")

            # Skip self-citations
            if from_id == to_id:
                logger.debug(f"Self-citation removed: {from_id}")
                continue

            # Skip duplicates
            key = (from_id, to_id)
            if key in seen:
                continue

            seen.add(key)
            cleaned.append(cit)

        return cleaned

    def _filter_references(
        self, references: List[Dict[str, Any]], valid_paper_ids: Set[str]
    ) -> List[Dict[str, Any]]:
        """Filter references to only include valid papers."""
        filtered = []

        for ref in references:
            from_id = ref.get("fromPaperId")
            to_id = ref.get("toPaperId")

            # Both papers must exist in our dataset
            if from_id in valid_paper_ids and to_id in valid_paper_ids:
                filtered.append(ref)
            else:
                logger.debug(
                    f"Reference filtered due to missing paper: {from_id} -> {to_id}"
                )

        return filtered

    def _filter_citations(
        self, citations: List[Dict[str, Any]], valid_paper_ids: Set[str]
    ) -> List[Dict[str, Any]]:
        """Filter citations to only include valid papers."""
        filtered = []

        for cit in citations:
            from_id = cit.get("fromPaperId")
            to_id = cit.get("toPaperId")

            # Both papers must exist in our dataset
            if from_id in valid_paper_ids and to_id in valid_paper_ids:
                filtered.append(cit)
            else:
                logger.debug(
                    f"Citation filtered due to missing paper: {from_id} -> {to_id}"
                )

        return filtered
