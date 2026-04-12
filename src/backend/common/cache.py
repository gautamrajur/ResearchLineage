"""
common/cache.py
---------------
Shared PostgreSQL cache for pred_successor_view and evolution_view.

All tables are paper-centric (keyed by paper_id, not tree_id) so data
fetched for one view is automatically reused by the other.

Tables
------
  papers               — paper metadata
  references           — cited-paper edges (ancestors)
  citations            — citing-paper edges (descendants)
  fetch_log            — every /references and /citations API call outcome
  lineage              — Gemini-selected predecessor chain
  analysis             — Gemini per-paper analysis output
  comparison           — Gemini comparison vs predecessor
  secondary_influences — secondary influence papers identified by Gemini
  trees                — pred_successor_view tree run metadata
  tree_nodes           — nodes in each tree run
  feedback             — user feedback
"""

import json
import psycopg2
import psycopg2.extras
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Dict, List, Optional
from psycopg2.pool import ThreadedConnectionPool

from .config import DATABASE_URL

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS papers (
    paper_id                    TEXT PRIMARY KEY,
    arxiv_id                    TEXT,
    title                       TEXT,
    year                        INT,
    abstract                    TEXT,
    citation_count              INT,
    influential_citation_count  INT,
    field_of_study              TEXT,
    pdf_s3_uri                  TEXT,
    source_type                 TEXT,
    fetched_at                  TEXT
);

CREATE TABLE IF NOT EXISTS "references" (
    paper_id              TEXT,
    cited_paper_id        TEXT,
    is_influential        INT,
    intents               TEXT,
    cited_citation_count  INT,
    fetched_at            TEXT,
    PRIMARY KEY (paper_id, cited_paper_id)
);

CREATE TABLE IF NOT EXISTS citations (
    paper_id               TEXT,
    citing_paper_id        TEXT,
    is_influential         INT,
    intents                TEXT,
    citing_citation_count  INT,
    year_window_start      INT,
    year_window_end        INT,
    fetched_at             TEXT,
    PRIMARY KEY (paper_id, citing_paper_id)
);

CREATE TABLE IF NOT EXISTS fetch_log (
    paper_id      TEXT,
    fetch_type    TEXT,
    year_start    INT,
    year_end      INT,
    result_count  INT,
    fetched_at    TEXT,
    PRIMARY KEY (paper_id, fetch_type, year_start, year_end)
);

CREATE TABLE IF NOT EXISTS lineage (
    paper_id             TEXT PRIMARY KEY,
    predecessor_id       TEXT,
    is_foundational      INT,
    selection_reasoning  TEXT
);

CREATE TABLE IF NOT EXISTS analysis (
    paper_id                TEXT PRIMARY KEY,
    problem_addressed       TEXT,
    core_method             TEXT,
    key_innovation          TEXT,
    limitations             TEXT,
    breakthrough_level      TEXT,
    explanation_eli5        TEXT,
    explanation_intuitive   TEXT,
    explanation_technical   TEXT,
    analyzed_at             TEXT
);

CREATE TABLE IF NOT EXISTS comparison (
    paper_id                        TEXT PRIMARY KEY,
    predecessor_id                  TEXT,
    what_was_improved               TEXT,
    how_it_was_improved             TEXT,
    why_it_matters                  TEXT,
    problem_solved_from_predecessor TEXT,
    remaining_limitations           TEXT
);

CREATE TABLE IF NOT EXISTS secondary_influences (
    paper_id         TEXT,
    influenced_by_id TEXT,
    contribution     TEXT,
    title            TEXT,
    year             INT,
    PRIMARY KEY (paper_id, influenced_by_id)
);

CREATE TABLE IF NOT EXISTS trees (
    tree_id        TEXT PRIMARY KEY,
    root_paper_id  TEXT,
    generated_at   TEXT,
    max_depth      INT,
    max_children   INT,
    window_years   INT
);

CREATE TABLE IF NOT EXISTS tree_nodes (
    tree_id         TEXT,
    paper_id        TEXT,
    node_type       TEXT,
    depth           INT,
    parent_paper_id TEXT,
    PRIMARY KEY (tree_id, paper_id)
);

CREATE TABLE IF NOT EXISTS feedback (
    feedback_id      TEXT PRIMARY KEY,
    paper_id         TEXT,
    related_paper_id TEXT,
    view_type        TEXT,
    feedback_target  TEXT,
    rating           INT,
    comment          TEXT,
    created_at       TEXT
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


_schema_applied: set = set()  # tracks DSNs that have already run DDL this process

# ---------------------------------------------------------------------------
# Module-level connection pool (one pool per DSN, shared across all Cache
# instances in this process)
# ---------------------------------------------------------------------------

_pools: Dict[str, ThreadedConnectionPool] = {}


def _get_pool(dsn: str) -> ThreadedConnectionPool:
    """Return the existing pool for this DSN, or create one."""
    if dsn not in _pools:
        _pools[dsn] = ThreadedConnectionPool(
            minconn=2,
            maxconn=20,
            dsn=dsn,
        )
    return _pools[dsn]


class Cache:
    """
    PostgreSQL-backed cache shared by both views.

    Uses a module-level ThreadedConnectionPool so connections are reused
    across requests instead of being opened and held per-request.

    Instantiate once per request:
        cache = Cache()          # uses DATABASE_URL from config
        cache = Cache(dsn="...") # override connection string
    """

    def __init__(self, dsn: str = DATABASE_URL):
        self._pool = _get_pool(dsn)
        self._dsn  = dsn
        if dsn not in _schema_applied:
            with self._get_conn() as conn:
                self._apply_schema(conn)
            _schema_applied.add(dsn)

    @contextmanager
    def _get_conn(self):
        """
        Borrow a connection from the pool, yield it, then return it.

        On exception: rolls back before returning so the connection is clean.
        On normal exit: caller is responsible for commit() inside the block.
        After exit (both paths): rollback() clears any open idle transaction
        left by read-only queries, then the connection is returned to the pool.
        """
        conn = self._pool.getconn()
        try:
            yield conn
        except Exception:
            conn.rollback()
            raise
        finally:
            # Safe after commit (no-op), and cleans up open read transactions.
            conn.rollback()
            self._pool.putconn(conn)

    def _apply_schema(self, conn) -> None:
        with conn.cursor() as cur:
            for stmt in SCHEMA.split(";"):
                stmt = stmt.strip()
                if stmt:
                    cur.execute(stmt)
        conn.commit()

    # ------------------------------------------------------------------
    # Papers
    # ------------------------------------------------------------------

    def get_paper(self, paper_id: str) -> Optional[Dict]:
        """
        Look up by S2 paper_id or ARXIV: prefix.
        Returns dict shaped like S2 API response, plus fetch-status fields.
        """
        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT paper_id, arxiv_id, title, year, abstract, "
                    "       citation_count, influential_citation_count, "
                    "       field_of_study, source_type "
                    "FROM papers WHERE paper_id = %s",
                    (paper_id,),
                )
                row = cur.fetchone()

                if row is None and paper_id.upper().startswith("ARXIV:"):
                    arxiv_bare = paper_id.split(":", 1)[1]
                    cur.execute(
                        "SELECT paper_id, arxiv_id, title, year, abstract, "
                        "       citation_count, influential_citation_count, "
                        "       field_of_study, source_type "
                        "FROM papers WHERE arxiv_id = %s",
                        (arxiv_bare,),
                    )
                    row = cur.fetchone()

                if row is None:
                    return None

                s2_id = row["paper_id"]

                cur.execute(
                    "SELECT result_count, fetched_at FROM fetch_log "
                    "WHERE paper_id = %s AND fetch_type = 'references'",
                    (s2_id,),
                )
                ref_log = cur.fetchone()

        fields = row["field_of_study"]
        return {
            "paperId":                  s2_id,
            "title":                    row["title"],
            "year":                     row["year"],
            "abstract":                 row["abstract"],
            "citationCount":            row["citation_count"],
            "influentialCitationCount": row["influential_citation_count"],
            "fieldsOfStudy":            [fields] if fields else [],
            "externalIds":              {"ArXiv": row["arxiv_id"]} if row["arxiv_id"] else {},
            "_source_type":             row["source_type"],
            "referencesFetched":        ref_log is not None,
            "referencesResultCount":    ref_log["result_count"] if ref_log else None,
        }

    def save_paper(self, paper: Dict, lookup_id: Optional[str] = None,
                   source_type: Optional[str] = None) -> None:
        """Insert paper metadata. Backfills arxiv_id and source_type if missing."""
        s2_id = paper.get("paperId")
        if not s2_id:
            return

        arxiv_id = None
        ext = paper.get("externalIds") or {}
        if ext.get("ArXiv"):
            arxiv_id = ext["ArXiv"]
        elif lookup_id and lookup_id.upper().startswith("ARXIV:"):
            arxiv_id = lookup_id.split(":", 1)[1]

        fields = paper.get("fieldsOfStudy") or []
        field  = fields[0] if fields else None
        now    = _now()

        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "INSERT INTO papers "
                    "(paper_id, arxiv_id, title, year, abstract, citation_count, "
                    " influential_citation_count, field_of_study, fetched_at) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) "
                    "ON CONFLICT DO NOTHING",
                    (
                        s2_id, arxiv_id, paper.get("title"), paper.get("year"),
                        paper.get("abstract"),
                        paper.get("citationCount"), paper.get("influentialCitationCount"),
                        field, now,
                    ),
                )
                if arxiv_id:
                    cur.execute(
                        "UPDATE papers SET arxiv_id = %s "
                        "WHERE paper_id = %s AND arxiv_id IS NULL",
                        (arxiv_id, s2_id),
                    )
                if source_type:
                    cur.execute(
                        "UPDATE papers SET source_type = %s WHERE paper_id = %s",
                        (source_type, s2_id),
                    )
            conn.commit()

    # ------------------------------------------------------------------
    # References (ancestors)
    # ------------------------------------------------------------------

    def has_references(self, paper_id: str) -> bool:
        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT COUNT(*) AS cnt FROM fetch_log "
                    "WHERE paper_id = %s AND fetch_type = 'references'",
                    (paper_id,),
                )
                return cur.fetchone()["cnt"] > 0

    def get_references(self, paper_id: str, max_children: int) -> List[Dict]:
        """
        Return filtered + sorted references replicating cold-run selection.
        Two-step fallback: methodology first, then influential.
        """
        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    'SELECT r.cited_paper_id, r.is_influential, r.intents, '
                    '       r.cited_citation_count, p.title, p.year, p.arxiv_id '
                    'FROM   "references" r '
                    'JOIN   papers p ON p.paper_id = r.cited_paper_id '
                    "WHERE  r.paper_id = %s AND r.intents LIKE '%%methodology%%'",
                    (paper_id,),
                )
                methodology = cur.fetchall()

                if len(methodology) < max_children:
                    seen = {r["cited_paper_id"] for r in methodology}
                    cur.execute(
                        'SELECT r.cited_paper_id, r.is_influential, r.intents, '
                        '       r.cited_citation_count, p.title, p.year, p.arxiv_id '
                        'FROM   "references" r '
                        'JOIN   papers p ON p.paper_id = r.cited_paper_id '
                        'WHERE  r.paper_id = %s AND r.is_influential = 1',
                        (paper_id,),
                    )
                    for row in cur.fetchall():
                        if row["cited_paper_id"] not in seen:
                            methodology.append(row)
                            seen.add(row["cited_paper_id"])

        top = sorted(
            methodology,
            key=lambda r: (-(r["cited_citation_count"] or 0), r["cited_paper_id"] or ""),
        )[:max_children]

        return [
            {
                "isInfluential": bool(r["is_influential"]),
                "intents": json.loads(r["intents"]) if r["intents"] else [],
                "citedPaper": {
                    "paperId":       r["cited_paper_id"],
                    "title":         r["title"],
                    "year":          r["year"],
                    "citationCount": r["cited_citation_count"],
                    "externalIds":   {"ArXiv": r["arxiv_id"]} if r["arxiv_id"] else {},
                },
            }
            for r in top
        ]

    def save_references(self, paper_id: str, refs_data: List[Dict]) -> None:
        """Save ALL refs from API response. Always writes a fetch_log row."""
        from psycopg2.extras import execute_values

        now = _now()

        paper_rows = []
        ref_rows = []
        for ref in refs_data:
            cited = ref.get("citedPaper") or ref.get("paper") or {}
            if not cited or not cited.get("paperId"):
                continue
            paper_rows.append((
                cited.get("paperId"), cited.get("title"),
                cited.get("year"), cited.get("citationCount"), now,
            ))
            ref_rows.append((
                paper_id, cited.get("paperId"),
                1 if ref.get("isInfluential") else 0,
                json.dumps(ref.get("intents") or []),
                cited.get("citationCount"), now,
            ))

        saved = len(ref_rows)
        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                if paper_rows:
                    execute_values(
                        cur,
                        "INSERT INTO papers "
                        "(paper_id, title, year, citation_count, fetched_at) "
                        "VALUES %s ON CONFLICT DO NOTHING",
                        paper_rows,
                        page_size=500,
                    )
                if ref_rows:
                    execute_values(
                        cur,
                        'INSERT INTO "references" '
                        "(paper_id, cited_paper_id, is_influential, intents, "
                        " cited_citation_count, fetched_at) "
                        "VALUES %s ON CONFLICT DO NOTHING",
                        ref_rows,
                        page_size=500,
                    )
                cur.execute(
                    "INSERT INTO fetch_log "
                    "(paper_id, fetch_type, year_start, year_end, result_count, fetched_at) "
                    "VALUES (%s, 'references', 0, 0, %s, %s) "
                    "ON CONFLICT (paper_id, fetch_type, year_start, year_end) "
                    "DO UPDATE SET result_count = EXCLUDED.result_count, "
                    "              fetched_at   = EXCLUDED.fetched_at",
                    (paper_id, saved, now),
                )
            conn.commit()

    # ------------------------------------------------------------------
    # Citations (descendants)
    # ------------------------------------------------------------------

    def has_citations(self, paper_id: str, year_start: int, year_end: int) -> bool:
        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT COUNT(*) AS cnt FROM fetch_log "
                    "WHERE paper_id = %s AND fetch_type = 'citations' "
                    "  AND year_start = %s AND year_end = %s",
                    (paper_id, year_start, year_end),
                )
                return cur.fetchone()["cnt"] > 0

    def get_citations(self, paper_id: str, year_start: int, year_end: int,
                      max_children: int) -> List[Dict]:
        """Two-step fallback: methodology first, then influential."""
        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT c.citing_paper_id, c.is_influential, c.intents, "
                    "       c.citing_citation_count, p.title, p.year, p.arxiv_id "
                    "FROM   citations c "
                    "JOIN   papers    p ON p.paper_id = c.citing_paper_id "
                    "WHERE  c.paper_id = %s "
                    "  AND  p.year BETWEEN %s AND %s "
                    "  AND  c.intents LIKE '%%methodology%%'",
                    (paper_id, year_start, year_end),
                )
                methodology = cur.fetchall()

                if len(methodology) < max_children:
                    seen = {r["citing_paper_id"] for r in methodology}
                    cur.execute(
                        "SELECT c.citing_paper_id, c.is_influential, c.intents, "
                        "       c.citing_citation_count, p.title, p.year, p.arxiv_id "
                        "FROM   citations c "
                        "JOIN   papers    p ON p.paper_id = c.citing_paper_id "
                        "WHERE  c.paper_id = %s "
                        "  AND  p.year BETWEEN %s AND %s "
                        "  AND  c.is_influential = 1",
                        (paper_id, year_start, year_end),
                    )
                    for row in cur.fetchall():
                        if row["citing_paper_id"] not in seen:
                            methodology.append(row)
                            seen.add(row["citing_paper_id"])

        top = sorted(
            methodology,
            key=lambda r: (-(r["citing_citation_count"] or 0), r["citing_paper_id"] or ""),
        )[:max_children]

        return [
            {
                "isInfluential": bool(r["is_influential"]),
                "intents": json.loads(r["intents"]) if r["intents"] else [],
                "citingPaper": {
                    "paperId":       r["citing_paper_id"],
                    "title":         r["title"],
                    "year":          r["year"],
                    "citationCount": r["citing_citation_count"],
                    "externalIds":   {"ArXiv": r["arxiv_id"]} if r["arxiv_id"] else {},
                },
            }
            for r in top
        ]

    def save_citations(self, paper_id: str, cites_data: List[Dict],
                       year_start: int, year_end: int) -> None:
        """Save ALL citation rows. Always writes a fetch_log row."""
        from psycopg2.extras import execute_values

        now = _now()

        paper_rows = []
        cite_rows = []
        for cite in cites_data:
            citing = cite.get("citingPaper") or {}
            if not citing or not citing.get("paperId"):
                continue
            paper_rows.append((
                citing.get("paperId"), citing.get("title"),
                citing.get("year"), citing.get("citationCount"), now,
            ))
            cite_rows.append((
                paper_id, citing.get("paperId"),
                1 if cite.get("isInfluential") else 0,
                json.dumps(cite.get("intents") or []),
                citing.get("citationCount"),
                year_start, year_end, now,
            ))

        saved = len(cite_rows)
        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                if paper_rows:
                    execute_values(
                        cur,
                        "INSERT INTO papers "
                        "(paper_id, title, year, citation_count, fetched_at) "
                        "VALUES %s ON CONFLICT DO NOTHING",
                        paper_rows,
                        page_size=500,
                    )
                if cite_rows:
                    execute_values(
                        cur,
                        "INSERT INTO citations "
                        "(paper_id, citing_paper_id, is_influential, intents, "
                        " citing_citation_count, year_window_start, year_window_end, fetched_at) "
                        "VALUES %s ON CONFLICT DO NOTHING",
                        cite_rows,
                        page_size=500,
                    )
                cur.execute(
                    "INSERT INTO fetch_log "
                    "(paper_id, fetch_type, year_start, year_end, result_count, fetched_at) "
                    "VALUES (%s, 'citations', %s, %s, %s, %s) "
                    "ON CONFLICT (paper_id, fetch_type, year_start, year_end) "
                    "DO UPDATE SET result_count = EXCLUDED.result_count, "
                    "              fetched_at   = EXCLUDED.fetched_at",
                    (paper_id, year_start, year_end, saved, now),
                )
            conn.commit()

    # ------------------------------------------------------------------
    # Gemini analysis (evolution_view)
    # ------------------------------------------------------------------

    def get_cached_analysis(self, paper_id: str) -> Optional[Dict]:
        """Return the full Gemini output dict for this paper, or None if not cached."""
        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM lineage WHERE paper_id = %s", (paper_id,)
                )
                lin = cur.fetchone()
                if lin is None:
                    return None

                cur.execute("SELECT * FROM analysis WHERE paper_id = %s", (paper_id,))
                an = cur.fetchone()

                cur.execute("SELECT * FROM comparison WHERE paper_id = %s", (paper_id,))
                cmp = cur.fetchone()

                cur.execute(
                    "SELECT influenced_by_id, contribution, title, year "
                    "FROM secondary_influences WHERE paper_id = %s",
                    (paper_id,),
                )
                sec_rows = cur.fetchall()

        ta = {}
        if an:
            ta = {
                "problem_addressed":     an["problem_addressed"],
                "core_method":           an["core_method"],
                "key_innovation":        an["key_innovation"],
                "limitations":           json.loads(an["limitations"]) if an["limitations"] else [],
                "breakthrough_level":    an["breakthrough_level"],
                "explanation_eli5":      an["explanation_eli5"],
                "explanation_intuitive": an["explanation_intuitive"],
                "explanation_technical": an["explanation_technical"],
            }

        comparison = None
        if cmp:
            comparison = {
                "what_was_improved":               cmp["what_was_improved"],
                "how_it_was_improved":             cmp["how_it_was_improved"],
                "why_it_matters":                  cmp["why_it_matters"],
                "problem_solved_from_predecessor": cmp["problem_solved_from_predecessor"],
                "remaining_limitations":           json.loads(cmp["remaining_limitations"])
                                                   if cmp["remaining_limitations"] else [],
            }

        return {
            "selected_predecessor_id": lin["predecessor_id"],
            "selection_reasoning":     lin["selection_reasoning"],
            "target_analysis":         ta,
            "comparison":              comparison,
            "secondary_influences": [
                {"paper_id": r["influenced_by_id"], "contribution": r["contribution"],
                 "title": r["title"], "year": r["year"]}
                for r in sec_rows
            ],
        }

    def save_analysis(self, paper_id: str, predecessor_id: Optional[str],
                      is_foundational: bool, analysis_dict: Dict) -> None:
        """Write lineage + analysis + comparison + secondary_influences atomically."""
        now = _now()
        ta  = analysis_dict.get("target_analysis") or {}
        cmp = analysis_dict.get("comparison") or {}
        sec = analysis_dict.get("secondary_influences") or []

        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "INSERT INTO lineage "
                    "(paper_id, predecessor_id, is_foundational, selection_reasoning) "
                    "VALUES (%s, %s, %s, %s) "
                    "ON CONFLICT (paper_id) DO UPDATE SET "
                    "  predecessor_id      = EXCLUDED.predecessor_id, "
                    "  is_foundational     = EXCLUDED.is_foundational, "
                    "  selection_reasoning = EXCLUDED.selection_reasoning",
                    (paper_id, predecessor_id, 1 if is_foundational else 0,
                     analysis_dict.get("selection_reasoning")),
                )
                cur.execute(
                    "INSERT INTO analysis "
                    "(paper_id, problem_addressed, core_method, key_innovation, "
                    " limitations, breakthrough_level, explanation_eli5, "
                    " explanation_intuitive, explanation_technical, analyzed_at) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
                    "ON CONFLICT (paper_id) DO UPDATE SET "
                    "  problem_addressed     = EXCLUDED.problem_addressed, "
                    "  core_method           = EXCLUDED.core_method, "
                    "  key_innovation        = EXCLUDED.key_innovation, "
                    "  limitations           = EXCLUDED.limitations, "
                    "  breakthrough_level    = EXCLUDED.breakthrough_level, "
                    "  explanation_eli5      = EXCLUDED.explanation_eli5, "
                    "  explanation_intuitive = EXCLUDED.explanation_intuitive, "
                    "  explanation_technical = EXCLUDED.explanation_technical, "
                    "  analyzed_at           = EXCLUDED.analyzed_at",
                    (
                        paper_id,
                        ta.get("problem_addressed"), ta.get("core_method"),
                        ta.get("key_innovation"),
                        json.dumps(ta.get("limitations") or []),
                        ta.get("breakthrough_level"), ta.get("explanation_eli5"),
                        ta.get("explanation_intuitive"), ta.get("explanation_technical"),
                        now,
                    ),
                )
                if cmp and not is_foundational:
                    cur.execute(
                        "INSERT INTO comparison "
                        "(paper_id, predecessor_id, what_was_improved, how_it_was_improved, "
                        " why_it_matters, problem_solved_from_predecessor, remaining_limitations) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s) "
                        "ON CONFLICT (paper_id) DO UPDATE SET "
                        "  what_was_improved               = EXCLUDED.what_was_improved, "
                        "  how_it_was_improved             = EXCLUDED.how_it_was_improved, "
                        "  why_it_matters                  = EXCLUDED.why_it_matters, "
                        "  problem_solved_from_predecessor = EXCLUDED.problem_solved_from_predecessor, "
                        "  remaining_limitations           = EXCLUDED.remaining_limitations",
                        (
                            paper_id, predecessor_id,
                            cmp.get("what_was_improved"), cmp.get("how_it_was_improved"),
                            cmp.get("why_it_matters"),
                            cmp.get("problem_solved_from_predecessor"),
                            json.dumps(cmp.get("remaining_limitations") or []),
                        ),
                    )
                for inf in sec:
                    if isinstance(inf, dict) and inf.get("paper_id"):
                        cur.execute(
                            "SELECT title, year FROM papers WHERE paper_id = %s",
                            (inf["paper_id"],),
                        )
                        p = cur.fetchone()
                        cur.execute(
                            "INSERT INTO secondary_influences "
                            "(paper_id, influenced_by_id, contribution, title, year) "
                            "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (paper_id, influenced_by_id) "
                            "DO UPDATE SET title = EXCLUDED.title, year = EXCLUDED.year",
                            (paper_id, inf["paper_id"], inf.get("contribution"),
                             p["title"] if p else None, p["year"] if p else None),
                        )
            conn.commit()

    def get_cached_timeline(self, paper_id: str,
                            max_depth: Optional[int] = None):
        """
        Reconstruct the full timeline chain from DB.

        Returns (steps_list, True) if fully cached, (None, False) on any miss.
        """
        from .s2_client import SemanticScholarClient
        norm_id = SemanticScholarClient.normalize_paper_id(paper_id)
        arxiv_bare = norm_id.replace("ARXIV:", "").replace("arxiv:", "")

        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT paper_id FROM papers WHERE arxiv_id = %s", (arxiv_bare,)
                )
                row = cur.fetchone()
        current = row["paper_id"] if row else paper_id

        chain_ids = []
        while True:
            with self._get_conn() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(
                        "SELECT * FROM lineage WHERE paper_id = %s", (current,)
                    )
                    lin = cur.fetchone()

            if lin is None:
                return None, False

            chain_ids.append(current)

            if max_depth and len(chain_ids) >= max_depth:
                break
            if lin["is_foundational"] or lin["predecessor_id"] is None:
                break
            current = lin["predecessor_id"]

        steps = []
        for depth, pid in enumerate(chain_ids):
            cached = self.get_cached_analysis(pid)
            paper  = self.get_paper(pid)
            if cached is None or paper is None:
                return None, False

            pred_id    = cached.get("selected_predecessor_id")
            pred_paper = self.get_paper(pred_id) if pred_id else None

            steps.append({
                "depth":              depth,
                "target_paper":       paper,
                "target_text":        "",
                "target_source_type": paper.get("_source_type") or "FULL_TEXT",
                "predecessor_paper":  pred_paper,
                "candidates_considered": 0,
                "analysis":           cached,
                "is_foundational":    pred_paper is None,
            })

        return steps, True

    # ------------------------------------------------------------------
    # Trees (pred_successor_view)
    # ------------------------------------------------------------------

    def save_tree(self, tree_id: str, root_paper_id: str,
                  max_depth: int, max_children: int, window_years: int) -> None:
        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "INSERT INTO trees "
                    "(tree_id, root_paper_id, generated_at, max_depth, max_children, window_years) "
                    "VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
                    (tree_id, root_paper_id, _now(), max_depth, max_children, window_years),
                )
            conn.commit()

    def save_tree_nodes(self, tree_id: str, nodes: List[Dict]) -> None:
        rows = [
            (tree_id, n["paper_id"], n["node_type"], n["depth"], n.get("parent_paper_id"))
            for n in nodes
        ]
        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                psycopg2.extras.execute_values(
                    cur,
                    "INSERT INTO tree_nodes "
                    "(tree_id, paper_id, node_type, depth, parent_paper_id) "
                    "VALUES %s ON CONFLICT DO NOTHING",
                    rows,
                )
            conn.commit()

    # ------------------------------------------------------------------
    # Feedback
    # ------------------------------------------------------------------

    def save_feedback(self, feedback_id: str, paper_id: str,
                      related_paper_id: Optional[str], view_type: str,
                      feedback_target: str, rating: int,
                      comment: Optional[str]) -> None:
        """Persist anonymous user feedback for drift detection."""
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO feedback "
                    "(feedback_id, paper_id, related_paper_id, view_type, "
                    " feedback_target, rating, comment, created_at) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
                    "ON CONFLICT DO NOTHING",
                    (feedback_id, paper_id, related_paper_id, view_type,
                     feedback_target, rating, comment, _now()),
                )
            conn.commit()

    # ------------------------------------------------------------------

    def close(self) -> None:
        # Connections are managed by the pool — nothing to close per-instance.
        # The pool itself lives for the process lifetime.
        pass
