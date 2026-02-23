"""Unit tests for SchemaTransformationTask."""
import uuid
import pytest

from src.tasks.schema_transformation import SchemaTransformationTask
from tests.conftest import make_paper, make_ref, make_cit


@pytest.fixture
def task():
    return SchemaTransformationTask()


def _enriched(papers=None, references=None, citations=None):
    """Minimal structure FeatureEngineeringTask would return."""
    p = papers or [make_paper("p1")]
    return {
        "target_paper_id": "p1",
        "papers": p,
        "references": references or [],
        "citations": citations or [],
        "metrics": {},
        "graph_stats": {},
        "components": {},
    }


# ─── Papers table ────────────────────────────────────────────────────────────

class TestPapersTable:
    def test_paper_fields_mapped_correctly(self, task):
        paper = make_paper("p1", title="My Paper", year=2021, citation_count=42, venue="ICLR")
        result = task.execute(_enriched(papers=[paper]))
        row = result["papers_table"][0]
        assert row["paperId"] == "p1"
        assert row["title"] == "My Paper"
        assert row["year"] == 2021
        assert row["citationCount"] == 42
        assert row["venue"] == "ICLR"

    def test_arxiv_id_extracted_from_external_ids(self, task):
        paper = make_paper("p1", arxiv_id="9999.0001")
        result = task.execute(_enriched(papers=[paper]))
        assert result["papers_table"][0]["arxivId"] == "9999.0001"

    def test_arxiv_id_empty_when_missing(self, task):
        paper = make_paper("p1")
        paper["externalIds"] = {}
        result = task.execute(_enriched(papers=[paper]))
        assert result["papers_table"][0]["arxivId"] == ""

    def test_text_availability_full_text_when_abstract_present(self, task):
        paper = make_paper(abstract="Some abstract text.")
        result = task.execute(_enriched(papers=[paper]))
        assert result["papers_table"][0]["text_availability"] == "full_text"

    def test_text_availability_abstract_only_when_no_abstract(self, task):
        paper = make_paper(abstract="")
        result = task.execute(_enriched(papers=[paper]))
        assert result["papers_table"][0]["text_availability"] == "abstract_only"

    def test_citation_count_defaults_to_zero(self, task):
        paper = make_paper()
        paper["citationCount"] = None
        result = task.execute(_enriched(papers=[paper]))
        assert result["papers_table"][0]["citationCount"] == 0

    def test_timestamp_fields_present(self, task):
        result = task.execute(_enriched())
        row = result["papers_table"][0]
        assert "first_queried_at" in row
        assert "query_count" in row


# ─── Authors table ───────────────────────────────────────────────────────────

class TestAuthorsTable:
    def test_authors_extracted_per_paper(self, task):
        paper = make_paper("p1", authors=[
            {"authorId": "a1", "name": "Alice"},
            {"authorId": "a2", "name": "Bob"},
        ])
        result = task.execute(_enriched(papers=[paper]))
        assert len(result["authors_table"]) == 2

    def test_author_fields_correct(self, task):
        paper = make_paper("p1", authors=[{"authorId": "a1", "name": "Alice"}])
        result = task.execute(_enriched(papers=[paper]))
        author = result["authors_table"][0]
        assert author["paper_id"] == "p1"
        assert author["author_id"] == "a1"
        assert author["author_name"] == "Alice"

    def test_author_without_id_gets_uuid(self, task):
        paper = make_paper("p1", authors=[{"authorId": None, "name": "Unknown Author"}])
        result = task.execute(_enriched(papers=[paper]))
        author_id = result["authors_table"][0]["author_id"]
        # Must be a valid UUID string
        uuid.UUID(author_id)  # raises if invalid

    def test_multiple_papers_all_authors_collected(self, task):
        p1 = make_paper("p1", authors=[{"authorId": "a1", "name": "Alice"}])
        p2 = make_paper("p2", authors=[{"authorId": "a2", "name": "Bob"}, {"authorId": "a3", "name": "Carol"}])
        result = task.execute(_enriched(papers=[p1, p2]))
        assert len(result["authors_table"]) == 3


# ─── Citations table ─────────────────────────────────────────────────────────

class TestCitationsTable:
    def test_references_added_to_citations_table(self, task):
        papers = [make_paper("p1"), make_paper("p2")]
        refs = [make_ref("p1", "p2")]
        result = task.execute(_enriched(papers=papers, references=refs))
        assert len(result["citations_table"]) == 1

    def test_citations_added_to_citations_table(self, task):
        papers = [make_paper("p1"), make_paper("p3")]
        cits = [make_cit("p3", "p1")]
        result = task.execute(_enriched(papers=papers, citations=cits))
        assert len(result["citations_table"]) == 1

    def test_duplicate_relationship_not_added_twice(self, task):
        """Same from→to pair in both references and citations should appear once."""
        papers = [make_paper("p1"), make_paper("p2")]
        refs = [make_ref("p1", "p2")]
        cits = [make_cit("p1", "p2")]  # same relationship
        result = task.execute(_enriched(papers=papers, references=refs, citations=cits))
        assert len(result["citations_table"]) == 1

    def test_citation_row_fields_present(self, task):
        papers = [make_paper("p1"), make_paper("p2")]
        result = task.execute(_enriched(papers=papers, references=[make_ref("p1", "p2")]))
        row = result["citations_table"][0]
        for field in ("fromPaperId", "toPaperId", "isInfluential", "timestamp", "direction"):
            assert field in row


# ─── Stats ───────────────────────────────────────────────────────────────────

class TestTransformationStats:
    def test_stats_match_table_lengths(self, task):
        papers = [make_paper("p1"), make_paper("p2")]
        refs = [make_ref("p1", "p2")]
        p1 = make_paper("p1", authors=[{"authorId": "a1", "name": "A"}])
        result = task.execute(_enriched(papers=papers, references=refs))
        stats = result["transformation_stats"]
        assert stats["papers_transformed"] == len(result["papers_table"])
        assert stats["citations_transformed"] == len(result["citations_table"])
