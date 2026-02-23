"""Anomaly detection task - Detect data anomalies before database write."""
from typing import Dict, Any, List, Tuple
import statistics
from src.utils.logging import get_logger
from src.utils.email_service import EmailConfig, EmailService
from src.utils.config import settings

logger = get_logger(__name__)


def _build_email_service() -> EmailService:
    return EmailService(EmailConfig(
        smtp_host=settings.smtp_host,
        smtp_port=settings.smtp_port,
        smtp_user=settings.smtp_user,
        smtp_password=settings.smtp_password,
        alert_email_from=settings.alert_email_from,
        alert_email_to=settings.alert_email_to,
    ))


class AnomalyDetectionTask:
    """Detect anomalies in validated data."""

    def execute(self, validated_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Detect anomalies in data.

        Args:
            validated_data: Output from quality validation

        Returns:
            Data with anomaly report
        """
        logger.info("Starting anomaly detection")

        papers = validated_data["papers_table"]
        authors = validated_data["authors_table"]
        citations = validated_data["citations_table"]

        # Run anomaly detection
        anomalies = {
            "missing_data": self._detect_missing_data(papers),
            "outliers": self._detect_outliers(papers),
            "citation_anomalies": self._detect_citation_anomalies(citations, papers),
            "disconnected_papers": self._detect_disconnected_papers(papers, citations),
        }

        # Count total anomalies
        total_anomalies = 0
        for category in anomalies.values():
            if isinstance(category, dict):
                for anomaly_list in category.values():
                    if isinstance(anomaly_list, list):
                        total_anomalies += len(anomaly_list)

        # Log anomalies
        if total_anomalies > 0:
            logger.warning(f"Detected {total_anomalies} anomalies")
            for category, results in anomalies.items():
                if isinstance(results, dict):
                    for anomaly_type, anomaly_list in results.items():
                        if anomaly_list:
                            logger.warning(
                                f"  {category}.{anomaly_type}: {len(anomaly_list)} issues"
                            )
            self._send_anomaly_alert(
                target_paper_id=validated_data["target_paper_id"],
                total_anomalies=total_anomalies,
                anomalies=anomalies,
            )
        else:
            logger.info("No anomalies detected")

        return {
            "target_paper_id": validated_data["target_paper_id"],
            "papers_table": papers,
            "authors_table": authors,
            "citations_table": citations,
            "quality_report": validated_data["quality_report"],
            "anomaly_report": {
                "total_anomalies": total_anomalies,
                "anomalies": anomalies,
            },
        }

    def _send_anomaly_alert(
        self,
        target_paper_id: str,
        total_anomalies: int,
        anomalies: Dict[str, Any],
    ) -> None:
        """Send email alert summarising detected anomalies."""
        lines = [
            f"Anomaly detection found {total_anomalies} issue(s) in pipeline run.",
            f"Target paper: {target_paper_id}",
            "",
            "Breakdown:",
        ]
        for category, results in anomalies.items():
            if isinstance(results, dict):
                for anomaly_type, anomaly_list in results.items():
                    if anomaly_list:
                        lines.append(f"  {category}.{anomaly_type}: {len(anomaly_list)}")

        lines += ["", "Check the Airflow logs for full details."]

        _build_email_service().send_alert(
            subject=f"ResearchLineage Anomaly Alert — {total_anomalies} issue(s) detected",
            body="\n".join(lines),
        )

    def _detect_missing_data(
        self, papers: List[Dict[str, Any]]
    ) -> Dict[str, List[str]]:
        """Detect missing critical fields."""
        missing_abstracts = []
        missing_years = []
        missing_venues = []

        for paper in papers:
            paper_id = paper["paperId"]

            if not paper.get("abstract"):
                missing_abstracts.append(paper_id)

            if not paper.get("year"):
                missing_years.append(paper_id)

            if not paper.get("venue"):
                missing_venues.append(paper_id)

        return {
            "missing_abstracts": missing_abstracts,
            "missing_years": missing_years,
            "missing_venues": missing_venues,
        }

    def _detect_outliers(
        self, papers: List[Dict[str, Any]]
    ) -> Dict[str, List[Tuple[str, float, int, str]]]:
        """Detect statistical outliers using z-score."""
        citation_counts = [p.get("citationCount", 0) or 0 for p in papers]

        if len(citation_counts) < 3:
            return {"citation_outliers": []}

        mean_cit = statistics.mean(citation_counts)
        stdev_cit = statistics.stdev(citation_counts) if len(citation_counts) > 1 else 1

        outliers = []

        for paper in papers:
            cit_count = paper.get("citationCount", 0) or 0

            if stdev_cit > 0:
                z_score = (cit_count - mean_cit) / stdev_cit

                if abs(z_score) > 3:
                    outliers.append(
                        (
                            paper["paperId"],
                            z_score,
                            cit_count,
                            paper.get("title", "")[:50],
                        )
                    )

        return {"citation_outliers": outliers}

    def _detect_citation_anomalies(
        self, citations: List[Dict[str, Any]], papers: List[Dict[str, Any]]
    ) -> Dict[str, List[str]]:
        """Detect anomalies in citation relationships."""
        self_citations = []
        duplicate_citations = []

        # Check for self-citations
        for cit in citations:
            if cit["fromPaperId"] == cit["toPaperId"]:
                self_citations.append(cit["fromPaperId"])

        # Check for duplicates
        seen = set()
        for cit in citations:
            pair = (cit["fromPaperId"], cit["toPaperId"])
            if pair in seen:
                duplicate_citations.append(f"{pair[0][:20]} -> {pair[1][:20]}")
            seen.add(pair)

        return {
            "self_citations": self_citations,
            "duplicate_citations": duplicate_citations,
        }

    def _detect_disconnected_papers(
        self, papers: List[Dict[str, Any]], citations: List[Dict[str, Any]]
    ) -> Dict[str, List[str]]:
        """Detect papers with no connections in the citation network."""
        # Build connection map
        paper_connections = {p["paperId"]: {"in": 0, "out": 0} for p in papers}

        for cit in citations:
            from_id = cit["fromPaperId"]
            to_id = cit["toPaperId"]

            if from_id in paper_connections:
                paper_connections[from_id]["out"] += 1

            if to_id in paper_connections:
                paper_connections[to_id]["in"] += 1

        # Find disconnected papers
        disconnected = []
        for paper_id, connections in paper_connections.items():
            if connections["in"] == 0 and connections["out"] == 0:
                disconnected.append(paper_id)

        return {"disconnected_papers": disconnected}
