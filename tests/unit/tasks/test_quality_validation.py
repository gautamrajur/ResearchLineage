"""Unit tests for src.tasks.quality_validation (QualityValidationTask)."""
import pytest

from src.tasks.quality_validation import QualityValidationTask
from src.utils.errors import DataQualityError


def _paper(pid: str, year: int = 2020, cit: int = 100, venue: str = "NeurIPS"):
    return {
        "paperId": pid,
        "title": f"Paper {pid}",
        "year": year,
        "citationCount": cit,
        "influentialCitationCount": 10,
        "referenceCount": 20,
        "venue": venue,
    }


@pytest.fixture
def task():
    return QualityValidationTask()


@pytest.fixture
def valid_db_data():
    # Diverse enough to pass quality checks: multiple eras, citation ranges, venues
    return {
        "target_paper_id": "t1",
        "papers_table": [
            _paper("t1", 2020, 100, "NeurIPS"),
            _paper("p2", 2019, 200, "ICML"),
            _paper("p3", 2015, 50, "ArXiv"),
            _paper("p4", 2012, 500, "Journal of ML"),
        ],
        "authors_table": [
            {"paper_id": "t1", "author_id": "a1", "author_name": "Alice"},
            {"paper_id": "p2", "author_id": "a2", "author_name": "Bob"},
            {"paper_id": "p3", "author_id": "a3", "author_name": "Carol"},
            {"paper_id": "p4", "author_id": "a4", "author_name": "Dave"},
        ],
        "citations_table": [
            {"fromPaperId": "t1", "toPaperId": "p2"},
            {"fromPaperId": "p2", "toPaperId": "p3"},
            {"fromPaperId": "p3", "toPaperId": "p4"},
        ],
    }


class TestQualityValidationExecute:
    def test_valid_data_passes(self, task, valid_db_data):
        result = task.execute(valid_db_data)

        assert result["quality_report"]["quality_score"] >= 0.85
        assert "papers_table" in result

    def test_low_quality_score_raises(self, task, valid_db_data):
        for i in range(10):
            valid_db_data["papers_table"].append({"paperId": f"bad{i}"})

        with pytest.raises(DataQualityError, match="Quality validation failed"):
            task.execute(valid_db_data)


class TestQualityValidationSchema:
    def test_missing_paper_fields_fail(self, task, valid_db_data):
        valid_db_data["papers_table"].append({"paperId": "bad"})

        result = task._validate_schema(
            valid_db_data["papers_table"],
            valid_db_data["authors_table"],
            valid_db_data["citations_table"],
        )

        assert len(result["failed"]) > 0


class TestQualityValidationBiasDetection:
    def test_temporal_bias_over_representation(self, task):
        papers = [_paper(f"p{i}", 2022) for i in range(10)]

        result = task._detect_bias_via_slicing(papers)

        assert any("over-represented" in f.lower() for f in result["failed"])

    def test_citation_bias_only_high_cited(self, task):
        papers = [_paper(f"p{i}", 2020, cit=10000) for i in range(10)]

        result = task._detect_bias_via_slicing(papers)

        assert "citation_bias" in result["bias_report"]

    def test_venue_diversity_check(self, task):
        papers = [_paper(f"p{i}", venue="ArXiv") for i in range(10)]

        result = task._detect_bias_via_slicing(papers)

        assert "venue_bias" in result["bias_report"]


class TestQualityValidationReferentialIntegrity:
    """Referential integrity: authors and citations must reference existing papers."""

    def test_referential_integrity_author_orphan_fails(self, task, valid_db_data):
        valid_db_data["authors_table"].append({
            "paper_id": "nonexistent",
            "author_id": "a99",
            "author_name": "Orphan Author",
        })
        result = task._validate_referential_integrity(
            valid_db_data["papers_table"],
            valid_db_data["authors_table"],
            valid_db_data["citations_table"],
        )
        assert len(result["failed"]) > 0
        assert any("non-existent" in f.lower() and "nonexistent" in f for f in result["failed"])

    def test_referential_integrity_citation_from_invalid_paper_fails(self, task, valid_db_data):
        valid_db_data["citations_table"].append({
            "fromPaperId": "nonexistent_from",
            "toPaperId": "t1",
        })
        result = task._validate_referential_integrity(
            valid_db_data["papers_table"],
            valid_db_data["authors_table"],
            valid_db_data["citations_table"],
        )
        assert len(result["failed"]) > 0
        assert any("from" in f.lower() and "non-existent" in f.lower() for f in result["failed"])

    def test_referential_integrity_citation_to_invalid_paper_fails(self, task, valid_db_data):
        valid_db_data["citations_table"].append({
            "fromPaperId": "t1",
            "toPaperId": "nonexistent_to",
        })
        result = task._validate_referential_integrity(
            valid_db_data["papers_table"],
            valid_db_data["authors_table"],
            valid_db_data["citations_table"],
        )
        assert len(result["failed"]) > 0
        assert any("to" in f.lower() and "non-existent" in f.lower() for f in result["failed"])

    def test_referential_integrity_valid_data_passes(self, task, valid_db_data):
        result = task._validate_referential_integrity(
            valid_db_data["papers_table"],
            valid_db_data["authors_table"],
            valid_db_data["citations_table"],
        )
        assert len(result["failed"]) == 0
        assert len(result["passed"]) > 0
