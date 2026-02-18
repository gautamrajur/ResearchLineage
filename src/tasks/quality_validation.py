"""Quality validation task - Validate data quality before database write."""
from typing import Dict, Any, List
from src.utils.logging import get_logger
from src.utils.errors import DataQualityError

logger = get_logger(__name__)


class QualityValidationTask:
    """Validate data quality using statistical and schema checks."""

    def execute(self, db_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate transformed data quality.

        Args:
            db_data: Output from schema transformation

        Returns:
            Validated data with quality report
        """
        logger.info("Starting quality validation")

        papers = db_data["papers_table"]
        authors = db_data["authors_table"]
        citations = db_data["citations_table"]

        # Run validation checks
        validation_results = {
            "schema_validation": self._validate_schema(papers, authors, citations),
            "statistical_validation": self._validate_statistics(papers, citations),
            "referential_integrity": self._validate_referential_integrity(
                papers, authors, citations
            ),
            "bias_detection": self._detect_bias_via_slicing(papers),
        }

        # Calculate overall quality score
        total_checks = sum(
            len(v["passed"]) + len(v["failed"]) for v in validation_results.values()
        )
        total_passed = sum(len(v["passed"]) for v in validation_results.values())

        quality_score = total_passed / total_checks if total_checks > 0 else 0

        # Check if quality is acceptable
        if quality_score < 0.85:
            failed_checks = []
            for category, results in validation_results.items():
                failed_checks.extend(results["failed"])

            error_msg = f"Quality validation failed: {quality_score:.1%} score. Failed checks: {failed_checks}"
            logger.error(error_msg)
            raise DataQualityError(error_msg)

        logger.info(f"Quality validation passed: {quality_score:.1%} score")

        return {
            "target_paper_id": db_data["target_paper_id"],
            "papers_table": papers,
            "authors_table": authors,
            "citations_table": citations,
            "quality_report": {
                "quality_score": quality_score,
                "total_checks": total_checks,
                "passed_checks": total_passed,
                "failed_checks": total_checks - total_passed,
                "validation_results": validation_results,
            },
        }

    def _validate_schema(
        self,
        papers: List[Dict[str, Any]],
        authors: List[Dict[str, Any]],
        citations: List[Dict[str, Any]],
    ) -> Dict[str, List[str]]:
        """Validate schema compliance."""
        passed = []
        failed = []

        # Papers schema validation
        required_paper_fields = [
            "paperId",
            "title",
            "year",
            "citationCount",
            "influentialCitationCount",
            "referenceCount",
        ]

        for paper in papers:
            for field in required_paper_fields:
                if field not in paper or paper[field] is None:
                    if field != "year":  # year can be None
                        failed.append(
                            f"Paper missing {field}: {paper.get('paperId', 'unknown')}"
                        )
                    break
            else:
                passed.append(f"Paper schema valid: {paper['paperId']}")

        # Authors schema validation
        for author in authors:
            if not author.get("paper_id") or not author.get("author_name"):
                failed.append("Author missing required fields")
            else:
                passed.append("Author schema valid")

        # Citations schema validation
        for cit in citations:
            if not cit.get("fromPaperId") or not cit.get("toPaperId"):
                failed.append("Citation missing required fields")
            else:
                passed.append("Citation schema valid")

        return {"passed": passed, "failed": failed}

    def _validate_statistics(
        self, papers: List[Dict[str, Any]], citations: List[Dict[str, Any]]
    ) -> Dict[str, List[str]]:
        """Validate statistical properties."""
        passed = []
        failed = []

        # Check citation counts are non-negative
        for paper in papers:
            citation_count = paper.get("citationCount", 0)
            if citation_count < 0:
                failed.append(f"Negative citation count: {paper['paperId']}")
            else:
                passed.append(f"Valid citation count: {paper['paperId']}")

        # Check year ranges
        for paper in papers:
            year = paper.get("year")
            if year and (year < 1900 or year > 2030):
                failed.append(f"Invalid year {year}: {paper['paperId']}")
            else:
                passed.append(f"Valid year: {paper['paperId']}")

        # Check for duplicate citations
        citation_pairs = set()
        for cit in citations:
            pair = (cit["fromPaperId"], cit["toPaperId"])
            if pair in citation_pairs:
                failed.append(f"Duplicate citation: {pair}")
            else:
                citation_pairs.add(pair)
                passed.append(f"Unique citation: {pair}")

        return {"passed": passed, "failed": failed}

    def _validate_referential_integrity(
        self,
        papers: List[Dict[str, Any]],
        authors: List[Dict[str, Any]],
        citations: List[Dict[str, Any]],
    ) -> Dict[str, List[str]]:
        """Validate referential integrity."""
        passed = []
        failed = []

        # Get valid paper IDs
        valid_paper_ids = {p["paperId"] for p in papers}

        # Check authors reference valid papers
        for author in authors:
            if author["paper_id"] not in valid_paper_ids:
                failed.append(
                    f"Author references non-existent paper: {author['paper_id']}"
                )
            else:
                passed.append("Author references valid paper")

        # Check citations reference valid papers
        for cit in citations:
            if cit["fromPaperId"] not in valid_paper_ids:
                failed.append(f"Citation from non-existent paper: {cit['fromPaperId']}")
            elif cit["toPaperId"] not in valid_paper_ids:
                failed.append(f"Citation to non-existent paper: {cit['toPaperId']}")
            else:
                passed.append("Citation references valid papers")

        return {"passed": passed, "failed": failed}

    def _detect_bias_via_slicing(self, papers: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Detect bias through data slicing.

        Args:
            papers: List of paper dictionaries

        Returns:
            Bias detection results with slicing analysis
        """
        passed = []
        failed = []
        bias_report = {}

        # 1. Temporal Bias - Year distribution
        year_slices: Dict[str, List[Dict[str, Any]]] = {
            "pre_2000": [],
            "2000_2010": [],
            "2010_2015": [],
            "2015_2020": [],
            "2020_plus": [],
        }

        for paper in papers:
            year = paper.get("year")
            if not year:
                continue

            if year < 2000:
                year_slices["pre_2000"].append(paper)
            elif 2000 <= year < 2010:
                year_slices["2000_2010"].append(paper)
            elif 2010 <= year < 2015:
                year_slices["2010_2015"].append(paper)
            elif 2015 <= year < 2020:
                year_slices["2015_2020"].append(paper)
            else:
                year_slices["2020_plus"].append(paper)

        # Check temporal distribution
        total_papers = len(papers)
        year_distribution = {
            era: len(papers_in_era) / total_papers if total_papers > 0 else 0
            for era, papers_in_era in year_slices.items()
        }

        # Flag if any era is over-represented (>50%) or completely missing
        for era, proportion in year_distribution.items():
            if proportion > 0.5:
                failed.append(
                    f"Temporal bias: {era} over-represented ({proportion:.1%})"
                )
            elif proportion == 0 and era in ["2010_2015", "2015_2020"]:
                # Missing recent papers is concerning for modern lineage
                failed.append(f"Temporal bias: {era} completely missing")
            else:
                passed.append(f"Temporal distribution acceptable for {era}")

        bias_report["temporal_bias"] = {
            "distribution": year_distribution,
            "total_papers": total_papers,
        }

        # 2. Citation Count Bias (Rich-get-richer)
        citation_slices: Dict[str, List[Dict[str, Any]]] = {
            "low_0_100": [],
            "medium_100_1k": [],
            "high_1k_10k": [],
            "very_high_10k_plus": [],
        }

        for paper in papers:
            cit_count = paper.get("citationCount", 0) or 0

            if cit_count < 100:
                citation_slices["low_0_100"].append(paper)
            elif 100 <= cit_count < 1000:
                citation_slices["medium_100_1k"].append(paper)
            elif 1000 <= cit_count < 10000:
                citation_slices["high_1k_10k"].append(paper)
            else:
                citation_slices["very_high_10k_plus"].append(paper)

        citation_distribution = {
            range_name: len(papers_in_range) / total_papers if total_papers > 0 else 0
            for range_name, papers_in_range in citation_slices.items()
        }

        # Flag if only selecting highly-cited papers (>70% in high categories)
        high_citation_proportion = citation_distribution.get(
            "high_1k_10k", 0
        ) + citation_distribution.get("very_high_10k_plus", 0)

        if high_citation_proportion > 0.7:
            failed.append(
                f"Citation bias: {high_citation_proportion:.1%} papers are highly cited "
                "(may miss important recent work)"
            )
        else:
            passed.append("Citation count distribution balanced")

        # Check if we have diversity
        if citation_distribution.get("low_0_100", 0) == 0:
            failed.append(
                "Citation bias: No low-citation papers (missing recent/emerging work)"
            )
        else:
            passed.append("Includes papers across citation ranges")

        bias_report["citation_bias"] = {
            "distribution": citation_distribution,
            "high_citation_proportion": high_citation_proportion,
        }

        # 3. Venue Bias - Conference vs Journal distribution
        venue_slices: Dict[str, List[Dict[str, Any]]] = {
            "top_conference": [],
            "journal": [],
            "arxiv": [],
            "other": [],
        }

        top_conferences = [
            "NeurIPS",
            "NIPS",
            "ICML",
            "ICLR",
            "ACL",
            "EMNLP",
            "CVPR",
            "ICCV",
            "ECCV",
            "AAAI",
            "IJCAI",
        ]

        for paper in papers:
            venue = paper.get("venue", "").upper()

            if any(conf in venue for conf in top_conferences):
                venue_slices["top_conference"].append(paper)
            elif "ARXIV" in venue or not venue:
                venue_slices["arxiv"].append(paper)
            elif "JOURNAL" in venue or "TRANSACTIONS" in venue:
                venue_slices["journal"].append(paper)
            else:
                venue_slices["other"].append(paper)

        venue_distribution = {
            venue_type: len(papers_in_venue) / total_papers if total_papers > 0 else 0
            for venue_type, papers_in_venue in venue_slices.items()
        }

        # Flag if too concentrated in one venue type
        for venue_type, proportion in venue_distribution.items():
            if proportion > 0.6:
                failed.append(
                    f"Venue bias: {proportion:.1%} from {venue_type} "
                    "(may miss work from other publication types)"
                )

        if len([p for p in venue_distribution.values() if p > 0]) < 2:
            failed.append("Venue bias: Papers from only one venue type")
        else:
            passed.append("Venue diversity acceptable")

        bias_report["venue_bias"] = {"distribution": venue_distribution}

        return {"passed": passed, "failed": failed, "bias_report": bias_report}
