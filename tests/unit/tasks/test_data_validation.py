"""Unit tests for src.tasks.data_validation (DataValidationTask)."""
import pytest

from src.tasks.data_validation import DataValidationTask
from src.utils.errors import ValidationError


def _valid_paper(paper_id: str = "p1", title: str = "Test"):
    return {
        "paperId": paper_id,
        "title": title,
        "year": 2020,
        "citationCount": 0,
    }


def _valid_ref(from_id: str = "p1", to_id: str = "p2"):
    return {"fromPaperId": from_id, "toPaperId": to_id, "isInfluential": False, "contexts": [], "intents": []}


def _valid_cit(from_id: str = "p2", to_id: str = "p1"):
    return {"fromPaperId": from_id, "toPaperId": to_id, "isInfluential": False}


@pytest.fixture
def task():
    return DataValidationTask()


@pytest.fixture
def minimal_raw_data():
    return {
        "target_paper_id": "target",
        "papers": [_valid_paper("target", "Target Paper")],
        "references": [_valid_ref("target", "p2")],
        "citations": [_valid_cit("p3", "target")],
    }


class TestDataValidationTaskStructure:
    def test_missing_target_paper_id_raises(self, task, minimal_raw_data):
        del minimal_raw_data["target_paper_id"]
        with pytest.raises(ValidationError, match="Missing required key"):
            task.execute(minimal_raw_data)

    def test_missing_papers_raises(self, task, minimal_raw_data):
        del minimal_raw_data["papers"]
        with pytest.raises(ValidationError, match="Missing required key"):
            task.execute(minimal_raw_data)

    def test_missing_references_raises(self, task, minimal_raw_data):
        del minimal_raw_data["references"]
        with pytest.raises(ValidationError, match="Missing required key"):
            task.execute(minimal_raw_data)

    def test_missing_citations_raises(self, task, minimal_raw_data):
        del minimal_raw_data["citations"]
        with pytest.raises(ValidationError, match="Missing required key"):
            task.execute(minimal_raw_data)


class TestDataValidationTaskPapers:
    def test_valid_papers_pass(self, task, minimal_raw_data):
        out = task.execute(minimal_raw_data)
        assert len(out["papers"]) == 1
        assert out["papers"][0]["paperId"] == "target"
        assert out["validation_report"]["valid_papers"] == 1
        assert out["validation_report"]["paper_errors"] == 0

    def test_missing_paper_id_collected_as_error(self, task, minimal_raw_data):
        for i in range(9):
            minimal_raw_data["papers"].append(_valid_paper(f"p{i}", f"Paper {i}"))
        minimal_raw_data["papers"].append({"title": "No ID", "year": 2020})  # 1 error
        out = task.execute(minimal_raw_data)  # 11 items -> rate 1/11 < 10%
        assert len(out["papers"]) == 10
        assert len(out["errors"]["papers"]) == 1
        assert "paperId" in out["errors"]["papers"][0]["error"].lower() or "Missing" in out["errors"]["papers"][0]["error"]

    def test_missing_title_collected_as_error(self, task, minimal_raw_data):
        for i in range(9):
            minimal_raw_data["papers"].append(_valid_paper(f"p{i}", f"Paper {i}"))
        minimal_raw_data["papers"].append({"paperId": "p9", "year": 2020})
        out = task.execute(minimal_raw_data)
        assert len(out["errors"]["papers"]) == 1

    def test_invalid_year_range_raises_in_validation(self, task, minimal_raw_data):
        for i in range(9):
            minimal_raw_data["papers"].append(_valid_paper(f"p{i}", f"Paper {i}"))
        minimal_raw_data["papers"].append(_valid_paper("p9", "Bad Year") | {"year": 1800})
        out = task.execute(minimal_raw_data)
        assert len(out["errors"]["papers"]) == 1

    def test_negative_citation_count_collected_as_error(self, task, minimal_raw_data):
        for i in range(9):
            minimal_raw_data["papers"].append(_valid_paper(f"p{i}", f"Paper {i}"))
        minimal_raw_data["papers"].append(_valid_paper("p9", "Neg") | {"citationCount": -1})
        out = task.execute(minimal_raw_data)
        assert len(out["errors"]["papers"]) == 1


class TestDataValidationTaskReferencesAndCitations:
    def test_self_citation_collected_as_error(self, task, minimal_raw_data):
        for i in range(9):
            minimal_raw_data["references"].append(_valid_ref("target", f"p{i}"))
        minimal_raw_data["references"].append(_valid_ref("p1", "p1"))
        out = task.execute(minimal_raw_data)  # 1 error / 12 items < 10%
        assert len(out["errors"]["references"]) == 1
        assert "self" in out["errors"]["references"][0]["error"].lower() or "Self" in out["errors"]["references"][0]["error"]

    def test_missing_from_paper_id_in_ref_collected(self, task, minimal_raw_data):
        for i in range(9):
            minimal_raw_data["references"].append(_valid_ref("target", f"p{i}"))
        minimal_raw_data["references"].append({"toPaperId": "p2"})
        out = task.execute(minimal_raw_data)
        assert len(out["errors"]["references"]) == 1

    def test_valid_refs_and_cits_pass(self, task, minimal_raw_data):
        minimal_raw_data["papers"] = [
            _valid_paper("target", "T"),
            _valid_paper("p2", "P2"),
            _valid_paper("p3", "P3"),
        ]
        out = task.execute(minimal_raw_data)
        assert out["validation_report"]["valid_references"] == 1
        assert out["validation_report"]["valid_citations"] == 1
        assert "target_paper_id" in out
        assert out["target_paper_id"] == "target"


class TestDataValidationTaskErrorRate:
    def test_high_error_rate_raises_validation_error(self, task):
        raw = {
            "target_paper_id": "t",
            "papers": [_valid_paper("p1", "A"), {"paperId": "p2"}],  # p2 missing title
            "references": [],
            "citations": [],
        }
        # 1 error out of 2 papers -> 50% error rate > 10%
        with pytest.raises(ValidationError, match="Too many validation errors"):
            task.execute(raw)

    def test_low_error_rate_succeeds(self, task, minimal_raw_data):
        # Add enough valid papers so 1 error gives rate < 10%: 1 error / 11 items < 0.1
        for i in range(8):
            minimal_raw_data["papers"].append(_valid_paper(f"p{i}", f"Paper {i}"))
        minimal_raw_data["papers"].append({"paperId": "bad2"})  # no title -> 1 error
        out = task.execute(minimal_raw_data)
        assert "papers" in out
        assert out["validation_report"]["total_errors"] == 1
        assert out["validation_report"]["error_rate"] < 0.1
