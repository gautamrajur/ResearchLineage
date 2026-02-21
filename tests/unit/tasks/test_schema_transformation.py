"""Unit tests for src.tasks.schema_transformation (SchemaTransformationTask)."""
import pytest

from src.tasks.schema_transformation import SchemaTransformationTask


@pytest.fixture
def task():
    return SchemaTransformationTask()


@pytest.fixture
def enriched_data():
    return {
        "target_paper_id": "t1",
        "papers": [
            {
                "paperId": "t1",
                "title": "Target Paper",
                "abstract": "This is the abstract.",
                "year": 2020,
                "citationCount": 100,
                "influentialCitationCount": 10,
                "referenceCount": 50,
                "venue": "NeurIPS",
                "url": "https://example.com/paper",
                "externalIds": {"ArXiv": "2001.00001", "DOI": "10.1234/t1"},
                "authors": [
                    {"authorId": "a1", "name": "Alice"},
                    {"authorId": None, "name": "Bob"},
                ],
            }
        ],
        "references": [
            {
                "fromPaperId": "t1",
                "toPaperId": "ref1",
                "isInfluential": True,
                "contexts": ["ctx"],
                "intents": ["methodology"],
            }
        ],
        "citations": [
            {
                "fromPaperId": "cit1",
                "toPaperId": "t1",
                "isInfluential": False,
                "contexts": [],
                "intents": [],
            }
        ],
    }


class TestSchemaTransformationExecute:
    def test_returns_required_keys(self, task, enriched_data):
        result = task.execute(enriched_data)

        assert "papers_table" in result
        assert "authors_table" in result
        assert "citations_table" in result
        assert "transformation_stats" in result

    def test_papers_table_has_db_fields(self, task, enriched_data):
        result = task.execute(enriched_data)
        paper = result["papers_table"][0]

        assert paper["paperId"] == "t1"
        assert paper["arxivId"] == "2001.00001"
        assert paper["title"] == "Target Paper"
        assert "first_queried_at" in paper
        assert paper["query_count"] == 1
        assert paper["text_availability"] == "full_text"

    def test_authors_table_generates_uuid_for_missing_id(self, task, enriched_data):
        result = task.execute(enriched_data)
        authors = result["authors_table"]

        alice = next(a for a in authors if a["author_name"] == "Alice")
        bob = next(a for a in authors if a["author_name"] == "Bob")

        assert alice["author_id"] == "a1"
        assert bob["author_id"] is not None
        assert len(bob["author_id"]) == 36

    def test_citations_table_combines_refs_and_cits(self, task, enriched_data):
        result = task.execute(enriched_data)
        citations = result["citations_table"]

        assert len(citations) == 2

        ref = next(c for c in citations if c["fromPaperId"] == "t1")
        assert ref["direction"] == "backward"
        assert ref["isInfluential"] is True

        cit = next(c for c in citations if c["fromPaperId"] == "cit1")
        assert cit["direction"] == "forward"

    def test_deduplicates_overlapping_refs_and_cits(self, task, enriched_data):
        enriched_data["citations"].append(
            {"fromPaperId": "t1", "toPaperId": "ref1", "isInfluential": False}
        )

        result = task.execute(enriched_data)

        matching = [
            c
            for c in result["citations_table"]
            if c["fromPaperId"] == "t1" and c["toPaperId"] == "ref1"
        ]
        assert len(matching) == 1
