"""Unit tests for src.tasks.data_cleaning (DataCleaningTask)."""
import pytest

from src.tasks.data_cleaning import DataCleaningTask


def _paper(paper_id: str, title: str = "Test"):
    return {"paperId": paper_id, "title": title, "authors": [], "citationCount": 0}


def _ref(fr: str, to: str):
    return {"fromPaperId": fr, "toPaperId": to}


@pytest.fixture
def task():
    return DataCleaningTask()


@pytest.fixture
def validated_data():
    return {
        "target_paper_id": "t",
        "papers": [_paper("t", "Target"), _paper("p2", "Paper 2")],
        "references": [_ref("t", "p2")],
        "citations": [_ref("p2", "t")],
    }


class TestDataCleaningTaskExecute:
    def test_output_has_required_keys(self, task, validated_data):
        out = task.execute(validated_data)
        assert "target_paper_id" in out
        assert "papers" in out
        assert "references" in out
        assert "citations" in out
        assert "cleaning_stats" in out

    def test_deduplicate_papers_by_paper_id(self, task, validated_data):
        validated_data["papers"].append(_paper("t", "Duplicate of t"))
        out = task.execute(validated_data)
        assert len(out["papers"]) == 2
        paper_ids = [p["paperId"] for p in out["papers"]]
        assert "t" in paper_ids
        assert "p2" in paper_ids

    def test_self_citations_removed_from_references(self, task, validated_data):
        validated_data["references"].extend([_ref("t", "t"), _ref("p2", "p2")])
        out = task.execute(validated_data)
        ref_pairs = [(r["fromPaperId"], r["toPaperId"]) for r in out["references"]]
        assert ("t", "t") not in ref_pairs
        assert ("p2", "p2") not in ref_pairs
        assert ("t", "p2") in ref_pairs

    def test_duplicate_refs_removed(self, task, validated_data):
        validated_data["references"].extend([_ref("t", "p2"), _ref("t", "p2")])
        out = task.execute(validated_data)
        assert len(out["references"]) == 1

    def test_references_filtered_to_valid_paper_ids(self, task, validated_data):
        validated_data["references"].append(_ref("t", "orphan"))
        out = task.execute(validated_data)
        ref_to_ids = {r["toPaperId"] for r in out["references"]}
        assert "orphan" not in ref_to_ids
        assert "p2" in ref_to_ids

    def test_cleaning_stats_populated(self, task, validated_data):
        out = task.execute(validated_data)
        stats = out["cleaning_stats"]
        assert "original_papers" in stats
        assert "cleaned_papers" in stats
        assert "duplicates_removed" in stats
        assert "references_removed" in stats
        assert "citations_removed" in stats


class TestDataCleaningTaskHelpers:
    def test_clean_text_collapses_whitespace(self, task):
        assert task._clean_text("  hello   world  ") == "hello world"

    def test_clean_text_strips_control_chars(self, task):
        out = task._clean_text("hello\x00world")
        assert "\x00" not in out
        assert "hello" in out and "world" in out

    def test_normalize_venue_expands_abbreviations(self, task):
        out = task._normalize_venue("NeurIPS conf proc")
        assert "Conference" in out or "Proceedings" in out

    def test_negative_citation_count_clamped_to_zero(self, task, validated_data):
        validated_data["papers"][0]["citationCount"] = -5
        out = task.execute(validated_data)
        assert out["papers"][0]["citationCount"] == 0
