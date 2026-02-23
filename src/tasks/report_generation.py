"""Report generation task - Generate database statistics report."""
from datetime import datetime
from typing import Dict, Any
from sqlalchemy import text
from src.database.connection import DatabaseConnection
from src.utils.logging import get_logger

logger = get_logger(__name__)


class ReportGenerationTask:
    """Generate database statistics and pipeline report."""

    def execute(self, write_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate comprehensive database statistics report.

        Args:
            write_result: Output from database write task

        Returns:
            Statistics report
        """
        logger.info("Starting report generation")

        db = DatabaseConnection()

        try:
            with db.get_session() as session:
                # Get database statistics
                stats = {}

                # Count papers
                result = session.execute(text("SELECT COUNT(*) FROM papers"))
                stats["total_papers"] = result.scalar()

                # Count authors
                result = session.execute(text("SELECT COUNT(*) FROM authors"))
                stats["total_authors"] = result.scalar()

                # Count unique authors
                result = session.execute(
                    text("SELECT COUNT(DISTINCT author_name) FROM authors")
                )
                stats["unique_authors"] = result.scalar()

                # Count citations
                result = session.execute(text("SELECT COUNT(*) FROM citations"))
                stats["total_citations"] = result.scalar()

                # Citations by direction
                result = session.execute(
                    text(
                        """
                    SELECT direction, COUNT(*) as count
                    FROM citations
                    GROUP BY direction
                """
                    )
                )
                stats["citations_by_direction"] = {row[0]: row[1] for row in result}

                # Papers by year
                result = session.execute(
                    text(
                        """
                    SELECT year, COUNT(*) as count
                    FROM papers
                    WHERE year IS NOT NULL
                    GROUP BY year
                    ORDER BY year
                """
                    )
                )
                stats["papers_by_year"] = {row[0]: row[1] for row in result}

                # Top venues
                result = session.execute(
                    text(
                        """
                    SELECT venue, COUNT(*) as count
                    FROM papers
                    WHERE venue IS NOT NULL AND venue != ''
                    GROUP BY venue
                    ORDER BY count DESC
                    LIMIT 10
                """
                    )
                )
                stats["top_venues"] = [
                    {"venue": row[0], "count": row[1]} for row in result
                ]

                # Citation statistics
                result = session.execute(
                    text(
                        """
                    SELECT
                        MIN(citationCount) as min_citations,
                        MAX(citationCount) as max_citations,
                        AVG(citationCount)::int as avg_citations
                    FROM papers
                """
                    )
                )
                row = result.fetchone()
                stats["citation_stats"] = {"min": row[0], "max": row[1], "avg": row[2]}

                # Year range
                result = session.execute(
                    text(
                        """
                    SELECT MIN(year) as earliest, MAX(year) as latest
                    FROM papers
                    WHERE year IS NOT NULL
                """
                    )
                )
                row = result.fetchone()
                stats["year_range"] = {"earliest": row[0], "latest": row[1]}

                # Log statistics
                logger.info("\n" + "=" * 60)
                logger.info("DATABASE STATISTICS REPORT")
                logger.info("=" * 60)
                logger.info(f"Total Papers: {stats['total_papers']}")
                logger.info(
                    f"Total Authors: {stats['total_authors']} ({stats['unique_authors']} unique)"
                )
                logger.info(f"Total Citations: {stats['total_citations']}")
                logger.info(
                    f"  Backward: {stats['citations_by_direction'].get('backward', 0)}"
                )
                logger.info(
                    f"  Forward: {stats['citations_by_direction'].get('forward', 0)}"
                )
                logger.info(
                    f"Year Range: {stats['year_range']['earliest']} - {stats['year_range']['latest']}"
                )
                logger.info(
                    f"Citation Range: {stats['citation_stats']['min']} - {stats['citation_stats']['max']:,} (avg: {stats['citation_stats']['avg']:,})"
                )
                logger.info("\nTop Venues:")
                for venue in stats["top_venues"][:5]:
                    logger.info(f"  {venue['venue']}: {venue['count']} papers")
                logger.info("=" * 60)

                # Save report to file
                report_data = {
                    "target_paper_id": write_result["target_paper_id"],
                    "database_stats": stats,
                    "write_stats": write_result.get("write_stats", {}),
                    "generated_at": datetime.utcnow().isoformat(),
                }

                # Save as JSON
                from pathlib import Path
                import json

                report_file = (
                    Path("/opt/airflow/logs")
                    / f"report_{write_result['target_paper_id']}.json"
                )
                report_file.write_text(json.dumps(report_data, indent=2))

                logger.info(f"Report saved to: {report_file}")

                return {
                    "target_paper_id": write_result["target_paper_id"],
                    "database_stats": stats,
                    "write_stats": write_result.get("write_stats", {}),
                    "quality_report": write_result.get("quality_report", {}),
                    "anomaly_report": write_result.get("anomaly_report", {}),
                    "report_file": str(report_file),
                }

        except Exception as e:
            logger.error(f"Report generation failed: {e}")
            raise
