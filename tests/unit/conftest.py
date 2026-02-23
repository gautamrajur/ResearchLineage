"""Fixtures for unit tests — one task at a time, no chaining."""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from tests.conftest import make_paper, make_ref, make_cit


# ─── Raw acquisition output (input to DataValidationTask) ───────────────────

@pytest.fixture
def five_papers():
    return [
        make_paper("p1", "Attention Is All You Need", year=2017, citation_count=50000, venue="NeurIPS"),
        make_paper("p2", "BERT Pre-training",          year=2018, citation_count=30000, venue="NAACL"),
        make_paper("p3", "Deep Residual Learning",     year=2016, citation_count=10000, venue="CVPR"),
        make_paper("p4", "Word2Vec",                   year=2013, citation_count=2000,  venue="arXiv"),
        make_paper("p5", "Emerging Technique",         year=2023, citation_count=50,    venue="EMNLP"),
    ]


@pytest.fixture
def raw_acquisition_output(five_papers):
    return {
        "target_paper_id": "p1",
        "papers": five_papers,
        "references": [
            make_ref("p1", "p2"),
            make_ref("p2", "p3"),
            make_ref("p3", "p4"),
        ],
        "citations": [make_cit("p5", "p1")],
        "total_papers": len(five_papers),
        "total_references": 3,
        "total_citations": 1,
        "direction": "both",
    }


# ─── Validated output (input to DataCleaningTask) ───────────────────────────

@pytest.fixture
def validated_output(raw_acquisition_output):
    """Validated data produced by DataValidationTask."""
    from src.tasks.data_validation import DataValidationTask
    return DataValidationTask().execute(raw_acquisition_output)


# ─── Cleaned output (input to CitationGraphConstructionTask) ────────────────

@pytest.fixture
def cleaned_output(validated_output):
    from src.tasks.data_cleaning import DataCleaningTask
    return DataCleaningTask().execute(validated_output)


# ─── Graph output (input to FeatureEngineeringTask) ─────────────────────────

@pytest.fixture
def graph_output(cleaned_output):
    from src.tasks.citation_graph_construction import CitationGraphConstructionTask
    return CitationGraphConstructionTask().execute(cleaned_output)


# ─── Enriched output (input to SchemaTransformationTask) ────────────────────

@pytest.fixture
def enriched_output(graph_output):
    from src.tasks.feature_engineering import FeatureEngineeringTask
    return FeatureEngineeringTask().execute(graph_output)


# ─── Schema output (input to QualityValidationTask) ─────────────────────────

@pytest.fixture
def schema_output(enriched_output):
    from src.tasks.schema_transformation import SchemaTransformationTask
    return SchemaTransformationTask().execute(enriched_output)


# ─── Quality output (input to AnomalyDetectionTask) ─────────────────────────

@pytest.fixture
def quality_output(schema_output):
    from src.tasks.quality_validation import QualityValidationTask
    return QualityValidationTask().execute(schema_output)
