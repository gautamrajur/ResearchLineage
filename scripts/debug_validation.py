"""Debug which papers are failing validation."""
import asyncio
from src.tasks.data_acquisition import DataAcquisitionTask
from src.tasks.data_validation import DataValidationTask


async def debug():
    acquisition = DataAcquisitionTask()
    paper_id = "204e3073870fae3d05bcbc2f6a8e263d9b72e776"

    raw = await acquisition.execute(
        paper_id=paper_id, max_depth=1, direction="backward"
    )
    await acquisition.close()

    print(f"\nTotal papers fetched: {len(raw['papers'])}")

    print("\nChecking each paper:")
    for i, paper in enumerate(raw["papers"]):
        has_id = "paperId" in paper and paper["paperId"] is not None
        print(f"{i}. Has paperId: {has_id}")
        if not has_id:
            print(f"   Keys in paper: {list(paper.keys())}")
            print(f"   Title: {paper.get('title', 'N/A')[:50]}")

    print("\n\nNow running validation:")
    validation = DataValidationTask()
    try:
        validated = validation.execute(raw)
        print(
            f"Validation passed: {validated['validation_report']['valid_papers']} valid papers"
        )
    except Exception as e:
        print(f"Validation failed: {e}")


if __name__ == "__main__":
    asyncio.run(debug())
