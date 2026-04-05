"""
evolution_view/data_export.py
------------------------------
Save pipeline outputs for fine-tuning and visualization.
Same logic as original, updated to use common.config imports.
"""

import json
import os
import time
import requests as _requests

from ..common.config import TRAINING_DATA_FILE, TIMELINE_OUTPUT_DIR, VERBOSE, logger

print = logger.info


# ── Training data ──────────────────────────────────────────────────────────────

def save_training_example(paper_id, instruction, prompt_text, response_text,
                          metadata=None, target_paper=None, candidates=None,
                          predecessor_paper=None, lineage_chain=None):
    os.makedirs(os.path.dirname(TRAINING_DATA_FILE) or ".", exist_ok=True)
    if _example_exists(paper_id):
        if VERBOSE:
            print(f"  Training example for {paper_id} already exists. Skipping.")
        return

    candidate_metadata = []
    if candidates:
        for c in candidates:
            p = c.get("paper", {}) if isinstance(c, dict) and "paper" in c else c
            candidate_metadata.append(_build_paper_metadata(p))

    example = {
        "instruction": instruction,
        "input":       prompt_text,
        "output":      response_text,
        "metadata":    metadata or {},
        "level_info": {
            "target_paper":            _build_paper_metadata(target_paper) if target_paper else {},
            "predecessor_paper":       _build_paper_metadata(predecessor_paper) if predecessor_paper else None,
            "candidates_passed_to_llm": candidate_metadata,
            "lineage_chain":           lineage_chain or [],
        },
    }

    with open(TRAINING_DATA_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(example, ensure_ascii=False) + "\n")

    if VERBOSE:
        print(f"  Training example saved ({count_training_examples()} total)")


def _build_paper_metadata(paper_data):
    if not paper_data:
        return {}
    fields   = paper_data.get("fieldsOfStudy") or []
    s2fields = paper_data.get("s2FieldsOfStudy") or []
    field    = fields[0] if fields else (
        next((f.get("category") for f in s2fields if f.get("source") == "external"), None)
        or (s2fields[0].get("category") if s2fields else None)
    )
    return {
        "paper_id":       paper_data.get("paperId"),
        "title":          paper_data.get("title"),
        "year":           paper_data.get("year"),
        "citation_count": paper_data.get("citationCount"),
        "field_of_study": field,
        "arxiv_id":       (paper_data.get("externalIds") or {}).get("ArXiv"),
    }


def _example_exists(paper_id):
    if not paper_id or not os.path.exists(TRAINING_DATA_FILE):
        return False
    with open(TRAINING_DATA_FILE, "r", encoding="utf-8") as f:
        for line in f:
            try:
                if json.loads(line).get("metadata", {}).get("target_paper_id") == paper_id:
                    return True
            except json.JSONDecodeError:
                continue
    return False


def count_training_examples():
    if not os.path.exists(TRAINING_DATA_FILE):
        return 0
    with open(TRAINING_DATA_FILE, "r", encoding="utf-8") as f:
        return sum(1 for line in f if line.strip())


# ── Timeline JSON export ───────────────────────────────────────────────────────

def save_timeline_json(timeline_steps, filename=None):
    if not timeline_steps:
        return None
    os.makedirs(TIMELINE_OUTPUT_DIR, exist_ok=True)
    chain  = _build_ordered_chain(timeline_steps)
    target = timeline_steps[0]["target_paper"]
    output = {
        "target_paper":  {"paperId": target.get("paperId"), "title": target.get("title"), "year": target.get("year")},
        "generated_at":  time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_papers":  len(chain),
        "total_steps":   len(timeline_steps),
        "chain":         chain,
    }
    if not filename:
        safe = "".join(c if c.isalnum() or c in " -_" else "" for c in (target.get("title", "unknown")[:40]))
        filename = f"timeline_{safe.strip().replace(' ', '_')}.json"
    filepath = os.path.join(TIMELINE_OUTPUT_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    if VERBOSE:
        print(f"  Timeline saved to {filepath}")
    return filepath


# ── API response builder ───────────────────────────────────────────────────────

def build_timeline_response(timeline_steps, from_cache=False, elapsed_time=None, enrich=True):
    """
    Build the canonical API response dict from pipeline output.
    Single source of truth consumed by both the Streamlit UI and REST API.
    """
    if not timeline_steps:
        return None
    if enrich:
        _enrich_secondary_influences(timeline_steps)

    seed  = timeline_steps[0]["target_paper"]
    chain = []

    for step in reversed(timeline_steps):
        paper    = step["target_paper"]
        analysis = step["analysis"]
        ta       = analysis.get("target_analysis") or {}
        comp     = analysis.get("comparison")
        secondary = analysis.get("secondary_influences") or []

        chain.append({
            "paper": {
                "paper_id":       paper.get("paperId"),
                "title":          paper.get("title"),
                "year":           paper.get("year"),
                "abstract":       paper.get("abstract"),
                "citation_count": paper.get("citationCount"),
                "arxiv_id":       (paper.get("externalIds") or {}).get("ArXiv"),
            },
            "source_type":         step["target_source_type"],
            "is_foundational":     step["is_foundational"],
            "selection_reasoning": analysis.get("selection_reasoning"),
            "analysis": {
                "problem_addressed":     ta.get("problem_addressed"),
                "core_method":           ta.get("core_method"),
                "key_innovation":        ta.get("key_innovation"),
                "limitations":           ta.get("limitations") or [],
                "breakthrough_level":    ta.get("breakthrough_level"),
                "explanation_eli5":      ta.get("explanation_eli5"),
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
                {"paper_id": inf.get("paper_id"), "title": inf.get("title"),
                 "year": inf.get("year"), "contribution": inf.get("contribution")}
                for inf in secondary if isinstance(inf, dict)
            ],
        })

    for i, entry in enumerate(chain, 1):
        entry["position"] = i

    first_year = chain[0]["paper"]["year"] if chain else None
    last_year  = chain[-1]["paper"]["year"] if chain else None

    return {
        "seed_paper":   {"paper_id": seed.get("paperId"), "title": seed.get("title"), "year": seed.get("year")},
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


def _enrich_secondary_influences(timeline_steps):
    id_set = {
        inf["paper_id"]
        for step in timeline_steps
        for inf in step["analysis"].get("secondary_influences", [])
        if isinstance(inf, dict) and inf.get("paper_id") and not inf.get("title")
    }
    if not id_set:
        return
    logger.debug("_enrich_secondary_influences: fetching %d titles from S2", len(id_set))
    title_map = {}
    for i in range(0, len(id_set), 500):
        batch = list(id_set)[i:i + 500]
        try:
            resp = _requests.post(
                "https://api.semanticscholar.org/graph/v1/paper/batch",
                json={"ids": batch}, params={"fields": "paperId,title,year"}, timeout=20,
            )
            if resp.status_code == 200:
                for p in resp.json():
                    if p and p.get("paperId"):
                        title_map[p["paperId"]] = {"title": p.get("title", ""), "year": p.get("year", "")}
        except Exception:
            pass
    for step in timeline_steps:
        for inf in step["analysis"].get("secondary_influences", []):
            if isinstance(inf, dict) and inf.get("paper_id") in title_map:
                inf["title"] = title_map[inf["paper_id"]]["title"]
                inf["year"]  = title_map[inf["paper_id"]]["year"]


def _build_ordered_chain(timeline_steps):
    chain = []
    for step in reversed(timeline_steps):
        target   = step["target_paper"]
        analysis = step["analysis"]
        entry = {
            "paper": {
                "paperId": target.get("paperId"),
                "title":   target.get("title"),
                "year":    target.get("year"),
                "abstract": target.get("abstract", ""),
            },
            "analysis":              analysis.get("target_analysis", {}),
            "source_type":           step["target_source_type"],
            "is_foundational":       step["is_foundational"],
            "secondary_influences":  analysis.get("secondary_influences", []),
            "comparison_with_next":  None if step["is_foundational"] else analysis.get("comparison"),
        }
        chain.append(entry)
    for i, entry in enumerate(chain, 1):
        entry["position"] = i
    return chain
