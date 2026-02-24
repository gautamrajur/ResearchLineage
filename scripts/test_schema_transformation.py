"""Test schema transformation."""
import asyncio
import logging
from src.tasks.data_acquisition import DataAcquisitionTask
from src.tasks.data_validation import DataValidationTask
from src.tasks.data_cleaning import DataCleaningTask
from src.tasks.citation_graph_construction import CitationGraphConstructionTask
from src.tasks.feature_engineering import FeatureEngineeringTask
from src.tasks.schema_transformation import SchemaTransformationTask

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


async def test():
    print("\nTesting Schema Transformation")
    print("=" * 60)

    paper_id = "204e3073870fae3d05bcbc2f6a8e263d9b72e776"

    # Run pipeline
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

    # Task 7: Schema Transformation
    print("\n[7/10] Schema Transformation...")
    transform_task = SchemaTransformationTask()
    db_data = transform_task.execute(enriched)

    print("\nTransformation Results:")
    stats = db_data["transformation_stats"]
    print(f"  Papers: {stats['papers_transformed']}")
    print(f"  Authors: {stats['authors_transformed']}")
    print(f"  Citations: {stats['citations_transformed']}")

    print("\nSample paper record:")
    if db_data["papers_table"]:
        paper = db_data["papers_table"][0]
        print(f"  paperId: {paper['paperId']}")
        print(f"  title: {paper['title'][:60]}")
        print(f"  year: {paper['year']}")
        print(f"  citationCount: {paper['citationCount']}")
        print(f"  text_availability: {paper['text_availability']}")

    print("\nSample author record:")
    if db_data["authors_table"]:
        author = db_data["authors_table"][0]
        print(f"  paper_id: {author['paper_id'][:20]}...")
        print(f"  author_name: {author['author_name']}")

    print("\nSample citation record:")
    if db_data["citations_table"]:
        cit = db_data["citations_table"][0]
        print(f"  from: {cit['fromPaperId'][:20]}...")
        print(f"  to: {cit['toPaperId'][:20]}...")
        print(f"  direction: {cit['direction']}")
        print(f"  isInfluential: {cit['isInfluential']}")

    print("\nSchema Transformation Test Complete!")


if __name__ == "__main__":
    asyncio.run(test())
