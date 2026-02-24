"""Unit tests for AnomalyDetectionTask."""
import pytest
from datetime import datetime

from src.tasks.anomaly_detection import AnomalyDetectionTask


@pytest.fixture
def task():
    return AnomalyDetectionTask()


def _paper_row(paper_id="p1", citation_count=500, abstract="Some text.", year=2020, venue="NeurIPS"):
    return {
        "paperId": paper_id,
        "title": f"Paper {paper_id}",
        "year": year,
        "citationCount": citation_count,
        "abstract": abstract,
        "venue": venue,
    }


def _cit_row(from_id="p1", to_id="p2"):
    return {
        "fromPaperId": from_id,
        "toPaperId": to_id,
        "isInfluential": False,
        "contexts": [],
        "intents": [],
        "direction": "backward",
        "timestamp": datetime.utcnow(),
    }


def _quality_output(papers=None, authors=None, citations=None):
    """Minimal structure QualityValidationTask would return."""
    p = papers or [_paper_row("p1"), _paper_row("p2")]
    return {
        "target_paper_id": "p1",
        "papers_table": p,
        "authors_table": authors or [],
        "citations_table": citations or [_cit_row("p1", "p2")],
        "quality_report": {"quality_score": 1.0, "total_checks": 10,
                           "passed_checks": 10, "failed_checks": 0,
                           "validation_results": {}},
    }


# ─── Clean data produces no anomalies ────────────────────────────────────────

class TestCleanData:
    def test_no_anomalies_on_valid_data(self, task):
        result = task.execute(_quality_output())
        assert result["anomaly_report"]["total_anomalies"] == 0

    def test_output_keys_present(self, task):
        result = task.execute(_quality_output())
        for key in ("target_paper_id", "papers_table", "authors_table",
                    "citations_table", "quality_report", "anomaly_report"):
            assert key in result

    def test_anomaly_report_structure(self, task):
        result = task.execute(_quality_output())
        report = result["anomaly_report"]
        assert "total_anomalies" in report
        assert "anomalies" in report
        for key in ("missing_data", "outliers", "citation_anomalies", "disconnected_papers"):
            assert key in report["anomalies"]


# ─── Missing data detection ───────────────────────────────────────────────────

class TestMissingData:
    def test_missing_abstract_detected(self, task):
        papers = [_paper_row("p1", abstract=""), _paper_row("p2")]
        result = task.execute(_quality_output(papers=papers))
        missing = result["anomaly_report"]["anomalies"]["missing_data"]["missing_abstracts"]
        assert "p1" in missing

    def test_missing_year_detected(self, task):
        paper = _paper_row("p1")
        paper["year"] = None
        result = task.execute(_quality_output(papers=[paper, _paper_row("p2")]))
        missing = result["anomaly_report"]["anomalies"]["missing_data"]["missing_years"]
        assert "p1" in missing

    def test_missing_venue_detected(self, task):
        paper = _paper_row("p1", venue="")
        result = task.execute(_quality_output(papers=[paper, _paper_row("p2")]))
        missing = result["anomaly_report"]["anomalies"]["missing_data"]["missing_venues"]
        assert "p1" in missing

    def test_complete_paper_has_no_missing_data(self, task):
        result = task.execute(_quality_output(papers=[_paper_row("p1"), _paper_row("p2")]))
        missing = result["anomaly_report"]["anomalies"]["missing_data"]
        assert len(missing["missing_abstracts"]) == 0
        assert len(missing["missing_years"]) == 0
        assert len(missing["missing_venues"]) == 0


# ─── Outlier detection ────────────────────────────────────────────────────────

class TestOutliers:
    def test_extreme_citation_count_flagged_as_outlier(self, task):
        """One paper with 10× the mean citation count → z-score > 3."""
        papers = [_paper_row(f"p{i}", citation_count=100) for i in range(10)]
        papers.append(_paper_row("extreme", citation_count=100_000))
        result = task.execute(_quality_output(papers=papers))
        outliers = result["anomaly_report"]["anomalies"]["outliers"]["citation_outliers"]
        outlier_ids = [o[0] for o in outliers]
        assert "extreme" in outlier_ids

    def test_normal_distribution_no_outliers(self, task):
        """Papers with similar citation counts should not be flagged."""
        papers = [_paper_row(f"p{i}", citation_count=500 + i * 10) for i in range(10)]
        result = task.execute(_quality_output(papers=papers))
        outliers = result["anomaly_report"]["anomalies"]["outliers"]["citation_outliers"]
        assert len(outliers) == 0

    def test_fewer_than_three_papers_skips_outlier_check(self, task):
        """Need at least 3 data points for meaningful z-score."""
        papers = [_paper_row("p1"), _paper_row("p2")]
        result = task.execute(_quality_output(papers=papers))
        outliers = result["anomaly_report"]["anomalies"]["outliers"]["citation_outliers"]
        assert outliers == []


# ─── Citation anomalies ───────────────────────────────────────────────────────

class TestCitationAnomalies:
    def test_self_citation_detected(self, task):
        papers = [_paper_row("p1"), _paper_row("p2")]
        cits = [_cit_row("p1", "p1")]  # self-citation
        result = task.execute(_quality_output(papers=papers, citations=cits))
        self_cits = result["anomaly_report"]["anomalies"]["citation_anomalies"]["self_citations"]
        assert "p1" in self_cits

    def test_duplicate_citation_detected(self, task):
        papers = [_paper_row("p1"), _paper_row("p2")]
        cits = [_cit_row("p1", "p2"), _cit_row("p1", "p2")]
        result = task.execute(_quality_output(papers=papers, citations=cits))
        dups = result["anomaly_report"]["anomalies"]["citation_anomalies"]["duplicate_citations"]
        assert len(dups) > 0

    def test_no_anomalies_in_clean_citations(self, task):
        papers = [_paper_row("p1"), _paper_row("p2")]
        cits = [_cit_row("p1", "p2")]
        result = task.execute(_quality_output(papers=papers, citations=cits))
        anom = result["anomaly_report"]["anomalies"]["citation_anomalies"]
        assert len(anom["self_citations"]) == 0
        assert len(anom["duplicate_citations"]) == 0


# ─── Disconnected papers ──────────────────────────────────────────────────────

class TestDisconnectedPapers:
    def test_isolated_paper_detected(self, task):
        """A paper with no citation connections at all is disconnected."""
        papers = [_paper_row("p1"), _paper_row("p2"), _paper_row("isolated")]
        cits = [_cit_row("p1", "p2")]
        result = task.execute(_quality_output(papers=papers, citations=cits))
        disconnected = result["anomaly_report"]["anomalies"]["disconnected_papers"]["disconnected_papers"]
        assert "isolated" in disconnected

    def test_connected_papers_not_flagged(self, task):
        papers = [_paper_row("p1"), _paper_row("p2")]
        cits = [_cit_row("p1", "p2")]
        result = task.execute(_quality_output(papers=papers, citations=cits))
        disconnected = result["anomaly_report"]["anomalies"]["disconnected_papers"]["disconnected_papers"]
        assert "p1" not in disconnected
        assert "p2" not in disconnected


# ─── Total anomaly count ──────────────────────────────────────────────────────

class TestTotalAnomalyCount:
    def test_total_count_sums_all_categories(self, task):
        papers = [_paper_row("p1", abstract=""), _paper_row("p2", abstract="")]
        cits = [_cit_row("p1", "p2")]
        result = task.execute(_quality_output(papers=papers, citations=cits))
        total = result["anomaly_report"]["total_anomalies"]
        # 2 missing abstracts should be counted
        assert total >= 2
