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

import json
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional

from .orchestrator import run
from .common.config import MAX_DEPTH, DATABASE_URL, GEMINI_API_KEY, GEMINI_MODEL
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


class ChatMessage(BaseModel):
    role: str   # "user" or "model"
    content: str


class ChatRequest(BaseModel):
    paper_id: str
    messages: list[ChatMessage]


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


@app.post("/chat")
def chat(req: ChatRequest):
    """Stream a chat response about a paper's lineage using Gemini."""
    cache = Cache(DATABASE_URL)
    steps, ok = cache.get_cached_timeline(req.paper_id)
    if not ok or not steps:
        raise HTTPException(
            status_code=404,
            detail="No timeline found for this paper. Run /analyze first.",
        )

    system_prompt = _build_chat_system_prompt(steps)
    return StreamingResponse(
        _stream_gemini(system_prompt, req.messages),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _build_chat_system_prompt(steps: list) -> str:
    """Serialize the cached timeline into a Gemini system prompt."""
    # Steps are seed → foundational; reverse for oldest-first narrative
    ordered = list(reversed(steps))
    seed_paper = steps[0].get("target_paper", {})

    lines = [
        "You are a research assistant specializing in academic paper lineages.",
        f'You are helping a user explore the intellectual lineage of the paper "{seed_paper.get("title", "Unknown")}" ({seed_paper.get("year", "?")}).',
        "The chain below runs from the oldest foundational work to the seed paper.",
        "Use this context to answer questions. Be specific and cite paper titles and years.",
        "Keep answers conversational, well-structured, and concise unless depth is requested.",
        "",
        "=" * 64,
        "LINEAGE CHAIN",
        "=" * 64,
    ]

    for i, step in enumerate(ordered):
        paper = step.get("target_paper", {})
        analysis_wrap = step.get("analysis", {})
        analysis = analysis_wrap.get("target_analysis", {})
        comparison = analysis_wrap.get("comparison")
        is_seed = i == len(ordered) - 1
        label = "SEED PAPER" if is_seed else f"Paper {i + 1} of {len(ordered) - 1}"

        lines += [
            "",
            f"[{label}]",
            f"Title    : {paper.get('title', 'Unknown')}",
            f"Year     : {paper.get('year', '?')}",
            f"Citations: {paper.get('citation_count', '?')}",
            f"Level    : {analysis.get('breakthrough_level', '?')}",
        ]
        for field, key in [
            ("Problem addressed", "problem_addressed"),
            ("Key innovation", "key_innovation"),
            ("Core method", "core_method"),
        ]:
            val = analysis.get(key)
            if val:
                lines.append(f"{field}: {val}")

        if comparison and not is_seed:
            lines += [
                "  Improvement over predecessor:",
                f"    What changed : {comparison.get('what_was_improved', '')}",
                f"    How          : {comparison.get('how_it_was_improved', '')}",
                f"    Why it matters: {comparison.get('why_it_matters', '')}",
            ]

    lines += [
        "",
        "=" * 64,
        "Answer only questions about this lineage and the papers above.",
        "If a question is unrelated, politely redirect to the lineage.",
    ]
    return "\n".join(lines)


def _stream_gemini(system_prompt: str, messages: list[ChatMessage]):
    """Generator that yields SSE-formatted chunks from Gemini."""
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=GEMINI_API_KEY)
    contents = [
        types.Content(role=m.role, parts=[types.Part(text=m.content)])
        for m in messages
    ]
    try:
        response = client.models.generate_content_stream(
            model=GEMINI_MODEL,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.7,
                max_output_tokens=2048,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
        )
        for chunk in response:
            text = getattr(chunk, "text", None)
            if text:
                yield f"data: {json.dumps({'text': text})}\n\n"
    except Exception as e:
        yield f"data: {json.dumps({'error': str(e)})}\n\n"
    yield "data: [DONE]\n\n"


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
