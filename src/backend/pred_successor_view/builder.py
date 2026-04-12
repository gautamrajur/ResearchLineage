"""
pred_successor_view/builder.py
-------------------------------
Builds a bidirectional research lineage tree:
    ancestors   — papers this paper cited (going back in time)
    descendants — papers that cited this paper (going forward in time)

Uses common.SemanticScholarClient for all API calls and
common.Cache for PostgreSQL-backed caching.
"""

import time
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from ..common.s2_client import SemanticScholarClient
from ..common.cache import Cache
from ..common.config import DATABASE_URL, logger as _base_logger

# Module logger (inherits handlers configured by setup_logging)
_logger = logging.getLogger("pred_successor_view")


def setup_logging(log_file: str = "pred_successor_view.log",
                  level: int = logging.DEBUG) -> None:
    """Configure console + file logging. Safe to call multiple times."""
    if _logger.handlers:
        return

    fmt = logging.Formatter(
        "%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%H:%M:%S",
    )

    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)

    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)

    _logger.setLevel(level)
    _logger.addHandler(ch)
    _logger.addHandler(fh)
    _logger.propagate = False


def _ms(start: float) -> str:
    return f"{(time.perf_counter() - start) * 1000:.0f} ms"


class PredSuccessorView:
    """
    Build research lineage trees using Semantic Scholar with PostgreSQL caching.

    Usage:
        view = PredSuccessorView()
        tree = view.build_tree("ARXIV:1706.03762", max_children=5, max_depth=2)
    """

    def __init__(self, api_key: Optional[str] = None, dsn: str = DATABASE_URL):
        self.s2     = SemanticScholarClient(api_key=api_key)
        self.cache  = Cache(dsn)
        _logger.info("PredSuccessorView initialised")

    # ------------------------------------------------------------------
    # Ancestors
    # ------------------------------------------------------------------

    def _build_ancestors(self, paper_id: str, paper_year,
                         current_depth: int = 0, max_depth: int = 2,
                         max_children: int = 3,
                         _nodes: Optional[List] = None) -> Tuple[List, List]:
        if _nodes is None:
            _nodes = []
        if current_depth >= max_depth:
            return [], _nodes

        indent = "  " * current_depth
        label  = f"ANCESTORS depth={current_depth} paper={paper_id}"
        t0     = time.perf_counter()

        if self.cache.has_references(paper_id):
            _logger.info("%s[CACHE HIT]  %s", indent, label)
            top_refs = self.cache.get_references(paper_id, max_children)
            _logger.info("%s  source=CACHE  refs=%d  elapsed=%s",
                         indent, len(top_refs), _ms(t0))
        else:
            _logger.info("%s[API CALL]   %s", indent, label)
            raw_refs = self.s2.get_references(paper_id, full_fields=False, limit=100)

            if not raw_refs:
                _logger.warning("%s  API returned empty — logging empty fetch", indent)
                self.cache.save_references(paper_id, [])
                return [], _nodes

            self.cache.save_references(paper_id, raw_refs)

            methodology = [
                r for r in raw_refs
                if "citedPaper" in r
                and "methodology" in (r.get("intents") or [])
            ]
            if len(methodology) < max_children:
                seen = {r["citedPaper"]["paperId"] for r in methodology if r.get("citedPaper")}
                influential = [
                    r for r in raw_refs
                    if r.get("isInfluential") and "citedPaper" in r
                    and r["citedPaper"].get("paperId") not in seen
                ]
                all_valid = methodology + influential
            else:
                all_valid = methodology

            if not all_valid:
                _logger.info("%s  no valid ancestors after filtering", indent)
                return [], _nodes

            all_valid.sort(
                key=lambda x: (
                    -(x.get("citedPaper", {}).get("citationCount") or 0),
                    x.get("citedPaper", {}).get("paperId") or "",
                )
            )
            top_refs = [
                {
                    "isInfluential": r.get("isInfluential", False),
                    "intents":       r.get("intents") or [],
                    "citedPaper":    r["citedPaper"],
                }
                for r in all_valid[:max_children]
            ]
            _logger.info("%s  selected top %d  elapsed=%s",
                         indent, len(top_refs), _ms(t0))

        ancestors = []
        for ref in top_refs:
            cited = ref["citedPaper"]
            if not cited.get("paperId"):
                continue
            _nodes.append({
                "paper_id": cited["paperId"],
                "node_type": "ancestor",
                "depth": current_depth + 1,
                "parent_paper_id": paper_id,
            })
            child_ancestors, _nodes = self._build_ancestors(
                cited["paperId"], cited.get("year"),
                current_depth + 1, max_depth, max_children, _nodes,
            )
            ancestors.append({"paper": cited, "ancestors": child_ancestors})

        _logger.info("%sANCESTORS DONE  depth=%d  count=%d  elapsed=%s",
                     indent, current_depth, len(ancestors), _ms(t0))
        return ancestors, _nodes

    # ------------------------------------------------------------------
    # Descendants
    # ------------------------------------------------------------------

    def _build_descendants(self, paper_id: str, paper_year,
                           current_depth: int = 0, max_depth: int = 2,
                           window_years: int = 3, max_children: int = 3,
                           _nodes: Optional[List] = None) -> Tuple[List, List]:
        if _nodes is None:
            _nodes = []
        if current_depth >= max_depth:
            return [], _nodes

        indent     = "  " * current_depth
        start_year = paper_year + 1
        end_year   = paper_year + window_years
        label      = (f"DESCENDANTS depth={current_depth} paper={paper_id}"
                      f" window={start_year}-{end_year}")
        t0         = time.perf_counter()

        if self.cache.has_citations(paper_id, start_year, end_year):
            _logger.info("%s[CACHE HIT]  %s", indent, label)
            children_limit = max_children if current_depth == 0 else 3
            cached = self.cache.get_citations(paper_id, start_year, end_year, children_limit)
            top_papers = [c["citingPaper"] for c in cached]
            _logger.info("%s  source=CACHE  cites=%d  elapsed=%s",
                         indent, len(top_papers), _ms(t0))
        else:
            _logger.info("%s[API CALL]   %s", indent, label)
            max_papers = 10000 if current_depth == 0 else 5000
            all_cites  = self.s2.get_citations_paginated(
                paper_id, start_year, end_year, max_papers
            )

            if not all_cites:
                _logger.info("%s  no citations — logging empty fetch", indent)
                self.cache.save_citations(paper_id, [], start_year, end_year)
                return [], _nodes

            self.cache.save_citations(paper_id, all_cites, start_year, end_year)

            methodology = [
                c for c in all_cites
                if c.get("citingPaper")
                and "methodology" in (c.get("intents") or [])
            ]
            if len(methodology) < max_children:
                seen = {
                    c["citingPaper"]["paperId"]
                    for c in methodology if c.get("citingPaper")
                }
                influential = [
                    c for c in all_cites
                    if c.get("citingPaper")
                    and c.get("isInfluential")
                    and c["citingPaper"].get("paperId") not in seen
                ]
                all_valid = methodology + influential
            else:
                all_valid = methodology

            if not all_valid:
                _logger.info("%s  no valid descendants after filtering", indent)
                return [], _nodes

            papers = [c["citingPaper"] for c in all_valid]
            papers.sort(
                key=lambda x: (-(x.get("citationCount") or 0), x.get("paperId") or "")
            )
            children_limit = max_children if current_depth == 0 else 3
            top_papers = papers[:children_limit]
            _logger.info("%s  selected top %d  elapsed=%s",
                         indent, len(top_papers), _ms(t0))

        descendants = []
        for p in top_papers:
            if not p.get("paperId"):
                continue
            _nodes.append({
                "paper_id": p["paperId"],
                "node_type": "descendant",
                "depth": current_depth + 1,
                "parent_paper_id": paper_id,
            })
            child_desc, _nodes = self._build_descendants(
                p["paperId"], p.get("year") or paper_year,
                current_depth + 1, max_depth, window_years, max_children, _nodes,
            )
            descendants.append({"paper": p, "children": child_desc})

        _logger.info("%sDESCENDANTS DONE  depth=%d  count=%d  elapsed=%s",
                     indent, current_depth, len(descendants), _ms(t0))
        return descendants, _nodes

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def build_tree(self, paper_id: str, max_children: int = 5,
                   max_depth: int = 2, window_years: int = 3) -> Optional[Dict]:
        """
        Build the complete pred/successor tree for a paper.

        Returns:
            {target, ancestors, descendants} or None on failure.
        """
        t_total = time.perf_counter()
        _logger.info("=" * 70)
        _logger.info("BUILD TREE START  paper=%s  children=%d  depth=%d  window=%d",
                     paper_id, max_children, max_depth, window_years)
        _logger.info("=" * 70)

        tree: Dict = {"ancestors": [], "target": None, "descendants": []}

        # Step 1 — target paper
        _logger.info("STEP 1 — target paper")
        t1 = time.perf_counter()
        cached = self.cache.get_paper(paper_id)
        if cached:
            target = cached
            _logger.info("  [CACHE HIT]  title=%s  elapsed=%s",
                         target.get("title", "")[:60], _ms(t1))
        else:
            target = self.s2.get_paper(paper_id, full_fields=False)
            if not target:
                _logger.error("  STEP 1 FAILED — could not fetch target paper")
                return None
            self.cache.save_paper(target, lookup_id=paper_id)
            _logger.info("  [API]  title=%s  year=%s  elapsed=%s",
                         target.get("title", "")[:60], target.get("year"), _ms(t1))

        _KEEP = {"paperId", "externalIds", "title", "year", "citationCount", "influentialCitationCount"}
        tree["target"] = {k: v for k, v in target.items() if k in _KEEP}

        tree_nodes = [{
            "paper_id":        target["paperId"],
            "node_type":       "target",
            "depth":           0,
            "parent_paper_id": None,
        }]

        # Step 2 — ancestors
        _logger.info("STEP 2 — ancestors")
        t2 = time.perf_counter()
        ancestors, anc_nodes = self._build_ancestors(
            paper_id, target.get("year"),
            current_depth=0, max_depth=max_depth, max_children=3, _nodes=[],
        )
        tree["ancestors"] = ancestors
        tree_nodes.extend(anc_nodes)
        _logger.info("STEP 2 DONE  nodes=%d  elapsed=%s", len(anc_nodes), _ms(t2))

        # Step 3 — descendants
        _logger.info("STEP 3 — descendants")
        t3 = time.perf_counter()
        if target.get("year"):
            descendants, desc_nodes = self._build_descendants(
                paper_id, target["year"],
                current_depth=0, max_depth=max_depth,
                window_years=window_years, max_children=max_children, _nodes=[],
            )
            tree["descendants"] = descendants
            tree_nodes.extend(desc_nodes)
            _logger.info("STEP 3 DONE  nodes=%d  elapsed=%s", len(desc_nodes), _ms(t3))
        else:
            _logger.warning("STEP 3 SKIPPED — target has no year")

        # Step 4 — persist tree run
        ts      = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        safe_id = paper_id.replace(":", "_").replace("/", "_")
        tree_id = f"{safe_id}_{ts}"
        self.cache.save_tree(tree_id, paper_id, max_depth, max_children, window_years)
        self.cache.save_tree_nodes(tree_id, tree_nodes)

        _logger.info("=" * 70)
        _logger.info("BUILD TREE COMPLETE  paper=%s  nodes=%d  elapsed=%s",
                     paper_id, len(tree_nodes), _ms(t_total))
        _logger.info("=" * 70)

        return tree
