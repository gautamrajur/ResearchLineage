"""Test feature engineering task."""
import asyncio
import logging
from src.tasks.data_acquisition import DataAcquisitionTask
from src.tasks.data_validation import DataValidationTask
from src.tasks.data_cleaning import DataCleaningTask
from src.tasks.citation_graph_construction import CitationGraphConstructionTask
from src.tasks.feature_engineering import FeatureEngineeringTask

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


async def test():
    print("\nTesting Feature Engineering")
    print("=" * 60)

    paper_id = "204e3073870fae3d05bcbc2f6a8e263d9b72e776"

    # Run pipeline through Task 4
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

    # Task 5: Feature Engineering
    print("\n[5/10] Feature Engineering...")
    feature_task = FeatureEngineeringTask()
    enriched_data = feature_task.execute(graph_data)

    # Show sample paper with features
    print("\nSample papers with features:")
    for i, paper in enumerate(enriched_data["papers"][:3], 1):
        print(f"\n{i}. {paper['title'][:60]}")
        print(f"   Year: {paper.get('year')}")
        print(f"   Citations: {paper.get('citationCount', 0)}")
        print(
            f"   Citation Velocity: {paper.get('citation_velocity', 0):.2f} cites/year"
        )
        print(f"   Recency Score: {paper.get('recency_score', 0):.3f}")
        print(f"   Temporal Category: {paper.get('temporal_category', 'N/A')}")
        print(f"   Years from Target: {paper.get('years_from_target', 0)}")
        print(f"   Influence Score: {paper.get('influence_score_normalized', 0):.3f}")
        print(f"   PageRank: {paper.get('pagerank', 0):.6f}")

    print("\nFeature Engineering Test Complete!")


if __name__ == "__main__":
    asyncio.run(test())
