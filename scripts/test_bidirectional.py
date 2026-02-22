"""Test bidirectional fetching - BOTH mode only."""
import asyncio
import logging
from src.tasks.data_acquisition import DataAcquisitionTask

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


async def test_directions():
    paper_id = "204e3073870fae3d05bcbc2f6a8e263d9b72e776"

    print("\n" + "=" * 60)
    print("Testing BOTH (references + citations)")
    print("=" * 60)

    task = DataAcquisitionTask()
    both = await task.execute(paper_id=paper_id, max_depth=3, direction="both")

    print("\nResults:")
    print(f"  Papers: {both['total_papers']}")
    print(f"  References (backward): {both['total_references']}")
    print(f"  Citations (forward): {both['total_citations']}")

    await task.close()

    print("\nTest complete!")


if __name__ == "__main__":
    asyncio.run(test_directions())
