import psycopg2
import psycopg2.extras
import json
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------
# Requires Cloud SQL Proxy running before use:
#   ./cloud-sql-proxy researchlineage:us-central1:researchlineage-db --port 5432 &
#
# Set PG_PASSWORD in the environment (or DATABASE_URL for a full override).
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://jithin:{pw}@127.0.0.1:5432/researchlineage".format(
        pw=os.environ.get("PG_PASSWORD", "")
    )
)

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
    PRIMARY KEY (paper_id, influenced_by_id)
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

CREATE TABLE IF NOT EXISTS fetch_log (
    paper_id      TEXT,
    fetch_type    TEXT,
    year_start    INT,
    year_end      INT,
    result_count  INT,
    fetched_at    TEXT,
    PRIMARY KEY (paper_id, fetch_type, year_start, year_end)
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Cache:
    def __init__(self, dsn: str = DATABASE_URL):
        self._conn = psycopg2.connect(dsn)
        self._conn.autocommit = False
        self._apply_schema()

    def _cur(self):
        """Return a RealDictCursor (column access by name, like sqlite3.Row)."""
        return self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    def _apply_schema(self) -> None:
        with self._cur() as cur:
            for stmt in SCHEMA.split(';'):
                stmt = stmt.strip()
                if stmt:
                    cur.execute(stmt)
        self._conn.commit()

    # ------------------------------------------------------------------
    # papers
    # ------------------------------------------------------------------

    def get_paper(self, paper_id: str) -> Optional[Dict]:
        """Look up paper by S2 paper_id OR by arxiv_id (e.g. 'ARXIV:1706.03762').

        Returns fetch_status fields so callers and the UI can distinguish:
          referencesFetched: True  → fetch was attempted (result_count may be 0)
          referencesResultCount: int or None → how many refs the API returned
        """
        with self._cur() as cur:
            cur.execute(
                "SELECT paper_id, title, year, citation_count, influential_citation_count "
                "FROM papers WHERE paper_id = %s",
                (paper_id,)
            )
            row = cur.fetchone()

            if row is None and paper_id.upper().startswith('ARXIV:'):
                arxiv_id = paper_id.split(':', 1)[1]
                cur.execute(
                    "SELECT paper_id, title, year, citation_count, influential_citation_count "
                    "FROM papers WHERE arxiv_id = %s",
                    (arxiv_id,)
                )
                row = cur.fetchone()

            if row is None:
                return None

            s2_id = row['paper_id']

            cur.execute(
                "SELECT result_count, fetched_at FROM fetch_log "
                "WHERE paper_id = %s AND fetch_type = 'references'",
                (s2_id,)
            )
            ref_log = cur.fetchone()

        return {
            'paperId': s2_id,
            'title': row['title'],
            'year': row['year'],
            'citationCount': row['citation_count'],
            'influentialCitationCount': row['influential_citation_count'],
            'referencesFetched': ref_log is not None,
            'referencesResultCount': ref_log['result_count'] if ref_log else None,
            'referencesFetchedAt': ref_log['fetched_at'] if ref_log else None,
        }

    def save_paper(self, paper: Dict, lookup_id: Optional[str] = None) -> None:
        """Insert basic paper metadata (tree_builder fields only)."""
        now = _now()
        s2_id = paper.get('paperId')

        arxiv_id = None
        if lookup_id and lookup_id.upper().startswith('ARXIV:'):
            arxiv_id = lookup_id.split(':', 1)[1]

        with self._cur() as cur:
            cur.execute(
                "INSERT INTO papers "
                "(paper_id, arxiv_id, title, year, citation_count, "
                " influential_citation_count, fetched_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT DO NOTHING",
                (s2_id, arxiv_id, paper.get('title'), paper.get('year'),
                 paper.get('citationCount'), paper.get('influentialCitationCount'), now),
            )
            if arxiv_id:
                cur.execute(
                    "UPDATE papers SET arxiv_id = %s WHERE paper_id = %s AND arxiv_id IS NULL",
                    (arxiv_id, s2_id)
                )
        self._conn.commit()

    # ------------------------------------------------------------------
    # references (ancestors)
    # ------------------------------------------------------------------

    def has_references(self, paper_id: str) -> bool:
        """True if we have previously fetched this paper's references (even if the API returned empty)."""
        with self._cur() as cur:
            cur.execute(
                "SELECT COUNT(*) AS cnt FROM fetch_log "
                "WHERE paper_id = %s AND fetch_type = 'references'",
                (paper_id,)
            )
            return cur.fetchone()['cnt'] > 0

    def get_references(self, paper_id: str, max_children: int) -> List[Dict]:
        """Return filtered + sorted references, replicating cold-run selection exactly.

        Two-step fallback:
          1. Take methodology refs only.
          2. If count < max_children, also add influential refs (deduplicated).
          3. Sort combined list by cited_citation_count DESC, paperId ASC; take top max_children.
        """
        with self._cur() as cur:
            # Step 1 — methodology refs
            cur.execute(
                'SELECT r.cited_paper_id, r.is_influential, r.intents, '
                '       r.cited_citation_count, p.title, p.year '
                'FROM   "references" r '
                'JOIN   papers p ON p.paper_id = r.cited_paper_id '
                "WHERE  r.paper_id = %s AND r.intents LIKE '%%methodology%%'",
                (paper_id,)
            )
            methodology = cur.fetchall()

            # Step 2 — fallback: add influential only when methodology count < max_children
            if len(methodology) < max_children:
                seen = {r['cited_paper_id'] for r in methodology}
                cur.execute(
                    'SELECT r.cited_paper_id, r.is_influential, r.intents, '
                    '       r.cited_citation_count, p.title, p.year '
                    'FROM   "references" r '
                    'JOIN   papers p ON p.paper_id = r.cited_paper_id '
                    'WHERE  r.paper_id = %s AND r.is_influential = 1',
                    (paper_id,)
                )
                for row in cur.fetchall():
                    if row['cited_paper_id'] not in seen:
                        methodology.append(row)
                        seen.add(row['cited_paper_id'])

        # Step 3 — sort combined list, take top max_children
        top = sorted(methodology,
                     key=lambda r: (-(r['cited_citation_count'] or 0),
                                    r['cited_paper_id'] or ''))[:max_children]

        return [
            {
                'isInfluential': bool(r['is_influential']),
                'intents': json.loads(r['intents']) if r['intents'] else [],
                'citedPaper': {
                    'paperId': r['cited_paper_id'],
                    'title': r['title'],
                    'year': r['year'],
                    'citationCount': r['cited_citation_count'],
                }
            }
            for r in top
        ]

    def save_references(self, paper_id: str, refs_data: List[Dict]) -> None:
        """Save ALL refs from API response. Always records the fetch in fetch_log."""
        now = _now()
        saved = 0
        with self._cur() as cur:
            for ref in refs_data:
                cited = ref.get('citedPaper')
                if not cited or not cited.get('paperId'):
                    continue

                cur.execute(
                    "INSERT INTO papers "
                    "(paper_id, title, year, citation_count, fetched_at) "
                    "VALUES (%s, %s, %s, %s, %s) "
                    "ON CONFLICT DO NOTHING",
                    (cited.get('paperId'), cited.get('title'),
                     cited.get('year'), cited.get('citationCount'), now)
                )
                cur.execute(
                    'INSERT INTO "references" '
                    "(paper_id, cited_paper_id, is_influential, intents, "
                    " cited_citation_count, fetched_at) "
                    "VALUES (%s, %s, %s, %s, %s, %s) "
                    "ON CONFLICT DO NOTHING",
                    (
                        paper_id,
                        cited.get('paperId'),
                        1 if ref.get('isInfluential') else 0,
                        json.dumps(ref.get('intents') or []),
                        cited.get('citationCount'),
                        now,
                    )
                )
                saved += 1

            # Always log the fetch — result_count=0 means API returned null/empty
            cur.execute(
                "INSERT INTO fetch_log "
                "(paper_id, fetch_type, year_start, year_end, result_count, fetched_at) "
                "VALUES (%s, 'references', 0, 0, %s, %s) "
                "ON CONFLICT (paper_id, fetch_type, year_start, year_end) "
                "DO UPDATE SET result_count = EXCLUDED.result_count, "
                "              fetched_at   = EXCLUDED.fetched_at",
                (paper_id, saved, now)
            )
        self._conn.commit()

    # ------------------------------------------------------------------
    # citations (descendants)
    # ------------------------------------------------------------------

    def has_citations(self, paper_id: str, year_start: int, year_end: int) -> bool:
        """True if we have previously fetched citations for this paper+window (even if empty)."""
        with self._cur() as cur:
            cur.execute(
                "SELECT COUNT(*) AS cnt FROM fetch_log "
                "WHERE paper_id = %s AND fetch_type = 'citations' "
                "  AND year_start = %s AND year_end = %s",
                (paper_id, year_start, year_end)
            )
            return cur.fetchone()['cnt'] > 0

    def get_citations(self, paper_id: str, year_start: int, year_end: int,
                      max_children: int) -> List[Dict]:
        """Return filtered + sorted citations for a year window.

        Two-step fallback:
          1. Take methodology cites only (within year window).
          2. If count < max_children, also add influential cites (deduplicated).
          3. Sort combined list by citing_citation_count DESC, paperId ASC; take top max_children.
        """
        with self._cur() as cur:
            # Step 1 — methodology cites within year window
            cur.execute(
                "SELECT c.citing_paper_id, c.is_influential, c.intents, "
                "       c.citing_citation_count, p.title, p.year "
                "FROM   citations c "
                "JOIN   papers    p ON p.paper_id = c.citing_paper_id "
                "WHERE  c.paper_id = %s "
                "  AND  p.year BETWEEN %s AND %s "
                "  AND  c.intents LIKE '%%methodology%%'",
                (paper_id, year_start, year_end)
            )
            methodology = cur.fetchall()

            # Step 2 — fallback: add influential only when methodology count < max_children
            if len(methodology) < max_children:
                seen = {r['citing_paper_id'] for r in methodology}
                cur.execute(
                    "SELECT c.citing_paper_id, c.is_influential, c.intents, "
                    "       c.citing_citation_count, p.title, p.year "
                    "FROM   citations c "
                    "JOIN   papers    p ON p.paper_id = c.citing_paper_id "
                    "WHERE  c.paper_id = %s "
                    "  AND  p.year BETWEEN %s AND %s "
                    "  AND  c.is_influential = 1",
                    (paper_id, year_start, year_end)
                )
                for row in cur.fetchall():
                    if row['citing_paper_id'] not in seen:
                        methodology.append(row)
                        seen.add(row['citing_paper_id'])

        # Step 3 — sort combined list, take top max_children
        top = sorted(methodology,
                     key=lambda r: (-(r['citing_citation_count'] or 0),
                                    r['citing_paper_id'] or ''))[:max_children]

        return [
            {
                'isInfluential': bool(r['is_influential']),
                'intents': json.loads(r['intents']) if r['intents'] else [],
                'citingPaper': {
                    'paperId': r['citing_paper_id'],
                    'title': r['title'],
                    'year': r['year'],
                    'citationCount': r['citing_citation_count'],
                }
            }
            for r in top
        ]

    def save_citations(self, paper_id: str, cites_data: List[Dict],
                       year_start: int, year_end: int) -> None:
        """Save ALL citation rows from paginated API response. Always records the fetch in fetch_log."""
        now = _now()
        saved = 0
        with self._cur() as cur:
            for cite in cites_data:
                citing = cite.get('citingPaper')
                if not citing or not citing.get('paperId'):
                    continue

                cur.execute(
                    "INSERT INTO papers "
                    "(paper_id, title, year, citation_count, fetched_at) "
                    "VALUES (%s, %s, %s, %s, %s) "
                    "ON CONFLICT DO NOTHING",
                    (citing.get('paperId'), citing.get('title'),
                     citing.get('year'), citing.get('citationCount'), now)
                )
                cur.execute(
                    "INSERT INTO citations "
                    "(paper_id, citing_paper_id, is_influential, intents, "
                    " citing_citation_count, year_window_start, year_window_end, fetched_at) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
                    "ON CONFLICT DO NOTHING",
                    (
                        paper_id,
                        citing.get('paperId'),
                        1 if cite.get('isInfluential') else 0,
                        json.dumps(cite.get('intents') or []),
                        citing.get('citationCount'),
                        year_start,
                        year_end,
                        now,
                    )
                )
                saved += 1

            # Always log the fetch — result_count=0 means API returned null/empty
            cur.execute(
                "INSERT INTO fetch_log "
                "(paper_id, fetch_type, year_start, year_end, result_count, fetched_at) "
                "VALUES (%s, 'citations', %s, %s, %s, %s) "
                "ON CONFLICT (paper_id, fetch_type, year_start, year_end) "
                "DO UPDATE SET result_count = EXCLUDED.result_count, "
                "              fetched_at   = EXCLUDED.fetched_at",
                (paper_id, year_start, year_end, saved, now)
            )
        self._conn.commit()

    # ------------------------------------------------------------------
    # trees + tree_nodes
    # ------------------------------------------------------------------

    def save_tree(self, tree_id: str, root_paper_id: str,
                  max_depth: int, max_children: int, window_years: int) -> None:
        with self._cur() as cur:
            cur.execute(
                "INSERT INTO trees "
                "(tree_id, root_paper_id, generated_at, max_depth, max_children, window_years) "
                "VALUES (%s, %s, %s, %s, %s, %s) "
                "ON CONFLICT DO NOTHING",
                (tree_id, root_paper_id, _now(), max_depth, max_children, window_years)
            )
        self._conn.commit()

    def save_tree_nodes(self, tree_id: str, nodes: List[Dict]) -> None:
        """nodes: list of {paper_id, node_type, depth, parent_paper_id}"""
        rows = [
            (tree_id, n['paper_id'], n['node_type'], n['depth'], n.get('parent_paper_id'))
            for n in nodes
        ]
        with self._cur() as cur:
            psycopg2.extras.execute_values(
                cur,
                "INSERT INTO tree_nodes "
                "(tree_id, paper_id, node_type, depth, parent_paper_id) "
                "VALUES %s ON CONFLICT DO NOTHING",
                rows
            )
        self._conn.commit()

    # ------------------------------------------------------------------

    def close(self) -> None:
        self._conn.close()
