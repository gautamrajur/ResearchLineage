"""
backend/api.py
--------------
FastAPI wrapper around the orchestrator.

Endpoints:
    GET  /health
    GET  /search             — search papers by title via Semantic Scholar
    POST /analyze            — run both views, return tree + timeline JSON
    GET  /analyze/{paper_id} — same but via GET with query params

Usage:
    uvicorn src.backend.api:app --reload --port 8000
"""

import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

from .orchestrator import run
from .common.config import MAX_DEPTH, DATABASE_URL
from .common.cache import Cache
from .common.s2_client import SemanticScholarClient


@asynccontextmanager
async def lifespan(app: FastAPI):
    Cache(DATABASE_URL)  # run DDL once at startup
    yield


app = FastAPI(title="ResearchLineage API", version="1.0.0", lifespan=lifespan)

# CORS — allow Vercel frontend and local dev
_allowed_origins = os.getenv(
    "CORS_ALLOWED_ORIGINS", "http://localhost:3000"
).split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class AnalyzeRequest(BaseModel):
    paper_id: str
    max_children: int = 5
    max_depth_tree: int = 2
    window_years: int = 3
    max_depth_evolution: int = MAX_DEPTH


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/analyze")
def analyze_post(req: AnalyzeRequest):
    return _run(
        req.paper_id,
        req.max_children,
        req.max_depth_tree,
        req.window_years,
        req.max_depth_evolution,
    )


@app.get("/analyze/{paper_id:path}")
def analyze_get(
    paper_id: str,
    max_children: int = Query(5),
    max_depth_tree: int = Query(2),
    window_years: int = Query(3),
    max_depth_evolution: int = Query(MAX_DEPTH),
):
    return _run(paper_id, max_children, max_depth_tree, window_years, max_depth_evolution)


@app.get("/search")
def search_papers(q: str = Query(..., min_length=1, description="Paper title to search")):
    """Search for papers by title via Semantic Scholar.

    Returns top 10 matches with metadata.
    Falls back to database ILIKE search if the API fails.
    """
    # 1. Try Semantic Scholar search API
    s2 = SemanticScholarClient()
    try:
        result = s2.api_call(
            "paper/search",
            params={
                "query": q,
                "limit": 10,
                "fields": "paperId,externalIds,title,abstract,year,"
                          "citationCount,influentialCitationCount,authors,venue",
            },
        )
        if result and result.get("data"):
            return {"results": result["data"], "source": "semantic_scholar"}
    except Exception:
        pass

    # 2. Fallback: search the local database cache
    cache = Cache(DATABASE_URL)
    try:
        import psycopg2.extras
        with cache._get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT paper_id AS \"paperId\", arxiv_id, title, year, abstract, "
                    "       citation_count AS \"citationCount\", "
                    "       influential_citation_count AS \"influentialCitationCount\" "
                    "FROM papers WHERE title ILIKE %s "
                    "ORDER BY citation_count DESC NULLS LAST LIMIT 10",
                    (f"%{q}%",),
                )
                rows = [dict(r) for r in cur.fetchall()]
        if rows:
            return {"results": rows, "source": "database"}
    except Exception:
        pass

    return {"results": [], "source": "none"}


def _run(paper_id, max_children, max_depth_tree, window_years, max_depth_evolution):
    try:
        result = run(
            paper_id,
            max_children=max_children,
            max_depth_tree=max_depth_tree,
            window_years=window_years,
            max_depth_evolution=max_depth_evolution,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    if result["tree"] is None and result["timeline"] is None:
        raise HTTPException(status_code=404, detail=f"Could not process paper: {paper_id}")

    return result
