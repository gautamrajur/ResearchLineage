"""Test bidirectional fetching."""
import asyncio
import logging
from src.tasks.data_acquisition import DataAcquisitionTask

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


async def test_directions():
    paper_id = "204e3073870fae3d05bcbc2f6a8e263d9b72e776"

    print("\n" + "=" * 60)
    print("Testing BACKWARD (references only)")
    print("=" * 60)
    task1 = DataAcquisitionTask()
    backward = await task1.execute(paper_id=paper_id, max_depth=2, direction="backward")
    print(f"Papers: {backward['total_papers']}")
    print(f"References: {backward['total_references']}")
    print(f"Citations: {backward['total_citations']}")
    await task1.close()

    print("\n" + "=" * 60)
    print("Testing FORWARD (citations only)")
    print("=" * 60)
    task2 = DataAcquisitionTask()
    forward = await task2.execute(paper_id=paper_id, max_depth=2, direction="forward")
    print(f"Papers: {forward['total_papers']}")
    print(f"References: {forward['total_references']}")
    print(f"Citations: {forward['total_citations']}")
    await task2.close()

    print("\n" + "=" * 60)
    print("Testing BOTH (references + citations)")
    print("=" * 60)
    task3 = DataAcquisitionTask()
    both = await task3.execute(paper_id=paper_id, max_depth=2, direction="both")
    print(f"Papers: {both['total_papers']}")
    print(f"References: {both['total_references']}")
    print(f"Citations: {both['total_citations']}")
    await task3.close()


if __name__ == "__main__":
    asyncio.run(test_directions())
