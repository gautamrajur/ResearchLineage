"""Fixtures for integration tests — full pipeline chain, no external I/O."""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from tests.conftest import make_paper, make_ref, make_cit


@pytest.fixture(scope="module")
def pipeline_seed_data():
    """Realistic multi-paper dataset that drives the full pipeline."""
    papers = [
        make_paper("p1", "Attention Is All You Need", year=2017, citation_count=50000, venue="NeurIPS"),
        make_paper("p2", "BERT Pre-training",          year=2018, citation_count=30000, venue="NAACL"),
        make_paper("p3", "Deep Residual Learning",     year=2016, citation_count=10000, venue="CVPR"),
        make_paper("p4", "Word2Vec",                   year=2013, citation_count=2000,  venue="arXiv"),
        make_paper("p5", "Emerging Technique",         year=2023, citation_count=50,    venue="EMNLP"),
    ]
    return {
        "target_paper_id": "p1",
        "papers": papers,
        "references": [
            make_ref("p1", "p2"),
            make_ref("p2", "p3"),
            make_ref("p3", "p4"),
        ],
        "citations": [make_cit("p5", "p1")],
        "total_papers": len(papers),
        "total_references": 3,
        "total_citations": 1,
        "direction": "both",
    }


@pytest.fixture(scope="module")
def full_pipeline_output(pipeline_seed_data):
    """
    Runs tasks 2–9 in sequence (validation → anomaly detection).
    Task 1 (data_acquisition) is skipped — needs live API.
    Task 10 (database_write) is skipped — needs live DB.
    """
    from src.tasks.data_validation import DataValidationTask
    from src.tasks.data_cleaning import DataCleaningTask
    from src.tasks.citation_graph_construction import CitationGraphConstructionTask
    from src.tasks.feature_engineering import FeatureEngineeringTask
    from src.tasks.schema_transformation import SchemaTransformationTask
    from src.tasks.quality_validation import QualityValidationTask
    from src.tasks.anomaly_detection import AnomalyDetectionTask

    validated   = DataValidationTask().execute(pipeline_seed_data)
    cleaned     = DataCleaningTask().execute(validated)
    graph       = CitationGraphConstructionTask().execute(cleaned)
    enriched    = FeatureEngineeringTask().execute(graph)
    schema      = SchemaTransformationTask().execute(enriched)
    quality     = QualityValidationTask().execute(schema)
    final       = AnomalyDetectionTask().execute(quality)

    return {
        "validated": validated,
        "cleaned": cleaned,
        "graph": graph,
        "enriched": enriched,
        "schema": schema,
        "quality": quality,
        "final": final,
    }
