import asyncio
import traceback
from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware

from mock_data import get_paper, get_references, get_citations, search_papers, MOCK_DATA
from tree_view import TreeView
from tree_flatten import flatten_ancestors, flatten_descendants

app = FastAPI(title="Research Lineage Tracker API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory cache for built trees
# Key: paper_id, Value: {"status": "building"|"ready"|"error", "tree": dict|None, "error": str|None}
tree_cache: dict[str, dict] = {}


def _build_tree_sync(paper_id: str):
    """Build tree synchronously (runs in background thread)."""
    try:
        tv = TreeView()
        tree = tv.build_tree(paper_id, max_children=5, max_depth=2, window_years=3)
        if tree is None:
            tree_cache[paper_id] = {
                "status": "error",
                "tree": None,
                "error": "Failed to fetch target paper from Semantic Scholar",
            }
        else:
            tree_cache[paper_id] = {"status": "ready", "tree": tree, "error": None}
    except Exception as e:
        traceback.print_exc()
        tree_cache[paper_id] = {"status": "error", "tree": None, "error": str(e)}


async def _build_tree_background(paper_id: str):
    """Run the blocking tree build in a thread so it doesn't block the event loop."""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _build_tree_sync, paper_id)


@app.get("/")
def read_root():
    return {"message": "Research Lineage Tracker API"}


@app.get("/api/health")
def health_check():
    return {"status": "healthy"}


@app.get("/api/paper/{paper_id}/references")
def api_get_references(paper_id: str, limit: int = Query(default=20, le=50)):
    """Get papers that this paper cites (Pre-Order data).
    Serves flattened live data if tree is ready, otherwise falls back to mock.
    """
    # Try live data first
    cached = tree_cache.get(paper_id)
    if cached and cached["status"] == "ready" and cached["tree"]:
        ancestors = cached["tree"].get("ancestors", [])
        if ancestors:
            flat = flatten_ancestors(ancestors, paper_id)
            return flat[:limit]

    # Fall back to mock
    paper = get_paper(paper_id)
    if paper is None:
        raise HTTPException(status_code=404, detail="Paper not found")
    return get_references(paper_id, limit)


@app.get("/api/paper/{paper_id}/citations")
def api_get_citations(paper_id: str, limit: int = Query(default=20, le=50)):
    """Get papers citing this paper (Post-Order data).
    Serves flattened live data if tree is ready, otherwise falls back to mock.
    """
    # Try live data first
    cached = tree_cache.get(paper_id)
    if cached and cached["status"] == "ready" and cached["tree"]:
        descendants = cached["tree"].get("descendants", [])
        if descendants:
            flat = flatten_descendants(descendants, paper_id)
            return flat[:limit]

    # Fall back to mock
    paper = get_paper(paper_id)
    if paper is None:
        raise HTTPException(status_code=404, detail="Paper not found")
    return get_citations(paper_id, limit)


@app.get("/api/paper/{paper_id}")
def api_get_paper(paper_id: str):
    """Get paper details by ID. Checks live tree cache first, then mock data."""
    # Check tree cache for target paper
    cached = tree_cache.get(paper_id)
    if cached and cached["status"] == "ready" and cached["tree"]:
        target = cached["tree"].get("target")
        if target:
            return target

    paper = get_paper(paper_id)
    if paper is None:
        raise HTTPException(status_code=404, detail="Paper not found")
    return paper


@app.get("/api/search")
def api_search(q: str = Query(..., min_length=1)):
    """Search papers by title."""
    return search_papers(q)


@app.get("/api/seed")
def api_get_seed(paper_id: str | None = Query(default=None)):
    """Get the seed paper. Accepts optional paper_id to look up a specific paper."""
    if paper_id:
        # Check tree cache first
        cached = tree_cache.get(paper_id)
        if cached and cached["status"] == "ready" and cached["tree"]:
            target = cached["tree"].get("target")
            if target:
                return target
        # Fall back to mock
        paper = get_paper(paper_id)
        if paper:
            return paper
    return MOCK_DATA["seed"]


@app.post("/api/tree/{paper_id}")
async def api_trigger_tree_build(paper_id: str):
    """Trigger a background tree build for the given paper.
    Returns immediately with status. Idempotent — won't restart if already building/ready.
    """
    cached = tree_cache.get(paper_id)

    if cached:
        return {"paperId": paper_id, "status": cached["status"]}

    # Start building
    tree_cache[paper_id] = {"status": "building", "tree": None, "error": None}
    asyncio.create_task(_build_tree_background(paper_id))

    return {"paperId": paper_id, "status": "building"}


@app.get("/api/tree/{paper_id}/status")
def api_tree_status(paper_id: str):
    """Poll the build status of a tree."""
    cached = tree_cache.get(paper_id)
    if not cached:
        raise HTTPException(status_code=404, detail="No tree build found for this paper")

    resp = {"paperId": paper_id, "status": cached["status"]}
    if cached["status"] == "error":
        resp["error"] = cached.get("error", "Unknown error")
    return resp
