"""Unit tests for DataCleaningTask."""
import pytest

from src.tasks.data_cleaning import DataCleaningTask
from tests.conftest import make_paper, make_ref, make_cit


@pytest.fixture
def task():
    return DataCleaningTask()


def _validated(papers=None, references=None, citations=None):
    """Minimal structure that DataCleaningTask.execute() expects."""
    return {
        "target_paper_id": "p1",
        "papers": papers or [make_paper()],
        "references": references or [],
        "citations": citations or [],
        "validation_report": {},
        "errors": {"papers": [], "references": [], "citations": []},
    }


# ─── Deduplication ───────────────────────────────────────────────────────────

class TestDeduplication:
    def test_duplicate_papers_removed(self, task):
        papers = [make_paper("p1"), make_paper("p1")]  # same ID
        result = task.execute(_validated(papers=papers))
        assert len(result["papers"]) == 1

    def test_unique_papers_kept(self, task):
        papers = [make_paper("p1"), make_paper("p2")]
        result = task.execute(_validated(papers=papers))
        assert len(result["papers"]) == 2

    def test_duplicate_references_removed(self, task):
        papers = [make_paper("p1"), make_paper("p2")]
        refs = [make_ref("p1", "p2"), make_ref("p1", "p2")]
        result = task.execute(_validated(papers=papers, references=refs))
        assert len(result["references"]) == 1

    def test_duplicate_citations_removed(self, task):
        papers = [make_paper("p1"), make_paper("p2")]
        cits = [make_cit("p2", "p1"), make_cit("p2", "p1")]
        result = task.execute(_validated(papers=papers, citations=cits))
        assert len(result["citations"]) == 1


# ─── Self-citation removal ───────────────────────────────────────────────────

class TestSelfCitationRemoval:
    def test_self_citation_in_references_removed(self, task):
        papers = [make_paper("p1")]
        refs = [make_ref("p1", "p1")]
        result = task.execute(_validated(papers=papers, references=refs))
        assert len(result["references"]) == 0

    def test_self_citation_in_citations_removed(self, task):
        papers = [make_paper("p1")]
        cits = [make_cit("p1", "p1")]
        result = task.execute(_validated(papers=papers, citations=cits))
        assert len(result["citations"]) == 0


# ─── Referential integrity filter ────────────────────────────────────────────

class TestReferentialFilter:
    def test_reference_with_missing_paper_filtered(self, task):
        """Reference where one paper isn't in the papers list is removed."""
        papers = [make_paper("p1")]
        refs = [make_ref("p1", "p_unknown")]
        result = task.execute(_validated(papers=papers, references=refs))
        assert len(result["references"]) == 0

    def test_citation_with_missing_paper_filtered(self, task):
        papers = [make_paper("p1")]
        cits = [make_cit("p_unknown", "p1")]
        result = task.execute(_validated(papers=papers, citations=cits))
        assert len(result["citations"]) == 0

    def test_valid_reference_kept(self, task):
        papers = [make_paper("p1"), make_paper("p2")]
        refs = [make_ref("p1", "p2")]
        result = task.execute(_validated(papers=papers, references=refs))
        assert len(result["references"]) == 1


# ─── Text cleaning ───────────────────────────────────────────────────────────

class TestTextCleaning:
    def test_extra_whitespace_removed_from_title(self, task):
        paper = make_paper(title="  Deep   Learning  ")
        result = task.execute(_validated(papers=[paper]))
        assert result["papers"][0]["title"] == "Deep Learning"

    def test_control_chars_removed_from_abstract(self, task):
        paper = make_paper(abstract="Valid\x00Text\x1f")
        result = task.execute(_validated(papers=[paper]))
        assert "\x00" not in result["papers"][0]["abstract"]
        assert "\x1f" not in result["papers"][0]["abstract"]

    def test_venue_abbreviation_expanded(self, task):
        paper = make_paper(venue="int'l conf on ML")
        result = task.execute(_validated(papers=[paper]))
        venue = result["papers"][0]["venue"]
        assert "International" in venue
        assert "Conference" in venue

    def test_author_names_cleaned(self, task):
        paper = make_paper(authors=[{"authorId": "a1", "name": "  John   Doe  "}])
        result = task.execute(_validated(papers=[paper]))
        assert result["papers"][0]["authors"][0]["name"] == "John Doe"


# ─── Negative count correction ───────────────────────────────────────────────

class TestNegativeCounts:
    def test_negative_citation_count_zeroed(self, task):
        paper = make_paper(citation_count=-5)
        result = task.execute(_validated(papers=[paper]))
        assert result["papers"][0]["citationCount"] == 0

    def test_negative_influential_count_zeroed(self, task):
        paper = make_paper()
        paper["influentialCitationCount"] = -3
        result = task.execute(_validated(papers=[paper]))
        assert result["papers"][0]["influentialCitationCount"] == 0


# ─── Cleaning stats ───────────────────────────────────────────────────────────

class TestCleaningStats:
    def test_stats_keys_present(self, task):
        result = task.execute(_validated())
        stats = result["cleaning_stats"]
        for key in (
            "original_papers", "cleaned_papers", "duplicates_removed",
            "original_references", "cleaned_references",
            "original_citations", "cleaned_citations",
        ):
            assert key in stats

    def test_duplicates_removed_count_accurate(self, task):
        papers = [make_paper("p1"), make_paper("p1"), make_paper("p2")]
        result = task.execute(_validated(papers=papers))
        assert result["cleaning_stats"]["duplicates_removed"] == 1
