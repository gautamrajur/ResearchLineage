"""Debug full pipeline with both directions."""
import asyncio
import logging
from src.tasks.data_acquisition import DataAcquisitionTask

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


async def debug():
    task = DataAcquisitionTask()
    paper_id = "204e3073870fae3d05bcbc2f6a8e263d9b72e776"

    print("\n" + "=" * 60)
    print("Testing BOTH directions with depth=1 (minimize API calls)")
    print("=" * 60)

    result = await task.execute(paper_id=paper_id, max_depth=1, direction="both")

    print("\nResults:")
    print(f"  Papers: {result['total_papers']}")
    print(f"  References: {result['total_references']}")
    print(f"  Citations: {result['total_citations']}")

    print("\nReferences sample (first 3):")
    for i, ref in enumerate(result["references"][:3], 1):
        print(
            f"  {i}. {ref['fromPaperId'][:20]}... -> {ref['toPaperId'][:20]}... (direction: {ref.get('direction')})"
        )

    print("\nCitations sample (first 3):")
    for i, cit in enumerate(result["citations"][:3], 1):
        print(
            f"  {i}. {cit['fromPaperId'][:20]}... -> {cit['toPaperId'][:20]}... (direction: {cit.get('direction')})"
        )

    await task.close()


if __name__ == "__main__":
    asyncio.run(debug())
