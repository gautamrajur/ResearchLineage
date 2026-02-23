"""Unit tests for QualityValidationTask."""
import pytest
from datetime import datetime

from src.tasks.quality_validation import QualityValidationTask
from src.utils.errors import DataQualityError


@pytest.fixture
def task():
    return QualityValidationTask()


# ─── Row builders ────────────────────────────────────────────────────────────

def _paper_row(paper_id="p1", year=2020, citation_count=100, venue="NeurIPS", title="Test"):
    return {
        "paperId": paper_id,
        "title": title,
        "year": year,
        "citationCount": citation_count,
        "influentialCitationCount": 10,
        "referenceCount": 5,
        "abstract": "Abstract text.",
        "venue": venue,
        "arxivId": "",
        "urls": "",
        "first_queried_at": datetime.utcnow(),
        "query_count": 1,
        "text_availability": "full_text",
    }


def _author_row(paper_id="p1", author_id="a1", name="Alice"):
    return {"paper_id": paper_id, "author_id": author_id, "author_name": name}


def _citation_row(from_id="p1", to_id="p2"):
    return {
        "fromPaperId": from_id,
        "toPaperId": to_id,
        "isInfluential": False,
        "contexts": [],
        "intents": [],
        "direction": "backward",
        "timestamp": datetime.utcnow(),
    }


def _diverse_papers():
    """
    Five papers spanning 5 temporal eras and 3 venue types.
    This satisfies every bias/distribution check in QualityValidationTask:
      - No single era > 50 %
      - 2010_2015 and 2015_2020 are present
      - No single venue type > 60 %  (top_conf=60 %, arxiv=20 %, journal=20 %)
      - All three citation ranges represented
    """
    return [
        _paper_row("p1", year=1998, citation_count=5000, venue="NeurIPS"),            # pre_2000   / top_conf / high
        _paper_row("p2", year=2005, citation_count=200,  venue="arXiv"),              # 2000_2010  / arxiv    / medium
        _paper_row("p3", year=2012, citation_count=1500, venue="ICML"),               # 2010_2015  / top_conf / high
        _paper_row("p4", year=2017, citation_count=300,  venue="IEEE Transactions"),  # 2015_2020  / journal  / medium
        _paper_row("p5", year=2022, citation_count=50,   venue="ICLR"),               # 2020_plus  / top_conf / low
    ]


def _db_data(papers=None, authors=None, citations=None):
    """
    Base dataset that passes QualityValidationTask out of the box.
    Individual tests override specific rows to trigger targeted failures.
    """
    p = papers if papers is not None else _diverse_papers()
    paper_ids = [row["paperId"] for row in p]
    a = authors if authors is not None else [
        _author_row(pid, f"a{i}") for i, pid in enumerate(paper_ids)
    ]
    c = citations if citations is not None else [
        _citation_row("p3", "p1"),
        _citation_row("p5", "p3"),
    ]
    return {
        "target_paper_id": paper_ids[0],
        "papers_table": p,
        "authors_table": a,
        "citations_table": c,
        "transformation_stats": {},
    }


# ─── Happy path ──────────────────────────────────────────────────────────────

class TestHappyPath:
    def test_valid_data_passes(self, task):
        result = task.execute(_db_data())
        assert result["quality_report"]["quality_score"] >= 0.85

    def test_output_keys_present(self, task):
        result = task.execute(_db_data())
        for key in ("target_paper_id", "papers_table", "authors_table",
                    "citations_table", "quality_report"):
            assert key in result

    def test_quality_report_structure(self, task):
        result = task.execute(_db_data())
        report = result["quality_report"]
        for key in ("quality_score", "total_checks", "passed_checks",
                    "failed_checks", "validation_results"):
            assert key in report

    def test_quality_score_between_zero_and_one(self, task):
        result = task.execute(_db_data())
        score = result["quality_report"]["quality_score"]
        assert 0.0 <= score <= 1.0


# ─── Schema validation ────────────────────────────────────────────────────────

class TestSchemaValidation:
    def test_paper_missing_citation_count_flagged(self, task):
        """One bad paper among 5 diverse papers → score stays ≥ 85 %, failure recorded."""
        papers = _diverse_papers()
        del papers[0]["citationCount"]        # remove from first paper only
        result = task.execute(_db_data(papers=papers))
        failed = result["quality_report"]["validation_results"]["schema_validation"]["failed"]
        assert any("citationCount" in f for f in failed)

    def test_author_missing_name_flagged(self, task):
        bad_author = {"paper_id": "p1", "author_id": "a99", "author_name": ""}
        result = task.execute(_db_data(authors=_db_data()["authors_table"] + [bad_author]))
        failed = result["quality_report"]["validation_results"]["schema_validation"]["failed"]
        assert any("Author" in f for f in failed)

    def test_citation_missing_to_paper_id_flagged(self, task):
        bad = {"fromPaperId": "p1", "toPaperId": "", "isInfluential": False,
               "contexts": [], "intents": [], "direction": "backward",
               "timestamp": datetime.utcnow()}
        result = task.execute(_db_data(citations=_db_data()["citations_table"] + [bad]))
        failed = result["quality_report"]["validation_results"]["schema_validation"]["failed"]
        assert any("Citation" in f for f in failed)


# ─── Statistical validation ───────────────────────────────────────────────────

class TestStatisticalValidation:
    def test_negative_citation_count_flagged(self, task):
        papers = _diverse_papers()
        papers[0]["citationCount"] = -1
        result = task.execute(_db_data(papers=papers))
        failed = result["quality_report"]["validation_results"]["statistical_validation"]["failed"]
        assert any("Negative" in f for f in failed)

    def test_invalid_year_flagged(self, task):
        papers = _diverse_papers()
        papers[0]["year"] = 1800          # below 1900 threshold
        result = task.execute(_db_data(papers=papers))
        failed = result["quality_report"]["validation_results"]["statistical_validation"]["failed"]
        assert any("1800" in f for f in failed)

    def test_duplicate_citations_flagged(self, task):
        dup_cits = [_citation_row("p3", "p1"), _citation_row("p3", "p1")]
        result = task.execute(_db_data(citations=dup_cits))
        failed = result["quality_report"]["validation_results"]["statistical_validation"]["failed"]
        assert any("Duplicate" in f for f in failed)

    def test_valid_data_has_no_stat_failures(self, task):
        result = task.execute(_db_data())
        failed = result["quality_report"]["validation_results"]["statistical_validation"]["failed"]
        assert len(failed) == 0


# ─── Referential integrity ────────────────────────────────────────────────────

class TestReferentialIntegrity:
    def test_author_referencing_missing_paper_flagged(self, task):
        ghost_author = _author_row("p_ghost", "a99")
        result = task.execute(_db_data(authors=_db_data()["authors_table"] + [ghost_author]))
        failed = result["quality_report"]["validation_results"]["referential_integrity"]["failed"]
        assert any("p_ghost" in f for f in failed)

    def test_citation_from_missing_paper_flagged(self, task):
        ghost_cit = _citation_row("p_ghost", "p1")
        result = task.execute(_db_data(citations=_db_data()["citations_table"] + [ghost_cit]))
        failed = result["quality_report"]["validation_results"]["referential_integrity"]["failed"]
        assert any("p_ghost" in f for f in failed)

    def test_citation_to_missing_paper_flagged(self, task):
        ghost_cit = _citation_row("p1", "p_ghost")
        result = task.execute(_db_data(citations=_db_data()["citations_table"] + [ghost_cit]))
        failed = result["quality_report"]["validation_results"]["referential_integrity"]["failed"]
        assert any("p_ghost" in f for f in failed)

    def test_valid_refs_pass_integrity(self, task):
        result = task.execute(_db_data())
        failed = result["quality_report"]["validation_results"]["referential_integrity"]["failed"]
        assert len(failed) == 0


# ─── Bias detection ───────────────────────────────────────────────────────────

class TestBiasDetection:
    def test_bias_report_keys_present(self, task):
        result = task.execute(_db_data())
        bias = result["quality_report"]["validation_results"]["bias_detection"]
        assert "bias_report" in bias
        for key in ("temporal_bias", "citation_bias", "venue_bias"):
            assert key in bias["bias_report"]

    def test_temporal_overrepresentation_flagged(self, task):
        """9 papers from 2022 + 1 from 1995 → 2020_plus = 90 % → temporal bias."""
        papers = [_paper_row(f"q{i}", year=2022, citation_count=50+i, venue="NeurIPS") for i in range(9)]
        papers += [_paper_row("q9", year=1995, citation_count=5000, venue="ICML")]
        authors = [_author_row(p["paperId"], f"a{i}") for i, p in enumerate(papers)]
        cits = [_citation_row("q0", "q1")]
        result = task.execute(_db_data(papers=papers, authors=authors, citations=cits))
        dist = result["quality_report"]["validation_results"]["bias_detection"]["bias_report"]["temporal_bias"]["distribution"]
        assert dist["2020_plus"] > 0.5

    def test_citation_bias_all_high_citation_flagged(self, task):
        """All papers highly cited → citation bias flagged."""
        papers = [_paper_row(f"q{i}", year=1998+i*5, citation_count=5000+i*1000, venue=v)
                  for i, v in enumerate(["NeurIPS", "arXiv", "ICML", "IEEE Transactions", "ICLR"])]
        authors = [_author_row(p["paperId"], f"a{i}") for i, p in enumerate(papers)]
        cits = [_citation_row("q2", "q0")]
        result = task.execute(_db_data(papers=papers, authors=authors, citations=cits))
        bias = result["quality_report"]["validation_results"]["bias_detection"]["bias_report"]["citation_bias"]
        assert bias["high_citation_proportion"] > 0.7

    def test_diverse_papers_pass_bias_checks(self, task):
        """The default diverse dataset should produce no bias failures."""
        result = task.execute(_db_data())
        bias_failed = result["quality_report"]["validation_results"]["bias_detection"]["failed"]
        assert len(bias_failed) == 0


# ─── Quality threshold ────────────────────────────────────────────────────────

class TestQualityThreshold:
    def test_low_quality_score_raises_data_quality_error(self, task):
        """
        Force quality below 85 % by using papers with all required fields missing.
        With all 5 papers failing schema (and bias also failing), score drops well below 85 %.
        """
        bad_papers = [
            {k: v for k, v in _paper_row(f"b{i}").items()
             if k not in ("citationCount", "influentialCitationCount", "referenceCount")}
            for i in range(5)
        ]
        with pytest.raises(DataQualityError):
            task.execute(_db_data(papers=bad_papers))

    def test_quality_score_calculated_correctly(self, task):
        result = task.execute(_db_data())
        report = result["quality_report"]
        expected = report["passed_checks"] / (report["passed_checks"] + report["failed_checks"])
        assert abs(report["quality_score"] - expected) < 1e-9
