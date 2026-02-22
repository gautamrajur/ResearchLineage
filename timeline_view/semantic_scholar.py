"""
semantic_scholar.py - Semantic Scholar API for Timeline Pipeline

Standalone module — does not depend on tree_view.py.
API call pattern matches tree view's proven logic
(retry, rate limiting, 1.2s delay between calls).
"""

import requests
import time
import re

from config import (
    S2_BASE_URL, S2_API_KEY, S2_REQUEST_TIMEOUT,
    S2_MAX_RETRIES, S2_RETRY_BASE_WAIT,
    MAX_CANDIDATES, VERBOSE
)
from config import logger
print = logger.info

# ========================================
# Base API Call (matches tree view pattern)
# ========================================

def api_call(endpoint, params=None):
    """
    Make a Semantic Scholar API call with retry logic.
    Mirrors TreeView.api_call() — same retry, same delays.

    Args:
        endpoint: API path (e.g., "paper/ARXIV:1706.03762")
        params: Query parameters dict

    Returns:
        dict: JSON response or None on failure
    """
    url = f"{S2_BASE_URL}/{endpoint.lstrip('/')}"

    headers = {}
    if S2_API_KEY:
        headers["x-api-key"] = S2_API_KEY

    for attempt in range(S2_MAX_RETRIES):
        try:
            response = requests.get(
                url, params=params, headers=headers,
                timeout=S2_REQUEST_TIMEOUT
            )

            if response.status_code == 200:
                time.sleep(1.2)  # Same delay as tree view
                return response.json()

            elif response.status_code == 429:
                wait = S2_RETRY_BASE_WAIT * (attempt + 1)
                if VERBOSE:
                    print(f"  ⚠️  Rate limited! Waiting {wait}s... "
                          f"(Attempt {attempt + 1}/{S2_MAX_RETRIES})")
                time.sleep(wait)
                continue

            elif response.status_code == 404:
                if VERBOSE:
                    print(f"  ❌ Paper not found: {endpoint}")
                return None

            else:
                if VERBOSE:
                    print(f"  ❌ Error {response.status_code}: "
                          f"{response.text[:200]}")
                return None

        except Exception as e:
            if VERBOSE:
                print(f"  ❌ Request failed: {str(e)}")
            return None

    if VERBOSE:
        print(f"  ❌ Failed after {S2_MAX_RETRIES} retries")
    return None


# ========================================
# Paper Details
# ========================================

# Timeline needs more fields than tree view:
# Tree view: paperId, title, year, citationCount, influentialCitationCount
# Timeline adds: abstract, tldr, externalIds, openAccessPdf, authors
PAPER_FIELDS = (
    "paperId,externalIds,title,abstract,year,"
    "citationCount,influentialCitationCount,"
    "fieldsOfStudy,s2FieldsOfStudy,"
    "tldr,openAccessPdf,authors"
)

def get_paper(paper_id):
    """
    Fetch paper with full details for timeline analysis.

    Args:
        paper_id: Any format — arXiv URL, raw ID, ARXIV: prefix, or S2 hash

    Returns:
        dict: Paper data or None
    """
    paper_id = normalize_paper_id(paper_id)
    result = api_call(f"paper/{paper_id}", {"fields": PAPER_FIELDS})

    if result and VERBOSE:
        print(f"  ✅ {result.get('title', 'Unknown')} ({result.get('year', '?')})")

    return result


# ========================================
# References with Contexts
# ========================================

# Timeline adds contexts and more citedPaper fields vs tree view:
# Tree view: citedPaper.paperId, citedPaper.title, citedPaper.year,
#            citedPaper.citationCount, isInfluential, intents
# Timeline adds: contexts, citedPaper.abstract, citedPaper.tldr,
#                citedPaper.externalIds, citedPaper.openAccessPdf,
#                citedPaper.influentialCitationCount
REFERENCE_FIELDS = (
    "citedPaper.paperId,citedPaper.title,"
    "citedPaper.year,citedPaper.citationCount,"
    "citedPaper.externalIds,"
    "isInfluential,intents,contexts"
)

def get_references(paper_id):
    """
    Fetch all references with citation contexts and intents.

    Args:
        paper_id: Paper ID in any format

    Returns:
        list: Reference dicts with citedPaper, contexts, intents,
              isInfluential. Empty list on failure.
    """
    paper_id = normalize_paper_id(paper_id)

    result = api_call(
        f"paper/{paper_id}/references",
        {"fields": REFERENCE_FIELDS, "limit": 1000}
    )

    if result and "data" in result:
        refs = result["data"]
        if refs and VERBOSE:
            print(f"  📚 Total references: {len(refs)}")
        return refs if refs else []

    return []


# ========================================
# Reference Filtering
# ========================================

def filter_methodology_references(references):
    """
    Filter references to methodology candidates for Gemini.

    Same logic as tree view's build_recursive_ancestors():
        1. Keep papers with "methodology" in intents
        2. If not enough, add isInfluential papers as fallback
        3. Sort by citation count
        4. Take top MAX_CANDIDATES

    Gemini does the actual predecessor selection from these.

    Args:
        references: Raw list from get_references()

    Returns:
        list of dicts:
            {
                "paper": {citedPaper data},
                "is_influential": bool,
                "has_methodology": bool,
                "intents": list,
                "contexts": list of citation sentences
            }
    """
    methodology_refs = []
    influential_refs = []

    for ref in references:
        cited = ref.get("citedPaper") or {}

        # Skip invalid
        if not cited.get("paperId") or not cited.get("title"):
            continue

        intents = ref.get("intents") or []
        is_influential = ref.get("isInfluential", False)
        has_methodology = "methodology" in intents

        entry = {
            "paper": cited,
            "is_influential": is_influential,
            "has_methodology": has_methodology,
            "intents": intents,
            "contexts": ref.get("contexts") or []
        }

        if has_methodology:
            methodology_refs.append(entry)
        elif is_influential:
            influential_refs.append(entry)

    # Fallback: add influential if not enough methodology
    # (same pattern as tree view)
    if len(methodology_refs) < MAX_CANDIDATES:
        methodology_ids = {e["paper"]["paperId"] for e in methodology_refs}
        for entry in influential_refs:
            if entry["paper"]["paperId"] not in methodology_ids:
                methodology_refs.append(entry)

    candidates = methodology_refs

    # Sort by citation count, take top N
    candidates.sort(
        key=lambda c: c["paper"].get("citationCount") or 0,
        reverse=True
    )
    top = candidates[:MAX_CANDIDATES]

    if VERBOSE:
        print(f"  🔬 Filtered: {len(candidates)} candidates "
              f"(sending top {len(top)} to Gemini)")
        for i, c in enumerate(top, 1):
            p = c["paper"]
            cites = p.get("citationCount") or 0
            flags = []
            if c["has_methodology"]:
                flags.append("methodology")
            if c["is_influential"]:
                flags.append("influential")
            print(f"     {i}. {p.get('title', '?')[:60]}... "
                  f"({cites:,} cites, {', '.join(flags)})")

    return top


# ========================================
# Utilities
# ========================================

def normalize_paper_id(paper_id):
    """
    Normalize paper ID to S2 format.

    "https://arxiv.org/abs/1706.03762"  → "ARXIV:1706.03762"
    "1706.03762"                         → "ARXIV:1706.03762"
    "ARXIV:1706.03762"                   → "ARXIV:1706.03762"
    "649def34f8be..."                    → "649def34f8be..."
    """
    paper_id = paper_id.strip()

    # Full arXiv URLs
    for pattern in [
        r'arxiv\.org/abs/(\d+\.\d+)',
        r'arxiv\.org/pdf/(\d+\.\d+)',
        r'arxiv\.org/html/(\d+\.\d+)',
    ]:
        match = re.search(pattern, paper_id)
        if match:
            return f"ARXIV:{match.group(1)}"

    # Raw arXiv ID
    if re.match(r'^\d{4}\.\d{4,5}(v\d+)?$', paper_id):
        return f"ARXIV:{paper_id}"

    # Older format (cs/0123456)
    if re.match(r'^[a-z-]+/\d+$', paper_id):
        return f"ARXIV:{paper_id}"

    return paper_id


def get_arxiv_id(paper_data):
    """
    Extract arXiv ID from paper data.

    Returns:
        str: e.g., "1706.03762" or None
    """
    external_ids = paper_data.get("externalIds") or {}
    return external_ids.get("ArXiv")


# ========================================
# Test
# ========================================

if __name__ == "__main__":
    print("=" * 60)
    print("Testing Semantic Scholar Module")
    print("=" * 60)

    print("\n1️⃣  Fetching 'Attention Is All You Need'...")
    paper = get_paper("1706.03762")
    if paper:
        print(f"   Title: {paper['title']}")
        print(f"   Year: {paper['year']}")
        print(f"   Citations: {paper['citationCount']}")
        print(f"   arXiv ID: {get_arxiv_id(paper)}")
        print(f"   Has abstract: {bool(paper.get('abstract'))}")
        print(f"   Has TLDR: {bool(paper.get('tldr'))}")

    print("\n2️⃣  Fetching references with contexts...")
    refs = get_references("ARXIV:1706.03762")
    if refs:
        sample = refs[0]
        cited = sample.get("citedPaper", {})
        print(f"   Sample: {cited.get('title', '?')[:50]}")
        print(f"   Contexts: {len(sample.get('contexts') or [])}")
        print(f"   Intents: {sample.get('intents')}")
        print(f"   Influential: {sample.get('isInfluential')}")

    print("\n3️⃣  Filtering methodology references...")
    candidates = filter_methodology_references(refs)

    print("\n4️⃣  ID normalization...")
    for tid in ["1706.03762", "ARXIV:1706.03762",
                "https://arxiv.org/abs/1706.03762",
                "649def34f8be52c8b66281af98ae884c09aef38b"]:
        print(f"   {tid:55s} → {normalize_paper_id(tid)}")

    print("\n✅ Done!")