"""Database write task - Persist data to PostgreSQL."""
from typing import Dict, Any
from src.database.connection import DatabaseConnection
from src.database.repositories import (
    PaperRepository,
    AuthorRepository,
    CitationRepository,
)
from src.utils.logging import get_logger
from src.utils.errors import DatabaseError

logger = get_logger(__name__)


class DatabaseWriteTask:
    """Write validated data to PostgreSQL database."""

    def __init__(self):
        """Initialize database connection."""
        self.db = DatabaseConnection()

    def execute(self, final_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Write data to database.

        Args:
            final_data: Output from anomaly detection

        Returns:
            Write statistics
        """
        logger.info("Starting database write")

        papers = final_data["papers_table"]
        authors = final_data["authors_table"]
        citations = final_data["citations_table"]

        try:
            with self.db.get_session() as session:
                # Initialize repositories
                paper_repo = PaperRepository(session)
                author_repo = AuthorRepository(session)
                citation_repo = CitationRepository(session)

                # Write papers
                papers_written = paper_repo.bulk_upsert(papers)

                # Write authors
                authors_written = author_repo.bulk_insert(authors)

                # Write citations
                citations_written = citation_repo.bulk_upsert(citations)

                logger.info(
                    f"Database write complete: {papers_written} papers, "
                    f"{authors_written} authors, {citations_written} citations"
                )

                return {
                    "target_paper_id": final_data["target_paper_id"],
                    "write_stats": {
                        "papers_written": papers_written,
                        "authors_written": authors_written,
                        "citations_written": citations_written,
                    },
                    "quality_report": final_data["quality_report"],
                    "anomaly_report": final_data["anomaly_report"],
                }

        except Exception as e:
            logger.error(f"Database write failed: {e}")
            raise DatabaseError(f"Failed to write to database: {e}")
