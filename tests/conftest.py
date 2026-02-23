"""Top-level shared data factory helpers used across unit and integration tests."""


def make_paper(
    paper_id="p1",
    title="Test Paper",
    year=2020,
    citation_count=500,
    abstract="Test abstract.",
    venue="NeurIPS",
    authors=None,
    arxiv_id="1234.5678",
):
    return {
        "paperId": paper_id,
        "title": title,
        "year": year,
        "citationCount": citation_count,
        "influentialCitationCount": 50,
        "referenceCount": 20,
        "abstract": abstract,
        "venue": venue,
        "authors": authors or [{"authorId": "a1", "name": "Alice Smith"}],
        "externalIds": {"ArXiv": arxiv_id},
        "url": f"https://example.com/{paper_id}",
    }


def make_ref(from_id="p1", to_id="p2", intents=None, is_influential=True):
    return {
        "fromPaperId": from_id,
        "toPaperId": to_id,
        "isInfluential": is_influential,
        "contexts": ["We build upon this work."],
        "intents": intents or ["methodology"],
        "direction": "backward",
    }


def make_cit(from_id="p3", to_id="p1", intents=None):
    return {
        "fromPaperId": from_id,
        "toPaperId": to_id,
        "isInfluential": False,
        "contexts": [],
        "intents": intents or ["methodology"],
        "direction": "forward",
    }
