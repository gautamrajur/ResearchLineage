"""Debug forward citation fetching with time window."""
import asyncio
import logging
from src.tasks.data_acquisition import DataAcquisitionTask

logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


async def debug():
    task = DataAcquisitionTask()
    paper_id = "204e3073870fae3d05bcbc2f6a8e263d9b72e776"

    # Get paper first
    paper_data = await task.api_client.get_paper(paper_id)
    print(f"\nPaper: {paper_data['title']}")
    print(f"Year: {paper_data.get('year')}")

    # Test regular citations
    print("\n--- Fetching ALL citations (no filter) ---")
    all_cites = await task.api_client.get_citations(paper_id, limit=200)
    print(f"Total citations: {len(all_cites)}")

    if all_cites:
        print("\nSample citations:")
        for i, cit in enumerate(all_cites[:5], 1):
            citing = cit.get("citingPaper", {})
            print(f"{i}. {citing.get('title', 'N/A')[:50]} ({citing.get('year')})")

    # Test time window filtering
    print("\n--- Testing time window filter ---")
    filtered = await task._get_citations_with_time_window(
        paper_id, paper_data, limit=200
    )
    print(f"After time window: {len(filtered)} citations")

    if filtered:
        print("\nFiltered citations:")
        for i, cit in enumerate(filtered[:5], 1):
            citing = cit.get("citingPaper", {})
            print(f"{i}. {citing.get('title', 'N/A')[:50]} ({citing.get('year')})")
    else:
        print("No citations passed time window filter!")
        print(
            f"Window: {paper_data.get('year', 0) + 1} to {paper_data.get('year', 0) + 3}"
        )

    await task.close()


if __name__ == "__main__":
    asyncio.run(debug())
