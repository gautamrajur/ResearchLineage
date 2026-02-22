"""Test database write."""
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
from src.tasks.database_write import DatabaseWriteTask

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


async def test():
    print("\nTesting Database Write - FULL PIPELINE")
    print("=" * 60)

    paper_id = "204e3073870fae3d05bcbc2f6a8e263d9b72e776"

    # Run full pipeline
    print("\n[1/10] Data Acquisition...")
    acquisition = DataAcquisitionTask()
    raw = await acquisition.execute(paper_id=paper_id, max_depth=3, direction="both")
    await acquisition.close()
    print(f"  Fetched: {raw['total_papers']} papers")

    print("\n[2/10] Data Validation...")
    validation = DataValidationTask()
    validated = validation.execute(raw)
    print(f"  Validated: {validated['validation_report']['valid_papers']} papers")

    print("\n[3/10] Data Cleaning...")
    cleaning = DataCleaningTask()
    cleaned = cleaning.execute(validated)
    print(f"  Cleaned: {cleaned['cleaning_stats']['cleaned_papers']} papers")

    print("\n[4/10] Graph Construction...")
    graph_task = CitationGraphConstructionTask()
    graph_data = graph_task.execute(cleaned)
    print(
        f"  Graph: {graph_data['graph_stats']['num_nodes']} nodes, {graph_data['graph_stats']['num_edges']} edges"
    )

    print("\n[5/10] Feature Engineering...")
    feature_task = FeatureEngineeringTask()
    enriched = feature_task.execute(graph_data)
    print(f"  Features added to {len(enriched['papers'])} papers")

    print("\n[7/10] Schema Transformation...")
    transform_task = SchemaTransformationTask()
    db_data = transform_task.execute(enriched)
    print(
        f"  Transformed: {db_data['transformation_stats']['papers_transformed']} papers"
    )

    print("\n[8/10] Quality Validation...")
    quality_task = QualityValidationTask()
    quality_data = quality_task.execute(db_data)
    print(f"  Quality Score: {quality_data['quality_report']['quality_score']:.1%}")

    print("\n[9/10] Anomaly Detection...")
    anomaly_task = AnomalyDetectionTask()
    final_data = anomaly_task.execute(quality_data)
    print(f"  Anomalies: {final_data['anomaly_report']['total_anomalies']}")

    print("\n[10/10] Database Write...")
    db_write_task = DatabaseWriteTask()
    result = db_write_task.execute(final_data)

    print("\nWrite Statistics:")
    stats = result["write_stats"]
    print(f"  Papers Written: {stats['papers_written']}")
    print(f"  Authors Written: {stats['authors_written']}")
    print(f"  Citations Written: {stats['citations_written']}")

    print("\n" + "=" * 60)
    print("FULL PIPELINE COMPLETED SUCCESSFULLY!")
    print("Data persisted to PostgreSQL database")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test())
