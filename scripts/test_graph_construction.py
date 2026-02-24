"""Test script for citation graph construction."""
import asyncio
import logging
from src.tasks.data_acquisition import DataAcquisitionTask
from src.tasks.data_validation import DataValidationTask
from src.tasks.data_cleaning import DataCleaningTask
from src.tasks.citation_graph_construction import CitationGraphConstructionTask

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


async def test_graph_construction():
    """Test citation graph construction pipeline."""
    print("\nTesting citation graph construction")
    print("=" * 60)

    # Pipeline execution
    print("\nStep 1: Acquiring data...")
    acquisition_task = DataAcquisitionTask()
    paper_id = "204e3073870fae3d05bcbc2f6a8e263d9b72e776"
    raw_data = await acquisition_task.execute(paper_id=paper_id, max_depth=2)

    print("\nStep 2: Validating data...")
    validation_task = DataValidationTask()
    validated_data = validation_task.execute(raw_data)

    print("\nStep 3: Cleaning data...")
    cleaning_task = DataCleaningTask()
    cleaned_data = cleaning_task.execute(validated_data)

    print("\nStep 4: Constructing citation graph...")
    graph_task = CitationGraphConstructionTask()
    graph_data = graph_task.execute(cleaned_data)

    print("\nGraph Statistics:")
    stats = graph_data["graph_stats"]
    print(f"  Nodes (papers): {stats['num_nodes']}")
    print(f"  Edges (citations): {stats['num_edges']}")
    print(f"  Graph density: {stats['density']:.4f}")
    print(f"  Directed: {stats['is_directed']}")

    print("\nComponent Analysis:")
    comp = graph_data["components"]
    print(f"  Weakly connected components: {comp['num_weak_components']}")
    print(f"  Largest component size: {comp['largest_component_size']}")

    print("\nTop 5 Papers by PageRank:")
    G = graph_data["graph"]
    metrics = graph_data["metrics"]

    sorted_papers = sorted(
        metrics.items(), key=lambda x: x[1]["pagerank"], reverse=True
    )[:5]

    for i, (paper_id, paper_metrics) in enumerate(sorted_papers, 1):
        node_data = G.nodes[paper_id]
        print(f"  {i}. {node_data['title'][:60]}...")
        print(f"     PageRank: {paper_metrics['pagerank']:.6f}")
        print(f"     Citations (in-degree): {paper_metrics['in_degree']}")
        print(f"     References (out-degree): {paper_metrics['out_degree']}")

    print("\nTest completed successfully!")


if __name__ == "__main__":
    asyncio.run(test_graph_construction())
