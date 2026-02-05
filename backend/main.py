from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from mock_data import get_paper, get_references, get_citations, search_papers, MOCK_DATA

app = FastAPI(title="Research Lineage Tracker API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def read_root():
    return {"message": "Research Lineage Tracker API"}


@app.get("/api/health")
def health_check():
    return {"status": "healthy"}


@app.get("/api/paper/{paper_id}")
def api_get_paper(paper_id: str):
    """Get paper details by ID."""
    paper = get_paper(paper_id)
    if paper is None:
        raise HTTPException(status_code=404, detail="Paper not found")
    return paper


@app.get("/api/paper/{paper_id}/references")
def api_get_references(paper_id: str, limit: int = Query(default=20, le=50)):
    """Get papers that this paper cites (Pre-Order data)."""
    paper = get_paper(paper_id)
    if paper is None:
        raise HTTPException(status_code=404, detail="Paper not found")
    return get_references(paper_id, limit)


@app.get("/api/paper/{paper_id}/citations")
def api_get_citations(paper_id: str, limit: int = Query(default=20, le=50)):
    """Get papers citing this paper (Post-Order data)."""
    paper = get_paper(paper_id)
    if paper is None:
        raise HTTPException(status_code=404, detail="Paper not found")
    return get_citations(paper_id, limit)


@app.get("/api/search")
def api_search(q: str = Query(..., min_length=1)):
    """Search papers by title."""
    return search_papers(q)


@app.get("/api/seed")
def api_get_seed():
    """Get the seed paper (default starting point)."""
    return MOCK_DATA["seed"]
