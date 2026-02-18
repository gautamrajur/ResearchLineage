"""Data validation task - Validate raw API responses."""
from typing import Dict, Any, List
from src.utils.errors import ValidationError
from src.utils.logging import get_logger

logger = get_logger(__name__)


class DataValidationTask:
    """Validate raw paper data from APIs."""

    def execute(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate raw data from data acquisition.

        Args:
            raw_data: Dictionary containing papers, references, citations

        Returns:
            Validated data dictionary with validation report

        Raises:
            ValidationError: If critical validation fails
        """
        logger.info("Starting data validation")

        # Validate inputs
        self._validate_structure(raw_data)

        # Validate papers
        valid_papers, paper_errors = self._validate_papers(raw_data["papers"])

        # Validate references
        valid_refs, ref_errors = self._validate_references(raw_data["references"])

        # Validate citations
        valid_cits, cit_errors = self._validate_citations(raw_data["citations"])

        # Create validation report
        total_errors = len(paper_errors) + len(ref_errors) + len(cit_errors)
        validation_report = {
            "total_papers": len(raw_data["papers"]),
            "valid_papers": len(valid_papers),
            "paper_errors": len(paper_errors),
            "total_references": len(raw_data["references"]),
            "valid_references": len(valid_refs),
            "reference_errors": len(ref_errors),
            "total_citations": len(raw_data["citations"]),
            "valid_citations": len(valid_cits),
            "citation_errors": len(cit_errors),
            "total_errors": total_errors,
            "error_rate": total_errors
            / (
                len(raw_data["papers"])
                + len(raw_data["references"])
                + len(raw_data["citations"])
            )
            if (
                len(raw_data["papers"])
                + len(raw_data["references"])
                + len(raw_data["citations"])
            )
            > 0
            else 0,
        }

        # Check if error rate is acceptable
        if validation_report["error_rate"] > 0.1:  # More than 10% errors
            logger.error(
                f"Validation failed: {validation_report['error_rate']:.1%} error rate"
            )
            raise ValidationError(f"Too many validation errors: {total_errors}")

        logger.info(
            f"Validation complete: {len(valid_papers)} papers, "
            f"{len(valid_refs)} references, {len(valid_cits)} citations validated"
        )

        return {
            "target_paper_id": raw_data["target_paper_id"],
            "papers": valid_papers,
            "references": valid_refs,
            "citations": valid_cits,
            "validation_report": validation_report,
            "errors": {
                "papers": paper_errors,
                "references": ref_errors,
                "citations": cit_errors,
            },
        }

    def _validate_structure(self, data: Dict[str, Any]) -> None:
        """Validate overall data structure."""
        required_keys = ["target_paper_id", "papers", "references", "citations"]
        for key in required_keys:
            if key not in data:
                raise ValidationError(f"Missing required key: {key}")

    def _validate_papers(self, papers: List[Dict[str, Any]]) -> tuple:
        """
        Validate paper records.

        Returns:
            Tuple of (valid_papers, errors)
        """
        valid_papers = []
        errors = []

        for i, paper in enumerate(papers):
            try:
                # Required fields
                if not paper.get("paperId"):
                    raise ValidationError("Missing paperId")

                if not paper.get("title"):
                    raise ValidationError("Missing title")

                # Data types
                if paper.get("year") and not isinstance(paper["year"], int):
                    raise ValidationError(f"Invalid year type: {type(paper['year'])}")

                if not isinstance(paper.get("citationCount", 0), int):
                    raise ValidationError("Invalid citationCount type")

                # Value ranges
                year = paper.get("year")
                if year and (year < 1900 or year > 2030):
                    raise ValidationError(f"Invalid year: {year}")

                citation_count = paper.get("citationCount", 0)
                if citation_count < 0:
                    raise ValidationError(f"Negative citationCount: {citation_count}")

                valid_papers.append(paper)

            except ValidationError as e:
                errors.append(
                    {
                        "index": i,
                        "paperId": paper.get("paperId", "unknown"),
                        "error": str(e),
                    }
                )
                logger.warning(f"Paper validation error at index {i}: {e}")

        return valid_papers, errors

    def _validate_references(self, references: List[Dict[str, Any]]) -> tuple:
        """
        Validate reference records.

        Returns:
            Tuple of (valid_references, errors)
        """
        valid_refs = []
        errors = []

        for i, ref in enumerate(references):
            try:
                # Required fields
                if not ref.get("fromPaperId"):
                    raise ValidationError("Missing fromPaperId")

                if not ref.get("toPaperId"):
                    raise ValidationError("Missing toPaperId")

                # No self-citations
                if ref["fromPaperId"] == ref["toPaperId"]:
                    raise ValidationError("Self-citation detected")

                # Data types
                if not isinstance(ref.get("isInfluential", False), bool):
                    raise ValidationError("Invalid isInfluential type")

                if not isinstance(ref.get("contexts", []), list):
                    raise ValidationError("Invalid contexts type")

                if not isinstance(ref.get("intents", []), list):
                    raise ValidationError("Invalid intents type")

                valid_refs.append(ref)

            except ValidationError as e:
                errors.append(
                    {
                        "index": i,
                        "fromPaperId": ref.get("fromPaperId", "unknown"),
                        "toPaperId": ref.get("toPaperId", "unknown"),
                        "error": str(e),
                    }
                )
                logger.warning(f"Reference validation error at index {i}: {e}")

        return valid_refs, errors

    def _validate_citations(self, citations: List[Dict[str, Any]]) -> tuple:
        """
        Validate citation records.

        Returns:
            Tuple of (valid_citations, errors)
        """
        valid_cits = []
        errors = []

        for i, cit in enumerate(citations):
            try:
                # Required fields
                if not cit.get("fromPaperId"):
                    raise ValidationError("Missing fromPaperId")

                if not cit.get("toPaperId"):
                    raise ValidationError("Missing toPaperId")

                # No self-citations
                if cit["fromPaperId"] == cit["toPaperId"]:
                    raise ValidationError("Self-citation detected")

                # Data types
                if not isinstance(cit.get("isInfluential", False), bool):
                    raise ValidationError("Invalid isInfluential type")

                valid_cits.append(cit)

            except ValidationError as e:
                errors.append(
                    {
                        "index": i,
                        "fromPaperId": cit.get("fromPaperId", "unknown"),
                        "toPaperId": cit.get("toPaperId", "unknown"),
                        "error": str(e),
                    }
                )
                logger.warning(f"Citation validation error at index {i}: {e}")

        return valid_cits, errors
