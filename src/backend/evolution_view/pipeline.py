"""
evolution_view/pipeline.py
---------------------------
Main orchestrator for the evolution (timeline) pipeline.

Flow per step:
    1. get_paper()  via common.SemanticScholarClient
    2. get_references() via common.SemanticScholarClient
    3. filter_methodology_references() via common.SemanticScholarClient
    4. extract_paper_text()
    5. analyze_step() → Gemini selects predecessor + analyzes
    6. save to common.Cache
    7. predecessor becomes new target → repeat

Stops when:
    - No methodology references found (foundational paper)
    - Max depth reached
    - Cycle detected
"""

import time

from ..common.s2_client import SemanticScholarClient
from ..common.cache import Cache
from ..common.config import DATABASE_URL, MAX_DEPTH, VERBOSE, logger, log_event

from .text_extraction import extract_paper_text
from .gemini_analysis import analyze_step, analyze_foundational, MAIN_PROMPT, FOUNDATIONAL_PROMPT
from .data_export import save_training_example, save_timeline_json

print = logger.info


def build_timeline(paper_id: str, max_depth: int = MAX_DEPTH,
                   dsn: str = DATABASE_URL):
    """
    Build complete research lineage timeline for a paper.

    Returns:
        (steps_list, from_cache)

        Each step:
        {
            depth, target_paper, target_text, target_source_type,
            predecessor_paper, candidates_considered, analysis, is_foundational
        }
    """
    s2    = SemanticScholarClient()
    cache = Cache(dsn)

    timeline_steps     = []
    current_paper_id   = paper_id
    visited            = set()
    original_target_info = None
    lineage_chain      = []

    log_event("PIPELINE_START", paper_id=paper_id, max_depth=max_depth)

    # Full chain cache check
    cached_steps, from_cache = cache.get_cached_timeline(paper_id, max_depth)
    if from_cache:
        log_event("PIPELINE_CACHE_HIT", paper_id=paper_id, papers=len(cached_steps))
        if VERBOSE:
            print(f"  Full timeline served from cache ({len(cached_steps)} papers)")
        return cached_steps, True

    for depth in range(max_depth):
        if VERBOSE:
            print(f"\n{'─' * 50}")
            print(f"  STEP {depth + 1} / {max_depth}")
            print(f"{'─' * 50}")

        # 1. Fetch target paper
        target_paper = cache.get_paper(current_paper_id) or s2.get_paper(
            current_paper_id, full_fields=True
        )
        if not target_paper:
            if VERBOSE:
                print(f"  Could not fetch paper. Stopping.")
            break

        current_paper_id = target_paper["paperId"]

        if current_paper_id in visited:
            if VERBOSE:
                print(f"  Cycle detected at {current_paper_id}. Stopping.")
            break
        visited.add(current_paper_id)
        cache.save_paper(target_paper)

        if original_target_info is None:
            abstract = target_paper.get("abstract") or ""
            title    = target_paper.get("title", "")
            original_target_info = {
                "title":  title,
                "domain": f"{title}. {abstract[:200]}",
            }

        # Per-step cache check (Gemini already ran for this paper)
        cached_analysis = cache.get_cached_analysis(target_paper["paperId"])
        if cached_analysis:
            if VERBOSE:
                print(f"  Analysis cached — skipping API + Gemini")
            log_event("STEP_CACHE_HIT", depth=depth, paper_id=target_paper["paperId"])
            pred_id    = cached_analysis.get("selected_predecessor_id")
            pred_paper = cache.get_paper(pred_id) if pred_id else None
            lineage_chain.append(target_paper["paperId"])
            step = {
                "depth":              depth,
                "target_paper":       target_paper,
                "target_text":        "",
                "target_source_type": target_paper.get("_source_type") or "FULL_TEXT",
                "predecessor_paper":  pred_paper,
                "candidates_considered": 0,
                "analysis":           cached_analysis,
                "is_foundational":    pred_paper is None,
            }
            timeline_steps.append(step)
            if pred_paper is None or not pred_id:
                break
            current_paper_id = pred_id
            continue

        # 2. Extract paper text
        target_text, target_source = extract_paper_text(target_paper)
        cache.save_paper(target_paper, source_type=target_source)

        # 3. Fetch references
        references = s2.get_references(current_paper_id, full_fields=True)
        cache.save_references(current_paper_id, references or [])

        # 4. Filter methodology candidates
        candidates = SemanticScholarClient.filter_methodology_references(references) if references else []

        if not candidates:
            step = _handle_foundational(
                depth, target_paper, target_text, target_source, lineage_chain, cache
            )
            if step:
                timeline_steps.append(step)
            break

        # 5. Extract candidate texts
        candidates_with_text = [
            (c["paper"], *extract_paper_text(c["paper"]), c["contexts"])
            for c in candidates
        ]

        # 6. Call Gemini
        analysis, prompt_text, raw_response = analyze_step(
            target_text, candidates_with_text, original_target_info
        )
        if not analysis:
            if VERBOSE:
                print(f"  Gemini analysis failed. Stopping.")
            break

        selected_id = analysis.get("selected_predecessor_id")

        if not selected_id or selected_id == "null":
            step = _handle_foundational(
                depth, target_paper, target_text, target_source, lineage_chain, cache
            )
            if step:
                step["analysis"]["target_analysis"] = analysis.get(
                    "target_analysis", step["analysis"].get("target_analysis", {})
                )
                timeline_steps.append(step)
            break

        cache.save_analysis(target_paper["paperId"], selected_id, False, analysis)

        predecessor_paper = next(
            (c["paper"] for c in candidates if c["paper"].get("paperId") == selected_id),
            candidates[0]["paper"] if candidates else None,
        )
        if not predecessor_paper:
            break

        log_event("STEP_COMPLETE", depth=depth, paper_id=target_paper["paperId"],
                  predecessor_id=selected_id)

        lineage_chain.append(target_paper["paperId"])
        step = {
            "depth":                 depth,
            "target_paper":          target_paper,
            "target_text":           target_text,
            "target_source_type":    target_source,
            "predecessor_paper":     predecessor_paper,
            "candidates_considered": len(candidates),
            "analysis":              analysis,
            "is_foundational":       False,
        }
        timeline_steps.append(step)

        save_training_example(
            paper_id=target_paper["paperId"],
            instruction=MAIN_PROMPT,
            prompt_text=prompt_text,
            response_text=raw_response,
            metadata={
                "target_paper_id":      target_paper["paperId"],
                "target_title":         target_paper.get("title"),
                "predecessor_paper_id": predecessor_paper["paperId"],
                "depth":                depth,
                "candidates_considered": len(candidates),
                "target_source_type":   target_source,
                "model":                "gemini-2.5-pro",
                "timestamp":            time.strftime("%Y-%m-%d %H:%M:%S"),
            },
            target_paper=target_paper,
            candidates=candidates,
            predecessor_paper=predecessor_paper,
            lineage_chain=list(lineage_chain),
        )

        current_paper_id = predecessor_paper["paperId"]
        time.sleep(1)

    # Check if last predecessor needs foundational analysis
    if timeline_steps and not timeline_steps[-1]["is_foundational"]:
        last_pred = timeline_steps[-1]["predecessor_paper"]
        last_refs = s2.get_references(last_pred["paperId"], full_fields=True)
        last_candidates = SemanticScholarClient.filter_methodology_references(last_refs) if last_refs else []
        if not last_candidates:
            last_text, last_source = extract_paper_text(last_pred)
            last_step = _handle_foundational(
                len(timeline_steps), last_pred, last_text, last_source, lineage_chain, cache
            )
            if last_step:
                timeline_steps.append(last_step)

    log_event("PIPELINE_COMPLETE", paper_id=paper_id,
              total_papers=len(timeline_steps), from_cache=False)

    return timeline_steps, False


# ── Helpers ───────────────────────────────────────────────────────────────────

def _handle_foundational(depth, paper, paper_text, source_type, lineage_chain, cache):
    analysis, prompt_text, raw_response = analyze_foundational(paper_text)
    if not analysis:
        return None

    cache.save_paper(paper, source_type=source_type)
    cache.save_analysis(paper["paperId"], None, True, analysis)

    chain = list(lineage_chain) + [paper["paperId"]]
    save_training_example(
        paper_id=paper["paperId"],
        instruction=FOUNDATIONAL_PROMPT,
        prompt_text=prompt_text,
        response_text=raw_response,
        metadata={
            "target_paper_id":      paper["paperId"],
            "target_title":         paper.get("title"),
            "predecessor_paper_id": None,
            "depth":                depth,
            "candidates_considered": 0,
            "target_source_type":   source_type,
            "is_foundational":      True,
            "model":                "gemini-2.5-pro",
            "timestamp":            time.strftime("%Y-%m-%d %H:%M:%S"),
        },
        target_paper=paper,
        candidates=None,
        predecessor_paper=None,
        lineage_chain=chain,
    )

    return {
        "depth":                 depth,
        "target_paper":          paper,
        "target_text":           paper_text,
        "target_source_type":    source_type,
        "predecessor_paper":     None,
        "candidates_considered": 0,
        "analysis":              analysis,
        "is_foundational":       True,
    }
