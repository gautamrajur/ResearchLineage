"""
orchestrator.py
---------------
Single entry point: takes an arXiv ID and runs both views sequentially.

    Step 1 — pred_successor_view: builds the bidirectional tree
             (ancestors + descendants via citation counts, no Gemini)

    Step 2 — evolution_view: traces the linear ancestry chain backwards
             using Gemini to pick + analyse predecessors at each step

Both views share the same PostgreSQL cache, so references fetched in
Step 1 are already cached when Step 2 runs.

Usage:
    from src.backend.orchestrator import run

    result = run("ARXIV:1706.03762")
    print(result["tree"])       # pred_successor_view output
    print(result["timeline"])   # evolution_view output
"""

import time
from typing import Optional

from .common.s2_client import SemanticScholarClient
from .common.config import DATABASE_URL, MAX_DEPTH, logger, log_event
from .pred_successor_view.builder import PredSuccessorView
from .evolution_view.pipeline import build_timeline
from .evolution_view.data_export import build_timeline_response


def run(
    paper_id: str,
    # pred_successor_view settings
    max_children: int = 5,
    max_depth_tree: int = 2,
    window_years: int = 3,
    # evolution_view settings
    max_depth_evolution: int = MAX_DEPTH,
    # shared
    dsn: str = DATABASE_URL,
    api_key: Optional[str] = None,
) -> dict:
    """
    Run both views sequentially for a given paper ID.

    Args:
        paper_id:            arXiv ID in any format
                             ("1706.03762", "ARXIV:1706.03762",
                              "https://arxiv.org/abs/1706.03762")
        max_children:        pred_successor_view — max nodes per level
        max_depth_tree:      pred_successor_view — recursion depth
        window_years:        pred_successor_view — year window for descendants
        max_depth_evolution: evolution_view — how far back to trace
        dsn:                 PostgreSQL connection string
        api_key:             Semantic Scholar API key (optional)

    Returns:
        {
            "paper_id":       normalised paper ID,
            "tree":           pred_successor_view result dict or None,
            "timeline":       evolution_view API response dict or None,
            "elapsed": {
                "tree_sec":      float,
                "evolution_sec": float,
                "total_sec":     float,
            }
        }
    """
    paper_id = SemanticScholarClient.normalize_paper_id(paper_id)

    logger.info("=" * 70)
    logger.info("ORCHESTRATOR START  paper=%s", paper_id)
    logger.info("=" * 70)
    log_event("ORCHESTRATOR_START", paper_id=paper_id)

    t_total = time.perf_counter()

    # ------------------------------------------------------------------
    # Step 1 — pred_successor_view (tree)
    # ------------------------------------------------------------------
    logger.info("STEP 1 — pred_successor_view")
    t1 = time.perf_counter()

    tree_result = None
    try:
        view = PredSuccessorView(api_key=api_key, dsn=dsn)
        tree_result = view.build_tree(
            paper_id,
            max_children=max_children,
            max_depth=max_depth_tree,
            window_years=window_years,
        )
        logger.info("STEP 1 DONE  elapsed=%.1fs", time.perf_counter() - t1)
    except Exception as e:
        logger.error("STEP 1 FAILED  error=%s", e)

    elapsed_tree = time.perf_counter() - t1

    # ------------------------------------------------------------------
    # Step 2 — evolution_view (timeline)
    # ------------------------------------------------------------------
    logger.info("STEP 2 — evolution_view")
    t2 = time.perf_counter()

    timeline_result = None
    from_cache      = False
    try:
        steps, from_cache = build_timeline(
            paper_id,
            max_depth=max_depth_evolution,
            dsn=dsn,
        )
        timeline_result = build_timeline_response(
            steps,
            from_cache=from_cache,
            elapsed_time=round(time.perf_counter() - t2, 2),
        )
        logger.info("STEP 2 DONE  elapsed=%.1fs  from_cache=%s",
                    time.perf_counter() - t2, from_cache)
    except Exception as e:
        logger.error("STEP 2 FAILED  error=%s", e)

    elapsed_evolution = time.perf_counter() - t2
    elapsed_total     = time.perf_counter() - t_total

    logger.info("=" * 70)
    logger.info("ORCHESTRATOR DONE  total=%.1fs  tree=%.1fs  evolution=%.1fs",
                elapsed_total, elapsed_tree, elapsed_evolution)
    logger.info("=" * 70)
    log_event("ORCHESTRATOR_DONE", paper_id=paper_id,
              total_sec=f"{elapsed_total:.1f}",
              tree_sec=f"{elapsed_tree:.1f}",
              evolution_sec=f"{elapsed_evolution:.1f}")

    return {
        "paper_id": paper_id,
        "tree":     tree_result,
        "timeline": timeline_result,
        "elapsed": {
            "tree_sec":      round(elapsed_tree, 2),
            "evolution_sec": round(elapsed_evolution, 2),
            "total_sec":     round(elapsed_total, 2),
        },
    }
