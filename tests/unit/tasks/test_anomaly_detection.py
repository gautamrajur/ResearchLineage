"""Unit tests for src.tasks.anomaly_detection (AnomalyDetectionTask)."""
import pytest

from src.tasks.anomaly_detection import AnomalyDetectionTask


def _paper(
    pid: str,
    abstract: str = "Abstract",
    year: int = 2020,
    venue: str = "NeurIPS",
    cit: int = 100,
):
    return {
        "paperId": pid,
        "title": f"Paper {pid}",
        "abstract": abstract,
        "year": year,
        "venue": venue,
        "citationCount": cit,
    }


@pytest.fixture
def task():
    return AnomalyDetectionTask()


@pytest.fixture
def quality_validated_data():
    return {
        "target_paper_id": "t1",
        "papers_table": [
            _paper("t1"),
            _paper("p2"),
            _paper("p3"),
        ],
        "authors_table": [],
        "citations_table": [
            {"fromPaperId": "t1", "toPaperId": "p2"},
            {"fromPaperId": "p2", "toPaperId": "p3"},
        ],
        "quality_report": {"quality_score": 0.95},
    }


class TestAnomalyDetectionExecute:
    def test_returns_anomaly_report(self, task, quality_validated_data):
        result = task.execute(quality_validated_data)

        assert "anomaly_report" in result
        assert "total_anomalies" in result["anomaly_report"]

    def test_passes_through_quality_report(self, task, quality_validated_data):
        result = task.execute(quality_validated_data)

        assert result["quality_report"]["quality_score"] == 0.95


class TestAnomalyDetectionMissingData:
    def test_detects_missing_abstracts(self, task, quality_validated_data):
        quality_validated_data["papers_table"][0]["abstract"] = None

        result = task.execute(quality_validated_data)

        missing = result["anomaly_report"]["anomalies"]["missing_data"]
        assert "t1" in missing["missing_abstracts"]

    def test_detects_missing_years(self, task, quality_validated_data):
        quality_validated_data["papers_table"][1]["year"] = None

        result = task.execute(quality_validated_data)

        missing = result["anomaly_report"]["anomalies"]["missing_data"]
        assert "p2" in missing["missing_years"]


class TestAnomalyDetectionOutliers:
    def test_detects_citation_outliers(self, task, quality_validated_data):
        # Many papers at ~100 so one at 100000 has z-score > 3 (stdev computed over all)
        for i in range(20):
            quality_validated_data["papers_table"].append(_paper(f"norm{i}", cit=100))
        quality_validated_data["papers_table"].append(_paper("outlier", cit=100000))

        result = task.execute(quality_validated_data)

        outliers = result["anomaly_report"]["anomalies"]["outliers"]["citation_outliers"]
        outlier_ids = [o[0] for o in outliers]
        assert "outlier" in outlier_ids

    def test_no_outliers_with_uniform_data(self, task, quality_validated_data):
        for p in quality_validated_data["papers_table"]:
            p["citationCount"] = 100

        result = task.execute(quality_validated_data)

        outliers = result["anomaly_report"]["anomalies"]["outliers"]["citation_outliers"]
        assert len(outliers) == 0


class TestAnomalyDetectionCitations:
    def test_detects_self_citations(self, task, quality_validated_data):
        quality_validated_data["citations_table"].append(
            {"fromPaperId": "t1", "toPaperId": "t1"}
        )

        result = task.execute(quality_validated_data)

        self_cits = result["anomaly_report"]["anomalies"]["citation_anomalies"][
            "self_citations"
        ]
        assert "t1" in self_cits

    def test_detects_duplicate_citations(self, task, quality_validated_data):
        quality_validated_data["citations_table"].append(
            {"fromPaperId": "t1", "toPaperId": "p2"}
        )

        result = task.execute(quality_validated_data)

        dups = result["anomaly_report"]["anomalies"]["citation_anomalies"][
            "duplicate_citations"
        ]
        assert len(dups) > 0


class TestAnomalyDetectionDisconnected:
    def test_detects_disconnected_papers(self, task, quality_validated_data):
        quality_validated_data["citations_table"] = [
            {"fromPaperId": "t1", "toPaperId": "p2"},
        ]

        result = task.execute(quality_validated_data)

        disconnected = result["anomaly_report"]["anomalies"]["disconnected_papers"][
            "disconnected_papers"
        ]
        assert "p3" in disconnected
