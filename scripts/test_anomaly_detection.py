"""Test anomaly detection."""
import asyncio
import logging
from src.tasks.data_acquisition import DataAcquisitionTask
from src.tasks.data_validation import DataValidationTask
from src.tasks.data_cleaning import DataCleaningTask
from src.tasks.citation_graph_construction import CitationGraphConstructionTask
from src.tasks.feature_engineering import FeatureEngineeringTask
from src.tasks.schema_transformation import SchemaTransformationTask
from src.tasks.quality_validation import QualityValidationTask
from src.tasks.anomaly_detection import AnomalyDetectionTask

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


async def test():
    print("\nTesting Anomaly Detection")
    print("=" * 60)

    paper_id = "204e3073870fae3d05bcbc2f6a8e263d9b72e776"

    # Run pipeline through Task 8
    acquisition = DataAcquisitionTask()
    raw = await acquisition.execute(
        paper_id=paper_id, max_depth=1, direction="backward"
    )
    await acquisition.close()

    validation = DataValidationTask()
    validated = validation.execute(raw)

    cleaning = DataCleaningTask()
    cleaned = cleaning.execute(validated)

    graph_task = CitationGraphConstructionTask()
    graph_data = graph_task.execute(cleaned)

    feature_task = FeatureEngineeringTask()
    enriched = feature_task.execute(graph_data)

    transform_task = SchemaTransformationTask()
    db_data = transform_task.execute(enriched)

    quality_task = QualityValidationTask()
    quality_data = quality_task.execute(db_data)

    # Task 9: Anomaly Detection
    print("\n[9/10] Anomaly Detection...")
    anomaly_task = AnomalyDetectionTask()
    final_data = anomaly_task.execute(quality_data)

    print("\nAnomaly Report:")
    report = final_data["anomaly_report"]
    print(f"  Total Anomalies: {report['total_anomalies']}")

    anomalies = report["anomalies"]

    print("\nMissing Data:")
    print(f"  Missing Abstracts: {len(anomalies['missing_data']['missing_abstracts'])}")
    print(f"  Missing Years: {len(anomalies['missing_data']['missing_years'])}")
    print(f"  Missing Venues: {len(anomalies['missing_data']['missing_venues'])}")

    print("\nOutliers:")
    outliers = anomalies["outliers"]["citation_outliers"]
    print(f"  Citation Count Outliers: {len(outliers)}")
    if outliers:
        for paper_id, z_score, cit_count, title in outliers[:3]:
            print(f"    {title}... (z-score: {z_score:.2f}, citations: {cit_count})")

    print("\nCitation Anomalies:")
    print(f"  Self-citations: {len(anomalies['citation_anomalies']['self_citations'])}")
    print(
        f"  Duplicate Citations: {len(anomalies['citation_anomalies']['duplicate_citations'])}"
    )

    print("\nDisconnected Papers:")
    print(
        f"  Papers with no connections: {len(anomalies['disconnected_papers']['disconnected_papers'])}"
    )

    print("\nAnomaly Detection Test Complete!")


if __name__ == "__main__":
    asyncio.run(test())
