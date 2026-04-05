"""
backend/api.py
--------------
FastAPI wrapper around the orchestrator.

Endpoints:
    GET  /health
    POST /analyze          — run both views, return tree + timeline JSON
    GET  /analyze/{paper_id} — same but via GET with query params

Usage:
    uvicorn src.backend.api:app --reload --port 8000
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from typing import Optional

from .orchestrator import run
from .common.config import MAX_DEPTH, DATABASE_URL
from .common.cache import Cache


@asynccontextmanager
async def lifespan(app: FastAPI):
    Cache(DATABASE_URL)  # run DDL once at startup
    yield


app = FastAPI(title="ResearchLineage API", version="1.0.0", lifespan=lifespan)


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
