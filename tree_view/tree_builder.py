import requests
import time
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from .cache import Cache, DATABASE_URL

# ---------------------------------------------------------------------------
# Module-level logger — callers configure handlers (see setup_logging below)
# ---------------------------------------------------------------------------
logger = logging.getLogger("tree_builder")


def setup_logging(log_file: str = "tree_builder.log", level: int = logging.DEBUG) -> None:
    """
    Configure console + file logging for tree_builder.
    Call once before using TreeView.  Safe to call multiple times.
    """
    if logger.handlers:
        return  # already configured

    fmt = logging.Formatter(
        "%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%H:%M:%S",
    )

    # Console — INFO and above
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)

    # File — DEBUG and above (full API responses)
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)

    logger.setLevel(level)
    logger.addHandler(ch)
    logger.addHandler(fh)
    logger.propagate = False


def _ms(start: float) -> str:
    """Return elapsed milliseconds as a readable string."""
    return f"{(time.perf_counter() - start) * 1000:.0f} ms"


class TreeView:
    """Build research lineage trees using Semantic Scholar API with PostgreSQL caching."""

    def __init__(self, api_key: Optional[str] = None, dsn: str = DATABASE_URL):
        self.base_url = "https://api.semanticscholar.org/graph/v1"
        self.api_key = api_key
        self.cache = Cache(dsn)
        logger.info("TreeView initialised  |  db=%s", dsn)

    # ------------------------------------------------------------------
    # Core HTTP helper
    # ------------------------------------------------------------------

    def api_call(self, endpoint: str, params: Optional[Dict] = None,
                 max_retries: int = 30) -> Optional[Dict]:
        """Make a single API call with rate-limit retry.  Logs every request/response."""
        endpoint = endpoint.lstrip('/')
        url = f"{self.base_url}/{endpoint}"
        headers = {"x-api-key": self.api_key} if self.api_key else {}

        logger.info("  -> API REQUEST  %s  params=%s", endpoint, params)
        t0 = time.perf_counter()

        for attempt in range(max_retries):
            try:
                response = requests.get(url, params=params, headers=headers, timeout=30)

                if response.status_code == 200:
                    data = response.json()
                    elapsed = _ms(t0)

                    # Count items in paginated responses
                    item_count = len(data.get("data", [])) if isinstance(data.get("data"), list) else "n/a"
                    logger.info("  <- API RESPONSE 200  items=%s  elapsed=%s", item_count, elapsed)
                    logger.debug("  <- FULL RESPONSE  %s", data)

                    time.sleep(1.2)
                    return data

                elif response.status_code == 429:
                    wait_time = 2
                    logger.warning("  <- 429 RATE LIMITED  attempt=%d/%d  waiting=%ds",
                                   attempt + 1, max_retries, wait_time)
                    time.sleep(wait_time)
                    continue

                else:
                    logger.error("  <- API ERROR %d  body=%s", response.status_code,
                                 response.text[:300])
                    return None

            except Exception as exc:
                logger.error("  <- REQUEST EXCEPTION  %s", exc)
                return None

        logger.error("  <- GAVE UP after %d retries  endpoint=%s", max_retries, endpoint)
        return None

    # ------------------------------------------------------------------
    # Ancestors
    # ------------------------------------------------------------------

    def build_recursive_ancestors(self, paper_id: str, paper_year, current_depth: int = 0,
                                  max_depth: int = 2, max_children: int = 3,
                                  _nodes: Optional[List] = None) -> Tuple[List, List]:
        """Recursively build ancestor tree (papers this paper cited)."""
        if _nodes is None:
            _nodes = []

        if current_depth >= max_depth:
            return [], _nodes

        indent = "  " * current_depth
        step_label = f"ANCESTORS depth={current_depth}  paper={paper_id}"
        t0 = time.perf_counter()

        # ── Cache check ──────────────────────────────────────────────
        if self.cache.has_references(paper_id):
            logger.info("%s[CACHE HIT]  %s  — skipping API call", indent, step_label)
            top_refs = self.cache.get_references(paper_id, max_children)

            logger.info("%s  source=CACHE  refs_returned=%d  elapsed=%s",
                        indent, len(top_refs), _ms(t0))
            for i, ref in enumerate(top_refs, 1):
                p = ref['citedPaper']
                logger.info("%s    %d. [%s] %s (%s)  citations=%s",
                            indent, i, p.get('paperId', '?')[:8],
                            p.get('title', '')[:55], p.get('year', 'N/A'),
                            p.get('citationCount', '?'))
        else:
            # ── API call ─────────────────────────────────────────────
            logger.info("%s[API CALL]   %s  — no cache row found", indent, step_label)
            refs_params = {
                'fields': 'citedPaper.paperId,citedPaper.title,citedPaper.year,'
                          'citedPaper.citationCount,isInfluential,intents',
                'limit': 100
            }
            refs_response = self.api_call(f"paper/{paper_id}/references", refs_params)

            if refs_response is None:
                logger.warning("%s  API returned None — logging empty fetch", indent)
                self.cache.save_references(paper_id, [])
                return [], _nodes

            if 'data' not in refs_response or refs_response['data'] is None:
                logger.warning("%s  API response has no 'data' key — logging empty fetch", indent)
                self.cache.save_references(paper_id, [])
                return [], _nodes

            raw_refs = refs_response['data']
            logger.info("%s  raw_refs_from_api=%d", indent, len(raw_refs))

            # Save ALL refs to cache before any filtering
            self.cache.save_references(paper_id, raw_refs)
            logger.info("%s  saved %d refs to cache", indent, len(raw_refs))

            # Filter by methodology intent
            methodology_refs = [
                ref for ref in raw_refs
                if 'citedPaper' in ref
                and 'intents' in ref and ref['intents']
                and 'methodology' in ref['intents']
            ]
            logger.info("%s  methodology_refs=%d / %d", indent, len(methodology_refs), len(raw_refs))

            # Fallback to influential if not enough methodology refs
            if len(methodology_refs) < max_children:
                logger.info("%s  methodology_refs < max_children(%d) — adding influential",
                            indent, max_children)
                influential_refs = [
                    ref for ref in raw_refs
                    if ref.get('isInfluential', False) and 'citedPaper' in ref
                ]
                all_valid = methodology_refs + [
                    r for r in influential_refs if r not in methodology_refs
                ]
                logger.info("%s  combined (methodology+influential)=%d", indent, len(all_valid))
            else:
                all_valid = methodology_refs

            if not all_valid:
                logger.info("%s  no valid ancestors found after filtering", indent)
                return [], _nodes

            all_valid.sort(
                key=lambda x: (-(x.get('citedPaper', {}).get('citationCount') or 0),
                               x.get('citedPaper', {}).get('paperId') or '')
            )
            top_refs = all_valid[:max_children]

            logger.info("%s  selected top %d by citation_count  elapsed=%s",
                        indent, len(top_refs), _ms(t0))
            for i, ref in enumerate(top_refs, 1):
                p = ref['citedPaper']
                logger.info("%s    %d. [%s] %s (%s)  citations=%s",
                            indent, i, p.get('paperId', '?')[:8],
                            p.get('title', '')[:55], p.get('year', 'N/A'),
                            p.get('citationCount', '?'))

        # ── Recurse ───────────────────────────────────────────────────
        ancestors = []
        for ref in top_refs:
            cited_paper = ref['citedPaper']
            if not cited_paper.get('paperId'):
                continue

            _nodes.append({
                'paper_id': cited_paper['paperId'],
                'node_type': 'ancestor',
                'depth': current_depth + 1,
                'parent_paper_id': paper_id,
            })

            child_ancestors, _nodes = self.build_recursive_ancestors(
                cited_paper['paperId'],
                cited_paper.get('year'),
                current_depth + 1,
                max_depth,
                max_children,
                _nodes=_nodes,
            )
            ancestors.append({'paper': cited_paper, 'ancestors': child_ancestors})

        logger.info("%sTOTAL step elapsed=%s  depth=%d  ancestors_built=%d",
                    indent, _ms(t0), current_depth, len(ancestors))
        return ancestors, _nodes

    # ------------------------------------------------------------------
    # Descendants
    # ------------------------------------------------------------------

    def build_recursive_descendants(self, paper_id: str, paper_year, current_depth: int = 0,
                                    max_depth: int = 2, window_years: int = 3,
                                    max_children: int = 3,
                                    _nodes: Optional[List] = None) -> Tuple[List, List]:
        """Recursively build descendant tree using time windows."""
        if _nodes is None:
            _nodes = []

        if current_depth >= max_depth:
            return [], _nodes

        indent = "  " * current_depth
        start_year = paper_year + 1
        end_year = paper_year + window_years
        step_label = (f"DESCENDANTS depth={current_depth}  paper={paper_id}"
                      f"  window={start_year}-{end_year}")
        t0 = time.perf_counter()

        # ── Cache check ──────────────────────────────────────────────
        if self.cache.has_citations(paper_id, start_year, end_year):
            logger.info("%s[CACHE HIT]  %s  — skipping API call", indent, step_label)
            children_limit = max_children if current_depth == 0 else 3
            cached_cites = self.cache.get_citations(paper_id, start_year, end_year, children_limit)
            top_cites_papers = [c['citingPaper'] for c in cached_cites]

            logger.info("%s  source=CACHE  cites_returned=%d  elapsed=%s",
                        indent, len(top_cites_papers), _ms(t0))
            for i, p in enumerate(top_cites_papers, 1):
                logger.info("%s    %d. [%s] %s (%s)  citations=%s",
                            indent, i, p.get('paperId', '?')[:8],
                            p.get('title', '')[:55], p.get('year', 'N/A'),
                            p.get('citationCount', '?'))
        else:
            # ── API call (paginated) ──────────────────────────────────
            max_papers = 10000 if current_depth == 0 else 5000
            logger.info("%s[API CALL]   %s  — no cache row found  max_papers=%d",
                        indent, step_label, max_papers)

            all_cites = []
            offset = 0
            limit = 1000
            page_num = 0

            while offset < max_papers and offset < 9000:
                page_num += 1
                t_page = time.perf_counter()
                cites_params = {
                    'fields': 'citingPaper.paperId,citingPaper.title,citingPaper.year,'
                              'citingPaper.citationCount,intents,isInfluential',
                    'limit': limit,
                    'offset': offset,
                    'publicationDateOrYear': f'{start_year}:{end_year}'
                }

                cites_response = self.api_call(
                    f"paper/{paper_id}/citations", cites_params
                )

                if cites_response is None:
                    logger.warning("%s  page=%d  API call failed — stopping pagination",
                                   indent, page_num)
                    break

                if 'data' not in cites_response:
                    logger.warning("%s  page=%d  no 'data' key in response", indent, page_num)
                    break

                batch = cites_response['data']
                all_cites.extend(batch)
                logger.info("%s  page=%d  offset=%d  batch_size=%d  running_total=%d  page_elapsed=%s",
                            indent, page_num, offset, len(batch), len(all_cites), _ms(t_page))

                if len(batch) < limit:
                    logger.info("%s  page=%d  batch < limit — pagination complete", indent, page_num)
                    break

                offset += limit
                if offset < max_papers and offset < 9000:
                    time.sleep(2)

            logger.info("%s  pagination done  total_fetched=%d  elapsed=%s",
                        indent, len(all_cites), _ms(t0))

            if not all_cites:
                logger.info("%s  no citations fetched — logging empty fetch", indent)
                self.cache.save_citations(paper_id, [], start_year, end_year)
                return [], _nodes

            # Save ALL citation rows to cache before filtering
            self.cache.save_citations(paper_id, all_cites, start_year, end_year)
            logger.info("%s  saved %d citation rows to cache", indent, len(all_cites))

            # Filter by methodology intent
            methodology_cites = [
                cite for cite in all_cites
                if 'citingPaper' in cite and cite['citingPaper'] is not None
                and 'intents' in cite and cite['intents']
                and 'methodology' in cite['intents']
            ]
            logger.info("%s  methodology_cites=%d / %d", indent,
                        len(methodology_cites), len(all_cites))

            # Fallback to influential
            if len(methodology_cites) < max_children:
                logger.info("%s  methodology_cites < max_children(%d) — adding influential",
                            indent, max_children)
                influential_cites = [
                    cite for cite in all_cites
                    if 'citingPaper' in cite and cite['citingPaper'] is not None
                    and cite.get('isInfluential', False)
                ]
                all_valid = methodology_cites + [
                    c for c in influential_cites if c not in methodology_cites
                ]
                logger.info("%s  combined=%d", indent, len(all_valid))
            else:
                all_valid = methodology_cites

            if not all_valid:
                logger.info("%s  no valid descendants after filtering", indent)
                return [], _nodes

            valid_papers = [cite['citingPaper'] for cite in all_valid]
            valid_papers.sort(key=lambda x: (-(x.get('citationCount') or 0), x.get('paperId') or ''))

            children_limit = max_children if current_depth == 0 else 3
            top_cites_papers = valid_papers[:children_limit]

            logger.info("%s  selected top %d by citation_count  elapsed=%s",
                        indent, len(top_cites_papers), _ms(t0))
            for i, p in enumerate(top_cites_papers, 1):
                logger.info("%s    %d. [%s] %s (%s)  citations=%s",
                            indent, i, p.get('paperId', '?')[:8],
                            p.get('title', '')[:55], p.get('year', 'N/A'),
                            p.get('citationCount', '?'))

        # ── Recurse ───────────────────────────────────────────────────
        descendants = []
        for cite in top_cites_papers:
            if not cite.get('paperId'):
                continue

            _nodes.append({
                'paper_id': cite['paperId'],
                'node_type': 'descendant',
                'depth': current_depth + 1,
                'parent_paper_id': paper_id,
            })

            child_descendants, _nodes = self.build_recursive_descendants(
                cite['paperId'],
                cite.get('year') or paper_year,
                current_depth + 1,
                max_depth,
                window_years,
                max_children,
                _nodes=_nodes,
            )
            descendants.append({'paper': cite, 'children': child_descendants})

        logger.info("%sTOTAL step elapsed=%s  depth=%d  descendants_built=%d",
                    indent, _ms(t0), current_depth, len(descendants))
        return descendants, _nodes

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def build_tree(self, paper_id: str, max_children: int = 5,
                   max_depth: int = 2, window_years: int = 3) -> Optional[Dict]:
        """
        Build complete tree view for a paper, using SQLite cache where available.

        Args:
            paper_id:     Semantic Scholar paper ID  (e.g. "ARXIV:1706.03762")
            max_children: Max children per level     (default 5)
            max_depth:    Recursion depth            (default 2)
            window_years: Years window for descendants (default 3)

        Returns:
            dict: {target, ancestors, descendants} or None on failure
        """
        t_total = time.perf_counter()
        logger.info("=" * 70)
        logger.info("BUILD TREE START  paper=%s  max_children=%d  max_depth=%d  window=%d",
                    paper_id, max_children, max_depth, window_years)
        logger.info("=" * 70)

        tree: Dict = {'ancestors': [], 'target': None, 'descendants': []}

        # ── Step 1: Target paper ─────────────────────────────────────
        logger.info("STEP 1 — target paper")
        t1 = time.perf_counter()
        cached_target = self.cache.get_paper(paper_id)

        if cached_target:
            logger.info("  [CACHE HIT]  source=DB  title=%s  year=%s  elapsed=%s",
                        cached_target.get('title', '')[:60], cached_target.get('year'), _ms(t1))
            target = cached_target
        else:
            logger.info("  [API CALL]   no cached row — calling Semantic Scholar")
            target = self.api_call(
                f"paper/{paper_id}",
                {'fields': 'paperId,title,year,citationCount,influentialCitationCount'}
            )
            if not target:
                logger.error("  STEP 1 FAILED — could not fetch target paper")
                return None

            self.cache.save_paper(target, lookup_id=paper_id)
            logger.info("  source=API  title=%s  year=%s  citations=%s  elapsed=%s",
                        target.get('title', '')[:60], target.get('year'),
                        target.get('citationCount'), _ms(t1))

        _TREE_PAPER_FIELDS = {'paperId', 'title', 'year', 'citationCount', 'influentialCitationCount'}
        tree['target'] = {k: v for k, v in target.items() if k in _TREE_PAPER_FIELDS}
        tree_nodes = [{
            'paper_id': target['paperId'],
            'node_type': 'target',
            'depth': 0,
            'parent_paper_id': None,
        }]

        # ── Step 2: Ancestors ────────────────────────────────────────
        logger.info("STEP 2 — ancestors  max_depth=%d  max_children=3", max_depth)
        t2 = time.perf_counter()
        ancestors, ancestor_nodes = self.build_recursive_ancestors(
            paper_id,
            target.get('year'),
            current_depth=0,
            max_depth=max_depth,
            max_children=3,
            _nodes=[],
        )
        tree['ancestors'] = ancestors
        tree_nodes.extend(ancestor_nodes)
        logger.info("STEP 2 DONE  total_ancestor_nodes=%d  elapsed=%s",
                    len(ancestor_nodes), _ms(t2))

        # ── Step 3: Descendants ──────────────────────────────────────
        logger.info("STEP 3 — descendants  max_depth=%d  max_children=%d  window=%d",
                    max_depth, max_children, window_years)
        t3 = time.perf_counter()
        if target.get('year'):
            descendants, descendant_nodes = self.build_recursive_descendants(
                paper_id,
                target['year'],
                current_depth=0,
                max_depth=max_depth,
                window_years=window_years,
                max_children=max_children,
                _nodes=[],
            )
            tree['descendants'] = descendants
            tree_nodes.extend(descendant_nodes)
            logger.info("STEP 3 DONE  total_descendant_nodes=%d  elapsed=%s",
                        len(descendant_nodes), _ms(t3))
        else:
            logger.warning("STEP 3 SKIPPED — target paper has no year")

        # ── Step 4: Persist tree run ─────────────────────────────────
        logger.info("STEP 4 — persist tree run")
        t4 = time.perf_counter()
        ts = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
        safe_id = paper_id.replace(':', '_').replace('/', '_')
        tree_id = f"{safe_id}_{ts}"

        self.cache.save_tree(tree_id, paper_id, max_depth, max_children, window_years)
        self.cache.save_tree_nodes(tree_id, tree_nodes)
        logger.info("STEP 4 DONE  tree_id=%s  total_nodes=%d  elapsed=%s",
                    tree_id, len(tree_nodes), _ms(t4))

        # ── Summary ──────────────────────────────────────────────────
        logger.info("=" * 70)
        logger.info("BUILD TREE COMPLETE  paper=%s  nodes=%d  total_elapsed=%s",
                    paper_id, len(tree_nodes), _ms(t_total))
        logger.info("  ancestors=%d  descendants=%d",
                    len(ancestor_nodes), len(tree_nodes) - 1 - len(ancestor_nodes))
        logger.info("=" * 70)

        return tree
