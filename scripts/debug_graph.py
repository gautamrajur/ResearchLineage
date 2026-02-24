"""Debug script to see what papers we have."""
import asyncio
import logging
from src.tasks.data_acquisition import DataAcquisitionTask
from src.tasks.data_validation import DataValidationTask
from src.tasks.data_cleaning import DataCleaningTask
from src.tasks.citation_graph_construction import CitationGraphConstructionTask

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


async def debug_graph():
    paper_id = "204e3073870fae3d05bcbc2f6a8e263d9b72e776"

    acquisition = DataAcquisitionTask()
    raw = await acquisition.execute(paper_id=paper_id, max_depth=2)

    validation = DataValidationTask()
    validated = validation.execute(raw)

    cleaning = DataCleaningTask()
    cleaned = cleaning.execute(validated)

    graph_task = CitationGraphConstructionTask()
    graph_data = graph_task.execute(cleaned)

    G = graph_data["graph"]
    metrics = graph_data["metrics"]

    # Find Attention is All You Need
    target_found = False
    for node in G.nodes():
        if node == paper_id:
            target_found = True
            node_data = G.nodes[node]
            print("\nTarget Paper Found:")
            print(f"  Title: {node_data['title']}")
            print(f"  Year: {node_data['year']}")
            print(f"  In-degree: {metrics[node]['in_degree']}")
            print(f"  Out-degree: {metrics[node]['out_degree']}")
            print(f"  PageRank: {metrics[node]['pagerank']:.6f}")

    if not target_found:
        print("\nWARNING: Target paper NOT in graph!")

    print("\n\nAll papers in graph:")
    for node in G.nodes():
        node_data = G.nodes[node]
        print(f"  - {node_data['title'][:70]} ({node_data['year']})")


if __name__ == "__main__":
    asyncio.run(debug_graph())
