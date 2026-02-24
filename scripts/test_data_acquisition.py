"""Test script for data acquisition task."""
import asyncio
import logging
from src.tasks.data_acquisition import DataAcquisitionTask

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


async def test_acquisition():
    """Test data acquisition with a sample paper."""
    task = DataAcquisitionTask()

    # Test with the Construction of Literature Graph paper
    paper_id = "204e3073870fae3d05bcbc2f6a8e263d9b72e776"

    print(f"\nTesting data acquisition for paper: {paper_id}")
    print("=" * 60)

    try:
        result = await task.execute(paper_id=paper_id, max_depth=2)

        print("\nResults:")
        print(f"  Target Paper ID: {result['target_paper_id']}")
        print(f"  Total Papers: {result['total_papers']}")
        print(f"  Total References: {result['total_references']}")
        print(f"  Total Citations: {result['total_citations']}")

        # Show sample paper
        if result["papers"]:
            sample = result["papers"][0]
            print("\nSample Paper:")
            print(f"  Title: {sample.get('title', 'N/A')}")
            print(f"  Year: {sample.get('year', 'N/A')}")
            print(f"  Citations: {sample.get('citationCount', 0)}")

        print("\nTest completed successfully!")

    except Exception as e:
        print(f"\nTest failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(test_acquisition())
