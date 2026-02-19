#!/usr/bin/env python3
"""
ResearchLineage — 01_fetch_and_analyze.py

Fetches all data for a seed paper from the Semantic Scholar Graph API and
writes structured JSON files for review before SQL generation.

Output files (written to --output-dir):
  raw_target.json         — seed paper metadata
  raw_references.json     — papers the seed cites (ancestors, recursive)
  raw_citations.json      — papers citing the seed (descendants, recursive)
  raw_all_papers.json     — deduplicated union of all papers
  raw_all_authors.json    — deduplicated union of all authors
  raw_all_edges.json      — all (citing, cited, context) edges discovered

Usage:
  python 01_fetch_and_analyze.py --paper-id ARXIV:1706.03762
  python 01_fetch_and_analyze.py --paper-id 204e3073870fae3d05bcbc2f6a8e263d9b72e776 \\
      --api-key YOUR_KEY --max-depth 2 --max-children 5 --output-dir ./output
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Semantic Scholar API client
# ---------------------------------------------------------------------------

BASE_URL = "https://api.semanticscholar.org/graph/v1"

PAPER_FIELDS = (
    "paperId,title,abstract,venue,year,publicationDate,"
    "citationCount,influentialCitationCount,isOpenAccess,"
    "openAccessPdf,externalIds,url,authors"
)

# NOTE: citedPaper.abstract / citingPaper.abstract cause HTTP 500 on the
# Semantic Scholar edge endpoints (known API bug as of 2026-02).
# Abstract is fetched separately via GET /paper/{id} after selection.
EDGE_FIELDS_REFS = (
    "citedPaper.paperId,citedPaper.title,"
    "citedPaper.venue,citedPaper.year,citedPaper.publicationDate,"
    "citedPaper.citationCount,citedPaper.influentialCitationCount,"
    "citedPaper.isOpenAccess,citedPaper.externalIds,citedPaper.url,"
    "citedPaper.authors,isInfluential,intents"
)

EDGE_FIELDS_CITES = (
    "citingPaper.paperId,citingPaper.title,"
    "citingPaper.venue,citingPaper.year,citingPaper.publicationDate,"
    "citingPaper.citationCount,citingPaper.influentialCitationCount,"
    "citingPaper.isOpenAccess,citingPaper.externalIds,citingPaper.url,"
    "citingPaper.authors,isInfluential,intents"
)


def api_get(endpoint: str, params: dict, api_key: Optional[str] = None,
            max_retries: int = 10) -> Optional[dict]:
    """GET request with rate-limit retry and backoff."""
    try:
        import requests
    except ImportError:
        print("ERROR: 'requests' not installed. Run: pip install requests")
        sys.exit(1)

    url = f"{BASE_URL}/{endpoint.lstrip('/')}"
    headers = {"x-api-key": api_key} if api_key else {}

    for attempt in range(max_retries):
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=30)

            if resp.status_code == 200:
                time.sleep(1.2 if not api_key else 0.15)  # respect rate limit
                return resp.json()

            if resp.status_code == 429:
                wait = 5 * (attempt + 1)
                print(f"  ⚠  Rate limited — waiting {wait}s (attempt {attempt + 1}/{max_retries})")
                time.sleep(wait)
                continue

            if resp.status_code == 404:
                print(f"  ✗  404 Not Found: {url}")
                return None

            print(f"  ✗  HTTP {resp.status_code}: {resp.text[:200]}")
            return None

        except Exception as exc:
            print(f"  ✗  Request error: {exc}")
            if attempt < max_retries - 1:
                time.sleep(3)

    print(f"  ✗  Failed after {max_retries} retries: {url}")
    return None


def fetch_paper(paper_id: str, api_key: Optional[str]) -> Optional[dict]:
    return api_get(f"paper/{paper_id}", {"fields": PAPER_FIELDS}, api_key)


def enrich_with_abstract(paper: dict, api_key: Optional[str]) -> dict:
    """Fetch the abstract for a paper separately (abstract breaks edge endpoints)."""
    pid = paper.get("paperId")
    if not pid or paper.get("abstract") is not None:
        return paper
    result = api_get(f"paper/{pid}", {"fields": "paperId,abstract"}, api_key)
    if result and result.get("abstract"):
        paper["abstract"] = result["abstract"]
    return paper


def fetch_all_pages(endpoint: str, params: dict, api_key: Optional[str],
                    page_size: int = 1000, max_total: int = 10_000) -> list:
    """Paginate through a /references or /citations endpoint."""
    all_items = []
    offset = 0

    while offset < max_total:
        params["limit"]  = page_size
        params["offset"] = offset
        data = api_get(endpoint, params, api_key)

        if not data or "data" not in data or not data["data"]:
            break

        batch = data["data"]
        all_items.extend(batch)
        print(f"    fetched {len(all_items):,} items so far...")

        if len(batch) < page_size:
            break  # last page

        offset += page_size
        time.sleep(2)  # extra courtesy delay between pages

    return all_items


# ---------------------------------------------------------------------------
# Recursive tree traversal
# ---------------------------------------------------------------------------

# Global accumulators (deduplicated by paperId)
_all_papers: dict[str, dict] = {}
_all_authors: dict[str, dict] = {}
_all_edges: list[dict] = []
_visited: set[str] = set()


def _register_paper(paper: dict) -> None:
    """Add a paper + its authors to global accumulators."""
    if not paper or not paper.get("paperId"):
        return
    _all_papers[paper["paperId"]] = paper
    for author in paper.get("authors") or []:
        if author.get("authorId"):
            _all_authors[author["authorId"]] = author


def fetch_ancestors(paper_id: str, paper_year: Optional[int],
                    depth: int, max_depth: int, max_children: int,
                    api_key: Optional[str]) -> list[dict]:
    """Fetch references (papers cited BY paper_id) recursively."""
    if depth >= max_depth or paper_id in _visited:
        return []
    _visited.add(paper_id)

    indent = "  " * depth
    print(f"{indent}→ depth {depth}: fetching references for {paper_id[:12]}...")

    params = {"fields": EDGE_FIELDS_REFS, "limit": 500}
    raw = fetch_all_pages(f"paper/{paper_id}/references", params, api_key)

    if not raw:
        return []

    # Filter: prefer methodology intent, fall back to influential
    methodology = [r for r in raw
                   if "methodology" in (r.get("intents") or [])]
    if len(methodology) < max_children:
        influential = [r for r in raw if r.get("isInfluential")]
        candidates = methodology + [r for r in influential if r not in methodology]
    else:
        candidates = methodology

    # Sort by citation count, take top N
    candidates.sort(
        key=lambda r: (r.get("citedPaper") or {}).get("citationCount") or 0,
        reverse=True,
    )
    top = candidates[:max_children]

    nodes = []
    for edge in top:
        cited = edge.get("citedPaper")
        if not cited or not cited.get("paperId"):
            continue

        # Fetch abstract separately (abstract field breaks edge endpoints)
        cited = enrich_with_abstract(cited, api_key)
        _register_paper(cited)
        _all_edges.append({
            "citing_paper_id": paper_id,
            "cited_paper_id":  cited["paperId"],
            "intents":         edge.get("intents") or [],
            "is_influential":  bool(edge.get("isInfluential")),
        })

        children = fetch_ancestors(
            cited["paperId"], cited.get("year"),
            depth + 1, max_depth, max_children, api_key
        )
        nodes.append({"paper": cited, "ancestors": children})

    return nodes


def fetch_descendants(paper_id: str, paper_year: Optional[int],
                      depth: int, max_depth: int, max_children: int,
                      window_years: int, api_key: Optional[str]) -> list[dict]:
    """Fetch citations (papers that cite paper_id) recursively."""
    desc_key = f"desc_{paper_id}"
    if depth >= max_depth or desc_key in _visited:
        return []
    _visited.add(desc_key)

    indent = "  " * depth
    print(f"{indent}→ depth {depth}: fetching citations for {paper_id[:12]}...")

    params = {"fields": EDGE_FIELDS_CITES, "limit": 1000}
    if paper_year:
        params["publicationDateOrYear"] = f"{paper_year + 1}:{paper_year + window_years}"

    raw = fetch_all_pages(f"paper/{paper_id}/citations", params, api_key,
                          page_size=1000, max_total=10_000)

    if not raw:
        return []

    methodology = [r for r in raw
                   if "methodology" in (r.get("intents") or [])
                   and (r.get("citingPaper") or {}).get("paperId")]
    if len(methodology) < max_children:
        influential = [r for r in raw
                       if r.get("isInfluential")
                       and (r.get("citingPaper") or {}).get("paperId")]
        candidates = methodology + [r for r in influential if r not in methodology]
    else:
        candidates = methodology

    citing_papers = [(r.get("citingPaper"), r) for r in candidates if r.get("citingPaper")]
    citing_papers.sort(key=lambda x: x[0].get("citationCount") or 0, reverse=True)
    top = citing_papers[:max_children]

    nodes = []
    for citing, edge in top:
        if not citing.get("paperId"):
            continue

        # Fetch abstract separately (abstract field breaks edge endpoints)
        citing = enrich_with_abstract(citing, api_key)
        _register_paper(citing)
        _all_edges.append({
            "citing_paper_id": citing["paperId"],
            "cited_paper_id":  paper_id,
            "intents":         edge.get("intents") or [],
            "is_influential":  bool(edge.get("isInfluential")),
        })

        children = fetch_descendants(
            citing["paperId"], citing.get("year"),
            depth + 1, max_depth, max_children, window_years, api_key
        )
        nodes.append({"paper": citing, "children": children})

    return nodes


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Fetch Semantic Scholar data for a seed paper.")
    parser.add_argument("--paper-id",    required=True, help="Seed paper ID or ARXIV:id")
    parser.add_argument("--api-key",     default=os.environ.get("S2_API_KEY"), help="Semantic Scholar API key (or set S2_API_KEY env var)")
    parser.add_argument("--max-depth",   type=int, default=2,  help="Recursion depth (default 2)")
    parser.add_argument("--max-children",type=int, default=5,  help="Papers per level (default 5)")
    parser.add_argument("--window-years",type=int, default=3,  help="Citation window years (default 3)")
    parser.add_argument("--output-dir",  default="./output",   help="Output directory (default ./output)")
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"  ResearchLineage — Phase 3 Fetch")
    print(f"  Seed paper: {args.paper_id}")
    print(f"  Max depth:  {args.max_depth} | Max children: {args.max_children}")
    print(f"  API key:    {'set' if args.api_key else 'NOT SET (rate limited to ~1 req/s)'}")
    print(f"{'='*60}\n")

    # 1. Fetch seed paper
    print("1. Fetching seed paper...")
    target = fetch_paper(args.paper_id, args.api_key)
    if not target:
        print("ERROR: Could not fetch seed paper. Check the paper ID and connectivity.")
        sys.exit(1)
    _register_paper(target)
    print(f"   ✓ {target['title']} ({target.get('year')})\n")

    # 2. Fetch ancestors (references)
    print(f"2. Fetching ancestors (max_depth={args.max_depth}, max_children={args.max_children})...")
    raw_references = fetch_ancestors(
        target["paperId"], target.get("year"),
        depth=0, max_depth=args.max_depth,
        max_children=args.max_children, api_key=args.api_key
    )
    print(f"   ✓ {len(raw_references)} top-level references\n")

    # 3. Fetch descendants (citations)
    _visited.clear()
    print(f"3. Fetching descendants (max_depth={args.max_depth}, window={args.window_years}yr)...")
    raw_citations = fetch_descendants(
        target["paperId"], target.get("year"),
        depth=0, max_depth=args.max_depth,
        max_children=args.max_children,
        window_years=args.window_years, api_key=args.api_key
    )
    print(f"   ✓ {len(raw_citations)} top-level citations\n")

    # 4. Write output files
    print("4. Writing output files...")

    def write_json(filename: str, data) -> None:
        path = out_dir / filename
        path.write_text(json.dumps(data, indent=2, default=str))
        print(f"   wrote {path} ({path.stat().st_size // 1024} KB)")

    write_json("raw_target.json",      target)
    write_json("raw_references.json",  raw_references)
    write_json("raw_citations.json",   raw_citations)
    write_json("raw_all_papers.json",  list(_all_papers.values()))
    write_json("raw_all_authors.json", list(_all_authors.values()))
    write_json("raw_all_edges.json",   _all_edges)

    # 5. Summary
    print(f"\n{'='*60}")
    print(f"  Summary")
    print(f"  Unique papers:  {len(_all_papers)}")
    print(f"  Unique authors: {len(_all_authors)}")
    print(f"  Citation edges: {len(_all_edges)}")
    print(f"  Output dir:     {out_dir.resolve()}")
    print(f"{'='*60}")
    print(f"\nNext step:")
    print(f"  python 02_transform_to_sql.py --input-dir {out_dir} --output-dir ./sql_output")


if __name__ == "__main__":
    main()
