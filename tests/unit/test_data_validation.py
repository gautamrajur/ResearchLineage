"""Unit tests for DataValidationTask."""
import pytest

from src.tasks.data_validation import DataValidationTask
from src.utils.errors import ValidationError
from tests.conftest import make_paper, make_ref, make_cit


@pytest.fixture
def task():
    return DataValidationTask()


def _wrap(papers=None, references=None, citations=None, target_id="p1"):
    return {
        "target_paper_id": target_id,
        "papers": papers or [],
        "references": references or [],
        "citations": citations or [],
    }


def _good_papers(n=20):
    """Return n distinct valid papers — used as padding to keep error rate < 10 %."""
    return [make_paper(paper_id=f"pad{i}") for i in range(n)]


# ─── Structure validation ────────────────────────────────────────────────────

class TestStructureValidation:
    def test_missing_target_paper_id_raises(self, task):
        data = {"papers": [], "references": [], "citations": []}
        with pytest.raises(ValidationError, match="target_paper_id"):
            task.execute(data)

    def test_missing_papers_key_raises(self, task):
        data = {"target_paper_id": "p1", "references": [], "citations": []}
        with pytest.raises(ValidationError, match="papers"):
            task.execute(data)

    def test_missing_references_key_raises(self, task):
        data = {"target_paper_id": "p1", "papers": [make_paper()], "citations": []}
        with pytest.raises(ValidationError, match="references"):
            task.execute(data)


# ─── Paper validation ────────────────────────────────────────────────────────

class TestPaperValidation:
    """
    Each test submits 20 valid padding papers + 1 bad paper so the overall
    error rate stays below the 10 % threshold, allowing us to inspect the
    errors dict rather than catching a ValidationError.
    """

    def test_valid_paper_passes(self, task):
        result = task.execute(_wrap(papers=[make_paper()]))
        assert len(result["papers"]) == 1

    def test_paper_missing_paper_id_is_invalid(self, task):
        bad = make_paper(); bad["paperId"] = ""
        result = task.execute(_wrap(papers=_good_papers() + [bad]))
        assert any(e["paperId"] == "unknown" or e["paperId"] == "" for e in result["errors"]["papers"])

    def test_paper_missing_title_is_invalid(self, task):
        bad = make_paper(); bad["title"] = ""
        result = task.execute(_wrap(papers=_good_papers() + [bad]))
        assert len(result["errors"]["papers"]) >= 1

    def test_invalid_year_type_is_invalid(self, task):
        bad = make_paper(); bad["year"] = "2020"  # should be int
        result = task.execute(_wrap(papers=_good_papers() + [bad]))
        assert len(result["errors"]["papers"]) >= 1

    def test_year_below_1900_is_invalid(self, task):
        bad = make_paper(year=1800)
        result = task.execute(_wrap(papers=_good_papers() + [bad]))
        assert len(result["errors"]["papers"]) >= 1

    def test_year_above_2030_is_invalid(self, task):
        bad = make_paper(year=2099)
        result = task.execute(_wrap(papers=_good_papers() + [bad]))
        assert len(result["errors"]["papers"]) >= 1

    def test_negative_citation_count_is_invalid(self, task):
        bad = make_paper(citation_count=-1)
        result = task.execute(_wrap(papers=_good_papers() + [bad]))
        assert len(result["errors"]["papers"]) >= 1

    def test_none_year_is_allowed(self, task):
        paper = make_paper(); paper["year"] = None
        result = task.execute(_wrap(papers=[paper]))
        assert len(result["papers"]) == 1

    def test_bad_paper_not_in_valid_list(self, task):
        """The bad paper must not appear in the valid papers output."""
        bad = make_paper(paper_id="bad_id"); bad["year"] = 1800
        result = task.execute(_wrap(papers=_good_papers() + [bad]))
        valid_ids = {p["paperId"] for p in result["papers"]}
        assert "bad_id" not in valid_ids


# ─── Reference validation ────────────────────────────────────────────────────

class TestReferenceValidation:
    """
    Pad with 20 good papers so the single bad reference keeps error rate < 10 %.
    """

    def test_valid_reference_passes(self, task):
        result = task.execute(_wrap(papers=[make_paper()], references=[make_ref()]))
        assert len(result["references"]) == 1

    def test_self_citation_in_reference_is_invalid(self, task):
        bad_ref = make_ref(from_id="p1", to_id="p1")
        result = task.execute(_wrap(papers=_good_papers(), references=[bad_ref]))
        assert len(result["references"]) == 0
        assert len(result["errors"]["references"]) == 1

    def test_missing_from_paper_id_is_invalid(self, task):
        bad = make_ref(); bad["fromPaperId"] = ""
        result = task.execute(_wrap(papers=_good_papers(), references=[bad]))
        assert len(result["errors"]["references"]) >= 1

    def test_missing_to_paper_id_is_invalid(self, task):
        bad = make_ref(); bad["toPaperId"] = ""
        result = task.execute(_wrap(papers=_good_papers(), references=[bad]))
        assert len(result["errors"]["references"]) >= 1

    def test_invalid_is_influential_type_is_invalid(self, task):
        bad = make_ref(); bad["isInfluential"] = "yes"  # should be bool
        result = task.execute(_wrap(papers=_good_papers(), references=[bad]))
        assert len(result["errors"]["references"]) >= 1


# ─── Citation validation ─────────────────────────────────────────────────────

class TestCitationValidation:
    def test_valid_citation_passes(self, task):
        result = task.execute(_wrap(papers=[make_paper()], citations=[make_cit()]))
        assert len(result["citations"]) == 1

    def test_self_citation_in_citations_is_invalid(self, task):
        """
        Pad with 20 good papers so the single bad citation keeps error rate
        below the 10 % threshold — allows inspecting errors dict directly.
        """
        bad = make_cit(from_id="p0", to_id="p0")
        result = task.execute(_wrap(papers=_good_papers(), citations=[bad]))
        assert len(result["citations"]) == 0
        assert len(result["errors"]["citations"]) == 1


# ─── Error rate threshold ────────────────────────────────────────────────────

class TestErrorRate:
    def test_high_error_rate_raises_validation_error(self, task):
        """If > 10 % of records are invalid the task should raise."""
        # 9 bad papers + 1 good paper = 90 % error rate
        bad_papers = [{"paperId": "", "title": f"bad{i}"} for i in range(9)]
        good_paper = make_paper()
        with pytest.raises(ValidationError, match="Too many"):
            task.execute(_wrap(papers=bad_papers + [good_paper]))

    def test_acceptable_error_rate_passes(self, task):
        """Single bad paper among 20 good ones (< 10 %) must not raise."""
        good_papers = [make_paper(paper_id=f"p{i}") for i in range(20)]
        bad = make_paper(); bad["paperId"] = ""
        task.execute(_wrap(papers=good_papers + [bad]))  # must not raise

    def test_validation_report_keys_present(self, task):
        result = task.execute(_wrap(papers=[make_paper()]))
        report = result["validation_report"]
        for key in ("total_papers", "valid_papers", "error_rate", "total_errors"):
            assert key in report

    def test_error_rate_zero_for_clean_data(self, task):
        result = task.execute(_wrap(papers=[make_paper()]))
        assert result["validation_report"]["error_rate"] == 0.0
