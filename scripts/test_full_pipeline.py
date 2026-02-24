"""Test full pipeline: Acquisition -> Validation -> Cleaning -> Graph Construction."""
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

import asyncio
import logging
from src.tasks.data_acquisition import DataAcquisitionTask
from src.tasks.data_validation import DataValidationTask
from src.tasks.data_cleaning import DataCleaningTask
from src.tasks.citation_graph_construction import CitationGraphConstructionTask

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


async def test_full_pipeline():
    print("\n" + "=" * 60)
    print("FULL PIPELINE TEST - BIDIRECTIONAL (depth=1)")
    print("=" * 60)

    paper_id = "204e3073870fae3d05bcbc2f6a8e263d9b72e776"

    # Task 1: Data Acquisition
    print("\n[1/4] Data Acquisition (both directions)...")
    acquisition = DataAcquisitionTask()
    raw_data = await acquisition.execute(
        paper_id=paper_id, max_depth=1, direction="both"
    )
    await acquisition.close()
    print(f"  Papers: {raw_data['total_papers']}")
    print(f"  References: {raw_data['total_references']}")
    print(f"  Citations: {raw_data['total_citations']}")

    # Task 2: Data Validation
    print("\n[2/4] Data Validation...")
    validation = DataValidationTask()
    validated_data = validation.execute(raw_data)
    print(f"  Valid Papers: {validated_data['validation_report']['valid_papers']}")
    print(
        f"  Valid References: {validated_data['validation_report']['valid_references']}"
    )
    print(
        f"  Valid Citations: {validated_data['validation_report']['valid_citations']}"
    )
    print(f"  Error Rate: {validated_data['validation_report']['error_rate']:.2%}")

    # Task 3: Data Cleaning
    print("\n[3/4] Data Cleaning...")
    cleaning = DataCleaningTask()
    cleaned_data = cleaning.execute(validated_data)
    print(f"  Cleaned Papers: {cleaned_data['cleaning_stats']['cleaned_papers']}")
    print(
        f"  Cleaned References: {cleaned_data['cleaning_stats']['cleaned_references']}"
    )
    print(f"  Cleaned Citations: {cleaned_data['cleaning_stats']['cleaned_citations']}")

    # Task 4: Citation Graph Construction
    print("\n[4/4] Citation Graph Construction...")
    graph_task = CitationGraphConstructionTask()
    graph_data = graph_task.execute(cleaned_data)
    G = graph_data["graph"]
    print(f"  Graph Nodes: {G.number_of_nodes()}")
    print(f"  Graph Edges: {G.number_of_edges()}")
    print(f"  Graph Density: {graph_data['graph_stats']['density']:.4f}")

    # Analyze target paper in graph
    metrics = graph_data["metrics"]
    target_metrics = metrics.get(paper_id, {})
    print("\n  Target Paper Metrics:")
    print(f"    In-degree (papers citing it): {target_metrics.get('in_degree', 0)}")
    print(f"    Out-degree (papers it cites): {target_metrics.get('out_degree', 0)}")
    print(f"    PageRank: {target_metrics.get('pagerank', 0):.6f}")

    # Top papers by different metrics
    print("\n  Top 5 Papers by Citation Count:")
    sorted_by_citations = sorted(
        G.nodes(data=True), key=lambda x: x[1].get("citationCount", 0), reverse=True
    )[:5]

    for i, (node_id, node_data) in enumerate(sorted_by_citations, 1):
        print(f"    {i}. {node_data['title'][:55]}")
        print(
            f"       Citations: {node_data['citationCount']}, Year: {node_data['year']}"
        )

    print("\n" + "=" * 60)
    print("PIPELINE TEST COMPLETED SUCCESSFULLY")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_full_pipeline())
