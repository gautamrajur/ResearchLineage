"""Test OpenAlex API directly."""
import asyncio
from src.api.openalex import OpenAlexClient


async def test_openalex():
    client = OpenAlexClient()

    # Test 1: Search by title
    print("\nTest 1: Searching for 'Attention is All You Need'")
    results = await client.search_by_title("attention is all you need")
    print(f"Found {len(results)} results")

    if results:
        first = results[0]
        print(f"First result: {first.get('display_name')}")
        print(f"OpenAlex ID: {first.get('id')}")
        print(f"DOI: {first.get('doi')}")
        print(f"Citations: {first.get('cited_by_count')}")

        # Test 2: Get citations for this paper
        openalex_id = first.get("id", "").split("/")[-1]
        print(f"\nTest 2: Getting citations for {openalex_id}")
        citations = await client.get_citations(openalex_id, limit=10)
        print(f"Found {len(citations)} citing papers")

        if citations:
            print("\nSample citing papers:")
            for i, cit in enumerate(citations[:3], 1):
                print(f"{i}. {cit.get('display_name', 'N/A')[:60]}")
                print(f"   Year: {cit.get('publication_year')}")

    await client.close()


if __name__ == "__main__":
    asyncio.run(test_openalex())
