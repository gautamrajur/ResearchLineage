"""Test script for data cleaning task."""
import asyncio
import logging
from src.tasks.data_acquisition import DataAcquisitionTask
from src.tasks.data_validation import DataValidationTask
from src.tasks.data_cleaning import DataCleaningTask

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


async def test_cleaning():
    """Test data cleaning pipeline."""
    print("\nTesting data cleaning pipeline")
    print("=" * 60)

    # Step 1: Acquire data
    print("\nStep 1: Acquiring data...")
    acquisition_task = DataAcquisitionTask()
    paper_id = "204e3073870fae3d05bcbc2f6a8e263d9b72e776"
    raw_data = await acquisition_task.execute(paper_id=paper_id, max_depth=2)
    print(f"Acquired: {raw_data['total_papers']} papers")

    # Step 2: Validate data
    print("\nStep 2: Validating data...")
    validation_task = DataValidationTask()
    validated_data = validation_task.execute(raw_data)
    print(f"Validated: {validated_data['validation_report']['valid_papers']} papers")

    # Step 3: Clean data
    print("\nStep 3: Cleaning data...")
    cleaning_task = DataCleaningTask()
    cleaned_data = cleaning_task.execute(validated_data)

    print("\nCleaning Results:")
    stats = cleaned_data["cleaning_stats"]
    print(f"  Original Papers: {stats['original_papers']}")
    print(f"  Cleaned Papers: {stats['cleaned_papers']}")
    print(f"  Duplicates Removed: {stats['duplicates_removed']}")
    print(f"  Original References: {stats['original_references']}")
    print(f"  Cleaned References: {stats['cleaned_references']}")
    print(f"  References Removed: {stats['references_removed']}")
    print(f"  Original Citations: {stats['original_citations']}")
    print(f"  Cleaned Citations: {stats['cleaned_citations']}")
    print(f"  Citations Removed: {stats['citations_removed']}")

    print("\nSample cleaned paper:")
    if cleaned_data["papers"]:
        sample = cleaned_data["papers"][0]
        print(f"  Title: {sample['title']}")
        print(f"  Venue: {sample.get('venue', 'N/A')}")
        if sample.get("authors"):
            print(f"  First Author: {sample['authors'][0]['name']}")

    print("\nTest completed successfully!")


if __name__ == "__main__":
    asyncio.run(test_cleaning())
