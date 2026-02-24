"""Test script for data validation task."""
import asyncio
import logging
from src.tasks.data_acquisition import DataAcquisitionTask
from src.tasks.data_validation import DataValidationTask

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


async def test_validation():
    """Test data validation with acquired data."""
    print("\nTesting data validation pipeline")
    print("=" * 60)

    # Step 1: Acquire data
    print("\nStep 1: Acquiring data...")
    acquisition_task = DataAcquisitionTask()
    paper_id = "204e3073870fae3d05bcbc2f6a8e263d9b72e776"  # Attention is All You Need

    raw_data = await acquisition_task.execute(paper_id=paper_id, max_depth=2)
    print(f"Acquired: {raw_data['total_papers']} papers")

    # Step 2: Validate data
    print("\nStep 2: Validating data...")
    validation_task = DataValidationTask()

    try:
        validated_data = validation_task.execute(raw_data)

        print("\nValidation Results:")
        report = validated_data["validation_report"]
        print(f"  Total Papers: {report['total_papers']}")
        print(f"  Valid Papers: {report['valid_papers']}")
        print(f"  Paper Errors: {report['paper_errors']}")
        print(f"  Total References: {report['total_references']}")
        print(f"  Valid References: {report['valid_references']}")
        print(f"  Reference Errors: {report['reference_errors']}")
        print(f"  Total Citations: {report['total_citations']}")
        print(f"  Valid Citations: {report['valid_citations']}")
        print(f"  Citation Errors: {report['citation_errors']}")
        print(f"  Error Rate: {report['error_rate']:.2%}")

        if report["total_errors"] > 0:
            print("\nError Details:")
            if validated_data["errors"]["papers"]:
                print(f"  Paper errors: {len(validated_data['errors']['papers'])}")
            if validated_data["errors"]["references"]:
                print(
                    f"  Reference errors: {len(validated_data['errors']['references'])}"
                )
            if validated_data["errors"]["citations"]:
                print(
                    f"  Citation errors: {len(validated_data['errors']['citations'])}"
                )

        print("\nTest completed successfully!")

    except Exception as e:
        print(f"\nTest failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(test_validation())
