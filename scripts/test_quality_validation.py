"""Test quality validation."""
import asyncio
import logging
from src.tasks.data_acquisition import DataAcquisitionTask
from src.tasks.data_validation import DataValidationTask
from src.tasks.data_cleaning import DataCleaningTask
from src.tasks.citation_graph_construction import CitationGraphConstructionTask
from src.tasks.feature_engineering import FeatureEngineeringTask
from src.tasks.schema_transformation import SchemaTransformationTask
from src.tasks.quality_validation import QualityValidationTask

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


async def test():
    print("\nTesting Quality Validation")
    print("=" * 60)

    paper_id = "204e3073870fae3d05bcbc2f6a8e263d9b72e776"

    # Run pipeline through Task 7
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

    # Task 8: Quality Validation
    print("\n[8/10] Quality Validation...")
    quality_task = QualityValidationTask()
    validated_db_data = quality_task.execute(db_data)

    print("\nQuality Report:")
    report = validated_db_data["quality_report"]
    print(f"  Quality Score: {report['quality_score']:.1%}")
    print(f"  Total Checks: {report['total_checks']}")
    print(f"  Passed: {report['passed_checks']}")
    print(f"  Failed: {report['failed_checks']}")

    print("\nValidation Details:")
    for category, results in report["validation_results"].items():
        print(f"  {category}:")
        print(f"    Passed: {len(results['passed'])}")
        print(f"    Failed: {len(results['failed'])}")
        if results["failed"]:
            print(f"    Failures: {results['failed'][:3]}")

    print("\nQuality Validation Test Complete!")

    # In test_quality_validation.py, add after the validation details:

    print("\nBias Detection:")
    if "bias_detection" in report["validation_results"]:
        bias = report["validation_results"]["bias_detection"]

        if "bias_report" in bias:
            print("  Temporal Distribution:")
            for era, prop in bias["bias_report"]["temporal_bias"][
                "distribution"
            ].items():
                print(f"    {era}: {prop:.1%}")

            print("  Citation Count Distribution:")
            for range_name, prop in bias["bias_report"]["citation_bias"][
                "distribution"
            ].items():
                print(f"    {range_name}: {prop:.1%}")

            print("  Venue Distribution:")
            for venue, prop in bias["bias_report"]["venue_bias"][
                "distribution"
            ].items():
                print(f"    {venue}: {prop:.1%}")


if __name__ == "__main__":
    asyncio.run(test())
