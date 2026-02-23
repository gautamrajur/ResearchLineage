"""Data access layer - Repository pattern for database operations."""
from typing import List, Dict, Any, Optional
from sqlalchemy import text
from src.utils.logging import get_logger

logger = get_logger(__name__)


class PaperRepository:
    """Repository for papers table operations."""

    def __init__(self, session):
        """Initialize with database session."""
        self.session = session

    def bulk_upsert(self, papers: List[Dict[str, Any]]) -> int:
        """
        Bulk upsert papers using PostgreSQL ON CONFLICT.

        Args:
            papers: List of paper dictionaries

        Returns:
            Number of papers written
        """
        if not papers:
            return 0

        # PostgreSQL UPSERT query
        upsert_query = text(
            """
            INSERT INTO papers (
                paperId, arxivId, title, abstract, year,
                citationCount, influentialCitationCount, referenceCount,
                venue, urls, first_queried_at, query_count, text_availability
            ) VALUES (
                :paperId, :arxivId, :title, :abstract, :year,
                :citationCount, :influentialCitationCount, :referenceCount,
                :venue, :urls, :first_queried_at, :query_count, :text_availability
            )
            ON CONFLICT (paperId) DO UPDATE SET
                query_count = papers.query_count + 1,
                citationCount = EXCLUDED.citationCount,
                influentialCitationCount = EXCLUDED.influentialCitationCount,
                referenceCount = EXCLUDED.referenceCount
        """
        )

        for paper in papers:
            self.session.execute(upsert_query, paper)

        logger.info(f"Upserted {len(papers)} papers")
        return len(papers)

    def get_by_id(self, paper_id: str) -> Optional[Dict[str, Any]]:
        """
        Get paper by ID from database.

        Args:
            paper_id: Paper ID

        Returns:
            Paper dictionary in API format or None if not found
        """
        query = text(
            """
            SELECT paperId, arxivId, title, abstract, year,
                citationCount, influentialCitationCount, referenceCount,
                venue, urls
            FROM papers
            WHERE paperId = :paper_id
        """
        )

        result = self.session.execute(query, {"paper_id": paper_id})
        row = result.fetchone()

        if not row:
            return None

        # Access by index (guaranteed column order from SELECT)
        paper_dict = {
            "paperId": row[0],
            "title": row[2],
            "abstract": row[3],
            "year": row[4],
            "citationCount": row[5],
            "influentialCitationCount": row[6],
            "referenceCount": row[7],
            "venue": row[8],
            "url": row[9],
            "authors": [],
            "externalIds": {"ArXiv": row[1]} if row[1] else {},
        }

        return paper_dict


class AuthorRepository:
    """Repository for authors table operations."""

    def __init__(self, session):
        """Initialize with database session."""
        self.session = session

    def bulk_insert(self, authors: List[Dict[str, Any]]) -> int:
        """
        Bulk insert authors.

        Args:
            authors: List of author dictionaries

        Returns:
            Number of authors written
        """
        if not authors:
            return 0

        # PostgreSQL INSERT with ON CONFLICT DO NOTHING
        insert_query = text(
            """
            INSERT INTO authors (paper_id, author_id, author_name)
            VALUES (:paper_id, :author_id, :author_name)
            ON CONFLICT (paper_id, author_id) DO NOTHING
        """
        )

        for author in authors:
            self.session.execute(insert_query, author)

        logger.info(f"Inserted {len(authors)} author records")
        return len(authors)


class CitationRepository:
    """Repository for citations table operations."""

    def __init__(self, session):
        """Initialize with database session."""
        self.session = session

    def bulk_upsert(self, citations: List[Dict[str, Any]]) -> int:
        """
        Bulk upsert citations.

        Args:
            citations: List of citation dictionaries

        Returns:
            Number of citations written
        """
        if not citations:
            return 0

        # Convert lists to PostgreSQL arrays
        for cit in citations:
            cit["contexts"] = cit.get("contexts", [])
            cit["intents"] = cit.get("intents", [])

        # PostgreSQL UPSERT query
        upsert_query = text(
            """
            INSERT INTO citations (
                fromPaperId, toPaperId, timestamp, isInfluential,
                contexts, intents, direction
            ) VALUES (
                :fromPaperId, :toPaperId, :timestamp, :isInfluential,
                :contexts, :intents, :direction
            )
            ON CONFLICT (fromPaperId, toPaperId) DO UPDATE SET
                isInfluential = EXCLUDED.isInfluential,
                contexts = EXCLUDED.contexts,
                intents = EXCLUDED.intents,
                direction = EXCLUDED.direction
        """
        )

        for citation in citations:
            self.session.execute(upsert_query, citation)

        logger.info(f"Upserted {len(citations)} citations")
        return len(citations)
