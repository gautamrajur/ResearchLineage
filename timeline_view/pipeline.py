"""
pipeline.py - Main orchestrator for the timeline pipeline

Wires together:
    semantic_scholar.py → text_extraction.py → gemini_analysis.py

Flow per step:
    1. get_paper() → paper details
    2. get_references() → all references
    3. filter_methodology_references() → top candidates
    4. extract_paper_text() → text for target + each candidate
    5. analyze_step() → Gemini selects predecessor + analyzes + compares
    6. Save step data + training example
    7. Predecessor becomes new target → repeat

Stops when:
    - No methodology references found (foundational paper)
    - Max depth reached
    - Paper already visited (cycle detection)
"""

import time

from config import MAX_DEPTH, VERBOSE, log_event
from semantic_scholar import (
    get_paper, get_references,
    filter_methodology_references, get_arxiv_id
)
from text_extraction import extract_paper_text
from gemini_analysis import (
    analyze_step, analyze_foundational,
    MAIN_PROMPT, FOUNDATIONAL_PROMPT
)
from data_export import save_training_example, save_timeline_json
import cache as _cache
from config import logger
print = logger.info

# ========================================
# Main Pipeline
# ========================================

def build_timeline(paper_id, max_depth=MAX_DEPTH):
    """
    Build complete research lineage timeline for a paper.

    Args:
        paper_id: arXiv URL, arXiv ID, or S2 paper ID

    Returns:
        list: Timeline steps from target (depth 0) to oldest ancestor.
              Each step is a dict:
              {
                  "depth": int,
                  "target_paper": {paperId, title, year, abstract, ...},
                  "target_text": str (formatted text sent to Gemini),
                  "target_source_type": "FULL_TEXT" or "ABSTRACT_ONLY",
                  "predecessor_paper": {paperId, title, year, ...} or None,
                  "candidates_considered": int,
                  "analysis": {Gemini output dict},
                  "is_foundational": bool
              }
    """
    timeline_steps = []
    current_paper_id = paper_id
    visited = set()
    original_target_info = None
    lineage_chain = []  # Track full chain of paper IDs

    _print_header("BUILDING RESEARCH LINEAGE TIMELINE")
    log_event("PIPELINE_START", paper_id=paper_id, max_depth=max_depth)

    # ── Full chain cache check ────────────────────────────────────────────────
    cached_steps, from_cache = _cache.get_cached_timeline(paper_id, max_depth)
    if from_cache:
        if VERBOSE:
            print(f"  ⚡ Full timeline served from cache ({len(cached_steps)} papers)")
        log_event("PIPELINE_CACHE_HIT", paper_id=paper_id, papers=len(cached_steps))
        return cached_steps, True

    for depth in range(max_depth):
        _print_step_header(depth, max_depth)

        # --- 1. Fetch target paper ---
        if VERBOSE:
            print(f"\n  1️⃣  Fetching paper details...")
        target_paper = _cache.get_paper(current_paper_id) or get_paper(current_paper_id)
        if not target_paper:
            if VERBOSE:
                print(f"  ❌ Could not fetch paper. Stopping.")
            break
        # Normalise current_paper_id to S2 paperId so cache lookups and
        # cycle detection always use the canonical ID, not an arXiv string.
        current_paper_id = target_paper["paperId"]

        # --- Cycle detection (after ID normalisation) ---
        if current_paper_id in visited:
            if VERBOSE:
                print(f"  ⚠️  Already visited {current_paper_id}. Stopping.")
            break
        visited.add(current_paper_id)

        _cache.save_paper(target_paper)

        # Track original target paper info for domain consistency
        if original_target_info is None:
            abstract = target_paper.get("abstract", "")
            title = target_paper.get("title", "")
            # Ask Gemini to infer domain would cost tokens — just use title + first sentence of abstract
            domain_hint = f"{title}. {abstract[:200] if abstract else ''}"
            original_target_info = {
                "title": title,
                "domain": domain_hint
            }

        # --- Per-step analysis cache check ---
        # If Gemini has already analysed this paper, skip text extraction,
        # references fetch, and the Gemini call entirely.
        # Use target_paper["paperId"] (resolved S2 ID) not current_paper_id
        # which may still be an arXiv ID on the first iteration.
        cached_analysis = _cache.get_cached_analysis(target_paper["paperId"])
        if cached_analysis:
            if VERBOSE:
                print(f"  ⚡ Analysis cached for this paper — skipping API + Gemini")
            log_event("STEP_CACHE_HIT", depth=depth, paper_id=target_paper["paperId"],
                      title=repr(target_paper.get("title","")[:60]))
            pred_id   = cached_analysis.get("selected_predecessor_id")
            pred_paper = _cache.get_paper(pred_id) if pred_id else None
            is_found  = pred_paper is None
            lineage_chain.append(target_paper.get("paperId"))
            step = {
                "depth":              depth,
                "target_paper":       target_paper,
                "target_text":        "",
                "target_source_type": target_paper.get("_source_type") or "FULL_TEXT",
                "predecessor_paper":  pred_paper,
                "candidates_considered": 0,
                "analysis":           cached_analysis,
                "is_foundational":    is_found,
            }
            timeline_steps.append(step)
            if is_found or not pred_id:
                break
            current_paper_id = pred_id
            continue

        # --- 2. Extract target paper text ---
        if VERBOSE:
            print(f"\n  2️⃣  Extracting target paper text...")
        target_text, target_source = extract_paper_text(target_paper)
        if VERBOSE:
            print(f"    Source: {target_source} "
                  f"(~{len(target_text) // 4:,} tokens)")
        log_event("TEXT_EXTRACTED", paper_id=target_paper["paperId"],
                  source=target_source, chars=len(target_text))
        _cache.save_paper(target_paper, source_type=target_source)

        # --- 3. Fetch references ---
        if VERBOSE:
            print(f"\n  3️⃣  Fetching references...")
        references = get_references(current_paper_id)

        _cache.save_references(current_paper_id, references or [])

        # --- 4. Filter methodology references ---
        if VERBOSE:
            print(f"\n  4️⃣  Filtering methodology references...")
        candidates = filter_methodology_references(references) if references else []

        # --- No candidates = foundational paper ---
        if not candidates:
            if VERBOSE:
                print(f"\n  📍 No methodology candidates found.")
                print(f"     This is a FOUNDATIONAL paper. Running final analysis...")

            step = _handle_foundational_paper(
                depth, target_paper, target_text, target_source, lineage_chain
            )
            if step:
                timeline_steps.append(step)
            break

        # --- 5. Extract text for all candidates ---
        if VERBOSE:
            print(f"\n  5️⃣  Extracting text for {len(candidates)} candidates...")
        candidates_with_text = _extract_candidate_texts(candidates)

        # --- 6. Call Gemini ---
        if VERBOSE:
            print(f"\n  6️⃣  Calling Gemini for analysis...")
        analysis, prompt_text, raw_response = analyze_step(
            target_text, candidates_with_text, original_target_info
        )
        if not analysis:
            if VERBOSE:
                print(f"  ❌ Gemini analysis failed. Stopping.")
            break

        # --- 7. Find selected predecessor ---
        selected_id = analysis.get("selected_predecessor_id")

        # Gemini might return null if no same-domain predecessor found
        if not selected_id or selected_id == "null":
            if VERBOSE:
                print(f"\n  📍 Gemini found no same-domain predecessor.")
                print(f"     Treating current paper as foundational...")
            step = _handle_foundational_paper(
                depth, target_paper, target_text, target_source
            )
            if step:
                # Merge the existing analysis into foundational step
                step["analysis"]["target_analysis"] = analysis.get("target_analysis", step["analysis"].get("target_analysis", {}))
                timeline_steps.append(step)
            break

        # Save Gemini analysis to cache (only when a valid predecessor was found)
        log_event("STEP_COMPLETE", depth=depth, paper_id=target_paper["paperId"],
                  predecessor_id=selected_id,
                  title=repr(target_paper.get("title","")[:60]))
        _cache.save_analysis(target_paper["paperId"], selected_id, False, analysis)

        predecessor_paper = _find_predecessor(selected_id, candidates)

        if not predecessor_paper:
            if VERBOSE:
                print(f"  ❌ Selected predecessor not found in candidates. Stopping.")
            break

        if VERBOSE:
            print(f"\n  ✅ PREDECESSOR SELECTED:")
            print(f"     {predecessor_paper.get('title', '?')} "
                  f"({predecessor_paper.get('year', '?')})")
            print(f"     Reason: {analysis.get('selection_reasoning', 'N/A')[:100]}...")

        # --- 8. Save step ---
        lineage_chain.append(target_paper.get("paperId"))

        step = {
            "depth": depth,
            "target_paper": target_paper,
            "target_text": target_text,
            "target_source_type": target_source,
            "predecessor_paper": predecessor_paper,
            "candidates_considered": len(candidates),
            "analysis": analysis,
            "is_foundational": False
        }
        timeline_steps.append(step)

        # --- 9. Save training example ---
        save_training_example(
            paper_id=target_paper["paperId"],
            instruction=MAIN_PROMPT,
            prompt_text=prompt_text,
            response_text=raw_response,
            metadata={
                "target_paper_id": target_paper["paperId"],
                "target_title": target_paper.get("title"),
                "predecessor_paper_id": predecessor_paper["paperId"],
                "depth": depth,
                "candidates_considered": len(candidates),
                "target_source_type": target_source,
                "model": "gemini-2.5-pro",
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            },
            target_paper=target_paper,
            candidates=[c for c in candidates],
            predecessor_paper=predecessor_paper,
            lineage_chain=list(lineage_chain)
        )

        # --- 10. Move to predecessor ---
        current_paper_id = predecessor_paper["paperId"]

        if VERBOSE:
            print(f"\n  ➡️  Moving to predecessor for next step...")
        time.sleep(1)

    # --- Check if we need to analyze the last predecessor ---
    # The last predecessor never became a target, so it has no analysis yet.
    # Unless we already handled it as foundational above.
    if timeline_steps and not timeline_steps[-1]["is_foundational"]:
        last_predecessor = timeline_steps[-1]["predecessor_paper"]

        # Check if this predecessor has methodology references
        if VERBOSE:
            print(f"\n  🔍 Checking if last predecessor needs foundational analysis...")
        last_refs = get_references(last_predecessor["paperId"])
        last_candidates = filter_methodology_references(last_refs) if last_refs else []

        if not last_candidates:
            # It's foundational — analyze it
            if VERBOSE:
                print(f"  📍 Last predecessor is foundational. Analyzing...")
            last_text, last_source = extract_paper_text(last_predecessor)
            last_step = _handle_foundational_paper(
                len(timeline_steps), last_predecessor, last_text, last_source, lineage_chain
            )
            if last_step:
                timeline_steps.append(last_step)

    _print_summary(timeline_steps)
    log_event("PIPELINE_COMPLETE", paper_id=paper_id,
              total_papers=len(timeline_steps), from_cache=False)

    return timeline_steps, False


# ========================================
# Helper Functions
# ========================================

def _handle_foundational_paper(depth, paper, paper_text, source_type, lineage_chain=None):
    """
    Run foundational analysis for the last paper in chain.

    Returns:
        dict: Step data or None on failure
    """
    analysis, prompt_text, raw_response = analyze_foundational(paper_text)
    if not analysis:
        if VERBOSE:
            print(f"  ❌ Foundational analysis failed.")
        return None

    if VERBOSE:
        bt = analysis.get("target_analysis", {}).get("breakthrough_level", "?")
        print(f"  ✅ Foundational paper analyzed (breakthrough: {bt})")

    _cache.save_paper(paper, source_type=source_type)
    _cache.save_analysis(paper["paperId"], None, True, analysis)

    # Add this paper to the chain
    if lineage_chain is not None:
        lineage_chain = list(lineage_chain) + [paper["paperId"]]
    else:
        lineage_chain = [paper["paperId"]]

    # Save training example
    save_training_example(
        paper_id=paper["paperId"],
        instruction=FOUNDATIONAL_PROMPT,
        prompt_text=prompt_text,
        response_text=raw_response,
        metadata={
            "target_paper_id": paper["paperId"],
            "target_title": paper.get("title"),
            "predecessor_paper_id": None,
            "depth": depth,
            "candidates_considered": 0,
            "target_source_type": source_type,
            "is_foundational": True,
            "model": "gemini-2.5-pro",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        },
        target_paper=paper,
        candidates=None,
        predecessor_paper=None,
        lineage_chain=lineage_chain
    )

    return {
        "depth": depth,
        "target_paper": paper,
        "target_text": paper_text,
        "target_source_type": source_type,
        "predecessor_paper": None,
        "candidates_considered": 0,
        "analysis": analysis,
        "is_foundational": True
    }


def _extract_candidate_texts(candidates):
    """
    Extract text for each candidate paper.

    Args:
        candidates: List from filter_methodology_references()

    Returns:
        list of tuples: (paper_data, text, source_type, contexts)
    """
    results = []
    for c in candidates:
        paper = c["paper"]
        text, source_type = extract_paper_text(paper)
        results.append((paper, text, source_type, c["contexts"]))
    return results


def _find_predecessor(selected_id, candidates):
    """
    Find the selected predecessor in the candidate list.

    Args:
        selected_id: paperId string from Gemini output
        candidates: List from filter_methodology_references()

    Returns:
        dict: Paper data or None
    """
    if not selected_id:
        return None

    for c in candidates:
        if c["paper"].get("paperId") == selected_id:
            return c["paper"]

    # Gemini might have returned a slightly different ID format
    # Try matching by title as fallback
    if VERBOSE:
        print(f"  ⚠️  Exact ID match failed for {selected_id}. "
              f"Trying first candidate as fallback...")
    if candidates:
        return candidates[0]["paper"]

    return None


# ========================================
# Display
# ========================================

def display_timeline(timeline_steps):
    """
    Pretty-print the timeline from oldest to newest.

    Args:
        timeline_steps: List from build_timeline()
    """
    if not timeline_steps:
        print("No timeline data to display.")
        return

    # Build ordered list: oldest (foundational) → newest (target)
    papers = []

    # Walk backwards through steps
    for step in reversed(timeline_steps):
        analysis = step["analysis"]
        target = step["target_paper"]
        ta = analysis.get("target_analysis", {})

        papers.append({
            "title": target.get("title", "?"),
            "year": target.get("year", "?"),
            "analysis": ta,
            "comparison": analysis.get("comparison"),
            "is_foundational": step["is_foundational"],
            "depth": step["depth"]
        })

    print(f"\n{'=' * 70}")
    print(f"📅 RESEARCH LINEAGE TIMELINE")
    print(f"{'=' * 70}\n")

    for i, paper in enumerate(papers):
        year = paper["year"]
        title = paper["title"]
        ta = paper["analysis"]

        # Breakthrough icon
        bt = ta.get("breakthrough_level", "minor")
        icon = {
            "revolutionary": "🔥",
            "major": "⚡",
            "moderate": "💡",
            "minor": "○"
        }.get(bt, "○")

        # Markers
        markers = []
        if i == len(papers) - 1:
            markers.append("🎯 TARGET")
        if paper["is_foundational"]:
            markers.append("🏛️ FOUNDATION")
        marker_str = " ".join(markers)

        print(f"  {year} ── {title}")
        print(f"         {icon} {bt.upper()} {marker_str}")
        print(f"         📌 {ta.get('key_innovation', 'N/A')[:80]}")

        # Show comparison (how this improved upon previous)
        comp = paper.get("comparison")
        if comp:
            print(f"         ⬆️  Improved: {comp.get('what_was_improved', 'N/A')[:80]}")

        print()

        # Arrow to next paper
        if i < len(papers) - 1:
            print(f"         │")
            print(f"         ▼")
            print()

    print(f"{'=' * 70}")
    print(f"  Papers in lineage: {len(papers)}")
    first_year = papers[0]["year"] if papers else "?"
    last_year = papers[-1]["year"] if papers else "?"
    print(f"  Time span: {first_year} → {last_year}")
    print(f"{'=' * 70}")


# ========================================
# Print Helpers
# ========================================

def _print_header(text):
    if VERBOSE:
        print(f"\n{'=' * 60}")
        print(f"🔬 {text}")
        print(f"{'=' * 60}")


def _print_step_header(depth, max_depth):
    if VERBOSE:
        print(f"\n{'─' * 50}")
        print(f"📍 STEP {depth + 1} / {max_depth}")
        print(f"{'─' * 50}")


def _print_summary(timeline_steps):
    if VERBOSE:
        print(f"\n{'=' * 60}")
        print(f"✅ TIMELINE COMPLETE: {len(timeline_steps)} papers traced")

        total_cost = 0
        for step in timeline_steps:
            tokens = len(step.get("target_text", "")) // 4
            total_cost += (tokens / 1_000_000) * 1.25

        print(f"   Estimated total cost: ${total_cost:.3f}")
        print(f"{'=' * 60}")


# ========================================
# Test
# ========================================

if __name__ == "__main__":
    print("Testing Pipeline with 'Attention Is All You Need'")
    print("=" * 60)

    # Run the pipeline
    timeline, _ = build_timeline("1706.03762", max_depth=6)

    # Display results
    display_timeline(timeline)

    # Save results
    save_timeline_json(timeline, "transformer_timeline.json")

    print("\n✅ Pipeline test complete!")