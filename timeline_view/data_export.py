"""
data_export.py - Save pipeline outputs for fine-tuning and visualization

Training data format — ready for fine-tuning, no reconstruction needed:
{
    "instruction": "system prompt used",
    "input": "exact prompt sent to Gemini",
    "output": "exact JSON response from Gemini",
    "metadata": {...}
}

Timeline JSON — complete timeline for frontend / DB loading.
"""

import json
import os
import time

from config import TRAINING_DATA_FILE, TIMELINE_OUTPUT_DIR, VERBOSE
from config import logger
print = logger.info

# ========================================
# Training Data Export
# ========================================

def save_training_example(paper_id, instruction, prompt_text, response_text,
                         metadata=None, target_paper=None, candidates=None,
                         predecessor_paper=None, lineage_chain=None):
    os.makedirs(os.path.dirname(TRAINING_DATA_FILE) or ".", exist_ok=True)
    if _example_exists(paper_id):
        if VERBOSE:
            print(f"  ⏭️  Training example for {paper_id} already exists. Skipping.")
        return

    candidate_metadata = []
    if candidates:
        for c in candidates:
            p = c.get("paper", {}) if isinstance(c, dict) and "paper" in c else c
            candidate_metadata.append(_build_paper_metadata(p))

    example = {
        "instruction": instruction,
        "input": prompt_text,
        "output": response_text,
        "metadata": metadata or {},
        "level_info": {
            "target_paper": _build_paper_metadata(target_paper) if target_paper else {},
            "predecessor_paper": _build_paper_metadata(predecessor_paper) if predecessor_paper else None,
            "candidates_passed_to_llm": candidate_metadata,
            "lineage_chain": lineage_chain or []
        }
    }

    with open(TRAINING_DATA_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(example, ensure_ascii=False) + "\n")

    if VERBOSE:
        total = count_training_examples()
        chain_str = " → ".join(lineage_chain) if lineage_chain else "N/A"
        print(f"  💾 Training example saved to {TRAINING_DATA_FILE} "
              f"(total: {total})")
        print(f"     Chain so far: {chain_str}")


def _build_paper_metadata(paper_data):
    if not paper_data:
        return {}

    fields = paper_data.get("fieldsOfStudy") or []
    s2_fields = paper_data.get("s2FieldsOfStudy") or []
    primary_field = None
    if fields:
        primary_field = fields[0]
    elif s2_fields:
        for f in s2_fields:
            if f.get("source") == "external":
                primary_field = f.get("category")
                break
        if not primary_field and s2_fields:
            primary_field = s2_fields[0].get("category")

    return {
        "paper_id": paper_data.get("paperId"),
        "title": paper_data.get("title"),
        "year": paper_data.get("year"),
        "citation_count": paper_data.get("citationCount"),
        "field_of_study": primary_field,
        "arxiv_id": (paper_data.get("externalIds") or {}).get("ArXiv")
    }


# ========================================
# Timeline JSON Export
# ========================================

def save_timeline_json(timeline_steps, filename=None):
    """
    Save complete timeline as structured JSON.
    Chain ordered oldest → newest with position numbers.

    Output structure:
    {
        "target_paper": {paperId, title, year},
        "generated_at": "2026-02-17 ...",
        "total_papers": int,
        "total_steps": int,
        "chain": [
            {
                "position": 1,  (oldest first)
                "paper": {paperId, title, year, abstract},
                "analysis": {target_analysis fields},
                "comparison_with_next": {comparison fields} or null,
                "secondary_influences": [...],
                "source_type": "FULL_TEXT" or "ABSTRACT_ONLY",
                "is_foundational": bool
            },
            ...
        ]
    }

    Args:
        timeline_steps: List from build_timeline()
        filename: Output filename. If None, auto-generated.

    Returns:
        str: Filepath of saved file, or None
    """
    if not timeline_steps:
        if VERBOSE:
            print("  ⚠️  No timeline data to save.")
        return None

    os.makedirs(TIMELINE_OUTPUT_DIR, exist_ok=True)

    chain = _build_ordered_chain(timeline_steps)

    original_target = timeline_steps[0]["target_paper"]

    output = {
        "target_paper": {
            "paperId": original_target.get("paperId"),
            "title": original_target.get("title"),
            "year": original_target.get("year"),
        },
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_papers": len(chain),
        "total_steps": len(timeline_steps),
        "chain": chain
    }

    if not filename:
        safe_title = original_target.get("title", "unknown")[:40]
        safe_title = "".join(c if c.isalnum() or c in " -_" else "" for c in safe_title)
        safe_title = safe_title.strip().replace(" ", "_")
        filename = f"timeline_{safe_title}.json"

    filepath = os.path.join(TIMELINE_OUTPUT_DIR, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    if VERBOSE:
        print(f"  💾 Timeline saved to {filepath}")
        print(f"     Papers: {len(chain)}, Steps: {len(timeline_steps)}")

    return filepath


# ========================================
# API Response Builder
# ========================================

def _enrich_secondary_influences(timeline_steps):
    """
    Batch-fetch titles/years for secondary influence paper IDs via S2.
    Updates steps in-place. Called automatically by build_timeline_response
    when enrich=True.
    """
    import requests as _requests

    id_set = set()
    for step in timeline_steps:
        for inf in step["analysis"].get("secondary_influences", []):
            if isinstance(inf, dict) and inf.get("paper_id") and not inf.get("title"):
                id_set.add(inf["paper_id"])

    if not id_set:
        return

    id_list = list(id_set)
    title_map = {}

    for i in range(0, len(id_list), 500):
        batch = id_list[i:i + 500]
        try:
            resp = _requests.post(
                "https://api.semanticscholar.org/graph/v1/paper/batch",
                json={"ids": batch},
                params={"fields": "paperId,title,year"},
                timeout=20
            )
            if resp.status_code == 200:
                for paper in resp.json():
                    if paper and paper.get("paperId"):
                        title_map[paper["paperId"]] = {
                            "title": paper.get("title", ""),
                            "year":  paper.get("year", ""),
                        }
        except Exception:
            pass

    for step in timeline_steps:
        for inf in step["analysis"].get("secondary_influences", []):
            if isinstance(inf, dict) and inf.get("paper_id") in title_map:
                inf["title"] = title_map[inf["paper_id"]].get("title", "")
                inf["year"]  = title_map[inf["paper_id"]].get("year", "")


def build_timeline_response(timeline_steps, from_cache=False, elapsed_time=None, enrich=True):
    """
    Build the canonical API response dict from pipeline output.

    This is the single source of truth for the timeline response format.
    - The Streamlit UI calls this directly and renders from it.
    - The REST API teammate wraps this in an HTTP response.
    - Nothing in the UI should read from raw timeline_steps directly.

    Args:
        timeline_steps: List from build_timeline()
        from_cache:     Whether the result was served from DB cache
        elapsed_time:   Wall-clock seconds from request to response
        enrich:         If True (default), fetch titles for secondary influences
                        from S2 before building the response. Set False to skip
                        the network call (e.g. in tests or batch processing).

    Returns:
        dict with keys:
            seed_paper, from_cache, elapsed_time, generated_at,
            total_papers, year_range, chain
        or None if timeline_steps is empty.
    """
    if not timeline_steps:
        return None

    if enrich:
        _enrich_secondary_influences(timeline_steps)

    seed = timeline_steps[0]["target_paper"]
    chain = []

    for step in reversed(timeline_steps):
        paper    = step["target_paper"]
        analysis = step["analysis"]
        ta       = analysis.get("target_analysis") or {}
        comp     = analysis.get("comparison")
        secondary = analysis.get("secondary_influences") or []

        chain.append({
            "paper": {
                "paper_id":      paper.get("paperId"),
                "title":         paper.get("title"),
                "year":          paper.get("year"),
                "abstract":      paper.get("abstract"),
                "citation_count": paper.get("citationCount"),
                "arxiv_id":      (paper.get("externalIds") or {}).get("ArXiv"),
            },
            "source_type":        step["target_source_type"],
            "is_foundational":    step["is_foundational"],
            "selection_reasoning": analysis.get("selection_reasoning"),
            "analysis": {
                "problem_addressed":    ta.get("problem_addressed"),
                "core_method":          ta.get("core_method"),
                "key_innovation":       ta.get("key_innovation"),
                "limitations":          ta.get("limitations") or [],
                "breakthrough_level":   ta.get("breakthrough_level"),
                "explanation_eli5":     ta.get("explanation_eli5"),
                "explanation_intuitive": ta.get("explanation_intuitive"),
                "explanation_technical": ta.get("explanation_technical"),
            },
            "comparison": {
                "what_was_improved":               comp.get("what_was_improved"),
                "how_it_was_improved":             comp.get("how_it_was_improved"),
                "why_it_matters":                  comp.get("why_it_matters"),
                "problem_solved_from_predecessor": comp.get("problem_solved_from_predecessor"),
                "remaining_limitations":           comp.get("remaining_limitations") or [],
            } if comp else None,
            "secondary_influences": [
                {
                    "paper_id":    inf.get("paper_id"),
                    "title":       inf.get("title"),
                    "year":        inf.get("year"),
                    "contribution": inf.get("contribution"),
                }
                for inf in secondary if isinstance(inf, dict)
            ],
        })

    for i, entry in enumerate(chain, 1):
        entry["position"] = i

    first_year = chain[0]["paper"]["year"] if chain else None
    last_year  = chain[-1]["paper"]["year"] if chain else None

    return {
        "seed_paper": {
            "paper_id": seed.get("paperId"),
            "title":    seed.get("title"),
            "year":     seed.get("year"),
        },
        "from_cache":   from_cache,
        "elapsed_time": elapsed_time,
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_papers": len(chain),
        "year_range": {
            "start": first_year,
            "end":   last_year,
            "span":  (last_year - first_year)
                     if isinstance(first_year, int) and isinstance(last_year, int)
                     else None,
        },
        "chain": chain,
    }


def _build_ordered_chain(timeline_steps):
    """
    Convert steps (target→predecessor) into ordered chain (oldest→newest).

    Steps:  Transformer→Attention, Attention→Seq2Seq, Seq2Seq→LSTM, LSTM(foundational)
    Chain:  LSTM(1), Seq2Seq(2), Attention(3), Transformer(4)
    """
    chain = []

    for step in reversed(timeline_steps):
        target = step["target_paper"]
        analysis = step["analysis"]

        entry = {
            "paper": {
                "paperId": target.get("paperId"),
                "title": target.get("title"),
                "year": target.get("year"),
                "abstract": target.get("abstract", ""),
            },
            "analysis": analysis.get("target_analysis", {}),
            "source_type": step["target_source_type"],
            "is_foundational": step["is_foundational"],
            "secondary_influences": analysis.get("secondary_influences", []),
        }

        if step["is_foundational"]:
            entry["comparison_with_next"] = None
        else:
            entry["comparison_with_next"] = analysis.get("comparison")

        chain.append(entry)

    for i, entry in enumerate(chain, 1):
        entry["position"] = i

    return chain


# ========================================
# Utility: Check & Count Training Examples
# ========================================

def _example_exists(paper_id):
    """
    Check if a training example for this paper already exists.

    Checks metadata.target_paper_id field in existing examples.
    """
    if not paper_id or not os.path.exists(TRAINING_DATA_FILE):
        return False

    with open(TRAINING_DATA_FILE, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                example = json.loads(line)
                existing_id = example.get("metadata", {}).get("target_paper_id")
                if existing_id == paper_id:
                    return True
            except json.JSONDecodeError:
                continue

    return False


def count_training_examples():
    """Count total training examples in the JSONL file."""
    if not os.path.exists(TRAINING_DATA_FILE):
        return 0

    count = 0
    with open(TRAINING_DATA_FILE, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                count += 1
    return count


# ========================================
# Test
# ========================================

if __name__ == "__main__":
    from semantic_scholar import get_paper, get_references, filter_methodology_references

    print("=" * 60)
    print("Testing Data Export with REAL Semantic Scholar Data")
    print("=" * 60)

    # Test 1: Fetch real paper + references
    print("\n1️⃣  Fetching Transformer paper from Semantic Scholar...")
    target = get_paper("ARXIV:1706.03762")
    if not target:
        print("   ❌ Failed to fetch paper. Try again later.")
        exit()

    print("\n2️⃣  Fetching references...")
    refs = get_references("ARXIV:1706.03762")
    candidates = filter_methodology_references(refs)

    # Fetch full details for candidates (same as pipeline does)
    print("\n3️⃣  Fetching full details for top candidates...")
    enriched_candidates = []
    for c in candidates[:3]:  # Only 3 to save time
        p = c["paper"]
        full = get_paper(p["paperId"])
        if full:
            c["paper"] = full
        enriched_candidates.append(c)

    # Pick first candidate as mock predecessor
    predecessor = enriched_candidates[0]["paper"] if enriched_candidates else None

    # Test 4: Save training example with real data
    print("\n4️⃣  Saving training example with real metadata...")
    save_training_example(
        paper_id=target["paperId"],
        instruction="[TEST] You are an expert research analyst...",
        prompt_text="[TEST] This is a test prompt, not sent to Gemini",
        response_text='{"selected_predecessor_id": "test", "target_analysis": {}}',
        metadata={
            "target_paper_id": target["paperId"],
            "target_title": target.get("title"),
            "predecessor_paper_id": predecessor["paperId"] if predecessor else None,
            "depth": 0,
            "candidates_considered": len(enriched_candidates),
            "target_source_type": "FULL_TEXT",
            "model": "test-no-gemini",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        },
        target_paper=target,
        candidates=enriched_candidates,
        predecessor_paper=predecessor,
        lineage_chain=[target["paperId"]]
    )

    # Test 5: Read back and verify all fields
    print("\n5️⃣  Verifying saved metadata...")
    with open(TRAINING_DATA_FILE, "r", encoding="utf-8") as f:
        for line in f:
            example = json.loads(line.strip())
            li = example.get("level_info", {})

            print(f"\n   --- TARGET PAPER ---")
            tp = li.get("target_paper", {})
            for k, v in tp.items():
                print(f"   {k}: {v}")

            print(f"\n   --- PREDECESSOR PAPER ---")
            pp = li.get("predecessor_paper", {})
            if pp:
                for k, v in pp.items():
                    print(f"   {k}: {v}")
            else:
                print("   None")

            print(f"\n   --- CANDIDATES PASSED TO LLM ({len(li.get('candidates_passed_to_llm', []))}) ---")
            for i, c in enumerate(li.get("candidates_passed_to_llm", []), 1):
                print(f"   {i}. {c.get('title', '?')[:55]}")
                print(f"      paper_id: {c.get('paper_id', '?')[:20]}...")
                print(f"      year: {c.get('year')}")
                print(f"      citation_count: {c.get('citation_count')}")
                print(f"      field_of_study: {c.get('field_of_study')}")
                print(f"      arxiv_id: {c.get('arxiv_id')}")

            print(f"\n   --- LINEAGE CHAIN ---")
            print(f"   {li.get('lineage_chain')}")

    # Cleanup
    print("\n6️⃣  Cleaning up test file...")
    if os.path.exists(TRAINING_DATA_FILE):
        os.remove(TRAINING_DATA_FILE)
        print(f"   Removed {TRAINING_DATA_FILE}")

    print("\n✅ Done!")