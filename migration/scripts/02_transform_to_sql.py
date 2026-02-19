#!/usr/bin/env python3
"""
ResearchLineage — 02_transform_to_sql.py

Reads the JSON files produced by 01_fetch_and_analyze.py and generates
SQL UPSERT scripts for each table in FK-dependency order.

Output files (written to --output-dir):
  insert_authors.sql
  insert_papers.sql
  insert_paper_authors.sql
  insert_citations.sql
  insert_external_ids.sql
  insert_citation_paths.sql      (from raw_references + raw_citations tree)
  insert_all.sql                 (combined, ready to run)

Usage:
  python 02_transform_to_sql.py
  python 02_transform_to_sql.py --input-dir ./output --output-dir ./sql_output
  python 02_transform_to_sql.py --seed-id 204e3073870fae3d05bcbc2f6a8e263d9b72e776
"""

import argparse
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


# ---------------------------------------------------------------------------
# SQL helpers
# ---------------------------------------------------------------------------

def _q(val: Any) -> str:
    """Escape and quote a value for SQL."""
    if val is None:
        return "NULL"
    if isinstance(val, bool):
        return "TRUE" if val else "FALSE"
    if isinstance(val, (int, float)):
        return str(val)
    # Escape single quotes
    escaped = str(val).replace("'", "''")
    return f"'{escaped}'"


def _row(*values) -> str:
    return "(" + ", ".join(_q(v) for v in values) + ")"


def _header(title: str) -> str:
    bar = "=" * 70
    return f"-- {bar}\n-- {title}\n-- {bar}\n"


# ---------------------------------------------------------------------------
# Transform functions — one per table
# ---------------------------------------------------------------------------

def transform_authors(authors: list[dict]) -> tuple[str, int]:
    lines = [
        _header("authors"),
        "INSERT INTO authors (author_id, name)",
        "VALUES",
    ]
    rows = []
    for a in authors:
        if not a.get("authorId") or not a.get("name"):
            continue
        rows.append("  " + _row(a["authorId"], a["name"].strip()))

    if not rows:
        return "-- No authors to insert\n", 0

    lines.append(",\n".join(rows))
    lines.append("ON CONFLICT (author_id) DO UPDATE SET")
    lines.append("  name       = EXCLUDED.name,")
    lines.append("  updated_at = NOW();")
    return "\n".join(lines) + "\n", len(rows)


def transform_papers(papers: list[dict]) -> tuple[str, int]:
    lines = [
        _header("papers"),
        "INSERT INTO papers (",
        "  paper_id, title, abstract, venue, year, publication_date,",
        "  citation_count, influential_citation_count, is_open_access,",
        "  source_url, s3_pdf_key",
        ")",
        "VALUES",
    ]
    rows = []
    for p in papers:
        if not p.get("paperId"):
            continue
        venue = p.get("venue") or None  # normalise empty string → NULL
        rows.append("  " + _row(
            p["paperId"],
            p.get("title"),
            p.get("abstract"),
            venue if venue else None,
            p.get("year"),
            p.get("publicationDate"),
            p.get("citationCount") or 0,
            p.get("influentialCitationCount") or 0,
            bool(p.get("isOpenAccess")),
            p.get("url"),
            None,   # s3_pdf_key — set after PDF download
        ))

    if not rows:
        return "-- No papers to insert\n", 0

    lines.append(",\n".join(rows))
    lines.append("ON CONFLICT (paper_id) DO UPDATE SET")
    lines.append("  title                       = EXCLUDED.title,")
    lines.append("  abstract                    = EXCLUDED.abstract,")
    lines.append("  venue                       = EXCLUDED.venue,")
    lines.append("  year                        = EXCLUDED.year,")
    lines.append("  publication_date            = EXCLUDED.publication_date,")
    lines.append("  citation_count              = EXCLUDED.citation_count,")
    lines.append("  influential_citation_count  = EXCLUDED.influential_citation_count,")
    lines.append("  is_open_access              = EXCLUDED.is_open_access,")
    lines.append("  source_url                  = EXCLUDED.source_url,")
    lines.append("  updated_at                  = NOW();")
    return "\n".join(lines) + "\n", len(rows)


def transform_paper_authors(papers: list[dict]) -> tuple[str, int]:
    lines = [
        _header("paper_authors"),
        "INSERT INTO paper_authors (paper_id, author_id, author_order)",
        "VALUES",
    ]
    rows = []
    for p in papers:
        pid = p.get("paperId")
        if not pid:
            continue
        for idx, author in enumerate(p.get("authors") or []):
            if not author.get("authorId"):
                continue
            rows.append("  " + _row(pid, author["authorId"], idx + 1))

    if not rows:
        return "-- No paper_authors rows to insert\n", 0

    lines.append(",\n".join(rows))
    lines.append("ON CONFLICT (paper_id, author_id) DO UPDATE SET")
    lines.append("  author_order = EXCLUDED.author_order,")
    lines.append("  updated_at   = NOW();")
    return "\n".join(lines) + "\n", len(rows)


def transform_citations(edges: list[dict]) -> tuple[str, int]:
    lines = [
        _header("citations"),
        "INSERT INTO citations (citing_paper_id, cited_paper_id, citation_context)",
        "VALUES",
    ]
    rows = []
    seen = set()
    for e in edges:
        cng = e.get("citing_paper_id")
        ced = e.get("cited_paper_id")
        if not cng or not ced or cng == ced:
            continue
        key = (cng, ced)
        if key in seen:
            continue
        seen.add(key)

        intents = e.get("intents") or []
        context = ", ".join(intents) if intents else None
        rows.append("  " + _row(cng, ced, context))

    if not rows:
        return "-- No citations to insert\n", 0

    lines.append(",\n".join(rows))
    lines.append("ON CONFLICT (citing_paper_id, cited_paper_id) DO UPDATE SET")
    lines.append("  citation_context = EXCLUDED.citation_context,")
    lines.append("  updated_at       = NOW();")
    return "\n".join(lines) + "\n", len(rows)


def transform_external_ids(papers: list[dict]) -> tuple[str, int]:
    # Map Semantic Scholar externalIds key → DB source name
    SOURCE_MAP = {
        "ArXiv":    "arxiv",
        "DBLP":     "dblp",
        "CorpusId": "corpus",
        "DOI":      "doi",
        "PubMed":   "pubmed",
        "MAG":      "mag",
        "ACL":      "acl",
    }

    lines = [
        _header("paper_external_ids"),
        "INSERT INTO paper_external_ids (paper_id, source, external_id)",
        "VALUES",
    ]
    rows = []
    seen = set()
    for p in papers:
        pid = p.get("paperId")
        if not pid:
            continue
        for api_key, db_source in SOURCE_MAP.items():
            val = (p.get("externalIds") or {}).get(api_key)
            if val is None:
                continue
            key = (pid, db_source)
            if key in seen:
                continue
            seen.add(key)
            rows.append("  " + _row(pid, db_source, str(val)))

    if not rows:
        return "-- No external IDs to insert\n", 0

    lines.append(",\n".join(rows))
    lines.append("ON CONFLICT (paper_id, source) DO UPDATE SET")
    lines.append("  external_id = EXCLUDED.external_id,")
    lines.append("  updated_at  = NOW();")
    return "\n".join(lines) + "\n", len(rows)


def transform_citation_paths(
    seed_id: str,
    references_tree: list[dict],
    citations_tree: list[dict],
    max_depth: int,
) -> tuple[str, int]:
    """
    Generate citation_paths + citation_path_nodes from the tree structures.
    One path for ancestors (references), one for descendants (citations).
    """

    def flatten_ancestors(nodes: list, seed: str, depth=1, pos_counter=None) -> list[dict]:
        if pos_counter is None:
            pos_counter = [2]  # seed is position 1
        result = []
        for node in nodes:
            paper = node.get("paper", {})
            pid = paper.get("paperId")
            if not pid:
                continue
            result.append({
                "paper_id":        pid,
                "depth":           depth,
                "position":        pos_counter[0],
                "is_influential":  False,
                "influence_reason": None,
            })
            pos_counter[0] += 1
            result.extend(flatten_ancestors(node.get("ancestors", []), seed, depth + 1, pos_counter))
        return result

    def flatten_descendants(nodes: list, seed: str, depth=1, pos_counter=None) -> list[dict]:
        if pos_counter is None:
            pos_counter = [2]
        result = []
        for node in nodes:
            paper = node.get("paper", {})
            pid = paper.get("paperId")
            if not pid:
                continue
            result.append({
                "paper_id":        pid,
                "depth":           depth,
                "position":        pos_counter[0],
                "is_influential":  False,
                "influence_reason": None,
            })
            pos_counter[0] += 1
            result.extend(flatten_descendants(node.get("children", []), seed, depth + 1, pos_counter))
        return result

    path_ref_id  = str(uuid.uuid4())
    path_cite_id = str(uuid.uuid4())
    now_str      = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S+00")

    ref_nodes   = flatten_ancestors(references_tree, seed_id)
    cite_nodes  = flatten_descendants(citations_tree, seed_id)

    sql_parts = [_header("citation_paths + citation_path_nodes")]

    # --- citation_paths ---
    sql_parts.append("INSERT INTO citation_paths (path_id, seed_paper_id, max_depth, path_score)")
    sql_parts.append("VALUES")
    sql_parts.append(f"  ({_q(path_ref_id)},  {_q(seed_id)}, {_q(max_depth)}, NULL),")
    sql_parts.append(f"  ({_q(path_cite_id)}, {_q(seed_id)}, {_q(max_depth)}, NULL)")
    sql_parts.append("ON CONFLICT (path_id) DO NOTHING;\n")

    def node_rows(path_id: str, seed_pid: str, nodes: list[dict]) -> list[str]:
        rows = []
        # Seed paper is always position 1, depth 0
        rows.append("  " + _row(path_id, seed_pid, 0, 1, True, "Seed paper"))
        for n in nodes:
            rows.append("  " + _row(
                path_id, n["paper_id"], n["depth"], n["position"],
                n["is_influential"], n["influence_reason"]
            ))
        return rows

    all_node_rows = (
        node_rows(path_ref_id,  seed_id, ref_nodes) +
        node_rows(path_cite_id, seed_id, cite_nodes)
    )

    if all_node_rows:
        sql_parts.append("INSERT INTO citation_path_nodes")
        sql_parts.append("  (path_id, paper_id, depth, position, is_influential, influence_reason)")
        sql_parts.append("VALUES")
        sql_parts.append(",\n".join(all_node_rows))
        sql_parts.append("ON CONFLICT (path_id, paper_id) DO UPDATE SET")
        sql_parts.append("  depth            = EXCLUDED.depth,")
        sql_parts.append("  position         = EXCLUDED.position,")
        sql_parts.append("  is_influential   = EXCLUDED.is_influential,")
        sql_parts.append("  influence_reason = EXCLUDED.influence_reason,")
        sql_parts.append("  updated_at       = NOW();")

    total = 2 + len(all_node_rows)
    return "\n".join(sql_parts) + "\n", total


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Transform fetched JSON → SQL INSERT scripts.")
    parser.add_argument("--input-dir",  default="./output",     help="Directory with raw_*.json files")
    parser.add_argument("--output-dir", default="./sql_output", help="Directory to write SQL files")
    parser.add_argument("--seed-id",    default=None,           help="Override seed paper ID for citation_paths")
    parser.add_argument("--max-depth",  type=int, default=2,    help="max_depth value stored in citation_paths")
    args = parser.parse_args()

    in_dir  = Path(args.input_dir)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    def load(filename: str) -> Any:
        path = in_dir / filename
        if not path.exists():
            print(f"  ⚠  {filename} not found — skipping.")
            return None
        return json.loads(path.read_text())

    print(f"\n{'='*60}")
    print(f"  ResearchLineage — Phase 3 Transform")
    print(f"  Input:  {in_dir.resolve()}")
    print(f"  Output: {out_dir.resolve()}")
    print(f"{'='*60}\n")

    all_papers  = load("raw_all_papers.json")  or []
    all_authors = load("raw_all_authors.json") or []
    all_edges   = load("raw_all_edges.json")   or []
    references  = load("raw_references.json")  or []
    citations   = load("raw_citations.json")   or []
    target      = load("raw_target.json")      or {}

    seed_id = args.seed_id or target.get("paperId")
    if not seed_id:
        print("ERROR: Cannot determine seed paper ID. Pass --seed-id or ensure raw_target.json exists.")
        import sys; sys.exit(1)

    results: dict[str, tuple[str, int]] = {}

    print("Transforming tables in FK dependency order...")

    results["insert_authors.sql"]      = transform_authors(all_authors)
    results["insert_papers.sql"]       = transform_papers(all_papers)
    results["insert_paper_authors.sql"]= transform_paper_authors(all_papers)
    results["insert_citations.sql"]    = transform_citations(all_edges)
    results["insert_external_ids.sql"] = transform_external_ids(all_papers)
    results["insert_citation_paths.sql"] = transform_citation_paths(
        seed_id, references, citations, args.max_depth
    )

    # Write individual files
    total_rows = 0
    for filename, (sql, count) in results.items():
        path = out_dir / filename
        path.write_text(sql)
        print(f"  ✓ {filename:<35} ({count} rows)")
        total_rows += count

    # Write combined insert_all.sql
    combined_header = f"""-- =============================================================================
-- ResearchLineage — insert_all.sql (combined)
-- Generated: {datetime.now(timezone.utc).isoformat()}
-- Seed paper: {seed_id}
-- REVIEW THIS FILE before running against your database.
-- =============================================================================

BEGIN;

"""
    order = [
        "insert_authors.sql",
        "insert_papers.sql",
        "insert_paper_authors.sql",
        "insert_citations.sql",
        "insert_external_ids.sql",
        "insert_citation_paths.sql",
    ]
    combined = combined_header
    for filename in order:
        sql, _ = results[filename]
        combined += f"\n-- ── {filename} ───────────────────────────────────────\n"
        combined += sql + "\n"

    combined += "\nCOMMIT;\n"
    all_path = out_dir / "insert_all.sql"
    all_path.write_text(combined)

    print(f"\n  ✓ insert_all.sql (combined — {total_rows} total rows)")
    print(f"\n{'='*60}")
    print(f"  Total rows generated: {total_rows}")
    print(f"{'='*60}")
    print(f"\nNext step — review then run:")
    print(f"  psql \"$DB_URL\" -f {out_dir.resolve()}/insert_all.sql")


if __name__ == "__main__":
    main()
