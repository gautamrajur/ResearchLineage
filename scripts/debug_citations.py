"""Debug citation fetching."""
import asyncio
import logging
from src.tasks.data_acquisition import DataAcquisitionTask

logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


async def debug():
    task = DataAcquisitionTask()
    paper_id = "204e3073870fae3d05bcbc2f6a8e263d9b72e776"

    # Get paper data first
    paper_data = await task.api_client.get_paper(paper_id)
    print(f"\nPaper: {paper_data['title']}")
    print(f"DOI: {task.id_mapper.extract_doi(paper_data)}")

    # Test Semantic Scholar citations directly
    print("\n--- Testing Semantic Scholar ---")
    ss_citations = await task.api_client.get_citations(paper_id, limit=15)
    print(f"Semantic Scholar citations: {len(ss_citations)}")

    # Test fallback method
    print("\n--- Testing Fallback Method ---")
    fallback_citations = await task._fetch_citations_with_fallback(
        paper_id, paper_data, limit=15
    )
    print(f"Fallback citations: {len(fallback_citations)}")

    if fallback_citations:
        print("\nSample citations:")
        for i, cit in enumerate(fallback_citations[:3], 1):
            print(
                f"{i}. From: {cit.get('fromPaperId')[:20]}... To: {cit.get('toPaperId')[:20]}..."
            )

    await task.close()


if __name__ == "__main__":
    asyncio.run(debug())
