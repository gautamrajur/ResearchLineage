"""
cache.py - SQLite cache for ResearchLineage timeline pipeline.

All DB reads and writes go through this module.
Tables: papers, references, lineage, analysis, comparison, secondary_influences
"""

import json
import sqlite3
import datetime

from config import CACHE_DB_PATH

# ─────────────────────────────────────────────
# Connection helper
# ─────────────────────────────────────────────

def _connect():
    conn = sqlite3.connect(CACHE_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


# ─────────────────────────────────────────────
# Schema init
# ─────────────────────────────────────────────

def init_db():
    """Create all tables if they don't exist."""
    conn = _connect()
    c = conn.cursor()

    c.executescript("""
        CREATE TABLE IF NOT EXISTS papers (
            paper_id                TEXT PRIMARY KEY,
            arxiv_id                TEXT,
            title                   TEXT,
            year                    INTEGER,
            abstract                TEXT,
            citation_count          INTEGER,
            influential_citation_count INTEGER,
            field_of_study          TEXT,
            source_type             TEXT,
            fetched_at              TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_papers_arxiv ON papers(arxiv_id);

        CREATE TABLE IF NOT EXISTS refs (
            paper_id        TEXT,
            cited_paper_id  TEXT,
            is_influential  INTEGER,
            intents         TEXT,
            fetched_at      TEXT,
            PRIMARY KEY (paper_id, cited_paper_id)
        );

        CREATE TABLE IF NOT EXISTS lineage (
            paper_id            TEXT PRIMARY KEY,
            predecessor_id      TEXT,
            is_foundational     INTEGER,
            selection_reasoning TEXT
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
            paper_id        TEXT,
            influenced_by_id TEXT,
            contribution    TEXT,
            PRIMARY KEY (paper_id, influenced_by_id)
        );
    """)
    conn.commit()
    conn.close()


# ─────────────────────────────────────────────
# Papers
# ─────────────────────────────────────────────

def get_paper(paper_id: str):
    """
    Two-pass lookup: by S2 paper_id first, then by arxiv_id.
    Returns a dict shaped like the S2 API response, or None.
    """
    conn = _connect()
    c = conn.cursor()

    # Pass 1 — direct PK lookup
    c.execute("SELECT * FROM papers WHERE paper_id = ?", (paper_id,))
    row = c.fetchone()

    # Pass 2 — arxiv_id lookup (strip ARXIV: prefix if present)
    if row is None:
        arxiv_bare = paper_id.replace("ARXIV:", "").replace("arxiv:", "")
        c.execute("SELECT * FROM papers WHERE arxiv_id = ?", (arxiv_bare,))
        row = c.fetchone()

    conn.close()
    if row is None:
        return None

    return {
        "paperId":                  row["paper_id"],
        "title":                    row["title"],
        "year":                     row["year"],
        "abstract":                 row["abstract"],
        "citationCount":            row["citation_count"],
        "influentialCitationCount": row["influential_citation_count"],
        "fieldsOfStudy":            [row["field_of_study"]] if row["field_of_study"] else [],
        "externalIds":              {"ArXiv": row["arxiv_id"]} if row["arxiv_id"] else {},
        "_source_type":             row["source_type"],
    }


def save_paper(paper_data: dict, source_type: str = None):
    """
    Insert paper metadata. If source_type is given, also update that column.
    Uses INSERT OR IGNORE so existing rows aren't overwritten.
    """
    pid = paper_data.get("paperId")
    if not pid:
        return

    arxiv_id = None
    ext = paper_data.get("externalIds") or {}
    if ext.get("ArXiv"):
        arxiv_id = ext["ArXiv"]

    fields = paper_data.get("fieldsOfStudy") or []
    field = fields[0] if fields else None

    now = datetime.datetime.utcnow().isoformat()

    conn = _connect()
    conn.execute(
        """INSERT OR IGNORE INTO papers
           (paper_id, arxiv_id, title, year, abstract,
            citation_count, influential_citation_count, field_of_study, fetched_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            pid,
            arxiv_id,
            paper_data.get("title"),
            paper_data.get("year"),
            paper_data.get("abstract"),
            paper_data.get("citationCount"),
            paper_data.get("influentialCitationCount"),
            field,
            now,
        )
    )

    # Update arxiv_id if the stub row was inserted without it
    if arxiv_id:
        conn.execute(
            "UPDATE papers SET arxiv_id = ? WHERE paper_id = ? AND arxiv_id IS NULL",
            (arxiv_id, pid)
        )

    if source_type:
        conn.execute(
            "UPDATE papers SET source_type = ? WHERE paper_id = ?",
            (source_type, pid)
        )

    conn.commit()
    conn.close()


# ─────────────────────────────────────────────
# References
# ─────────────────────────────────────────────

def has_references(paper_id: str) -> bool:
    """Return True if we have already fetched references for this paper."""
    conn = _connect()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM refs WHERE paper_id = ?", (paper_id,))
    count = c.fetchone()[0]
    conn.close()
    return count > 0


def save_references(paper_id: str, references: list):
    """
    Save all raw references (all intents, not just methodology) so future
    queries with different filters still hit the cache.
    Also inserts stub rows into papers for cited papers.
    """
    if not references:
        return

    now = datetime.datetime.utcnow().isoformat()
    conn = _connect()

    for ref in references:
        cited = ref.get("citedPaper") or ref.get("paper") or {}
        cited_id = cited.get("paperId")
        if not cited_id:
            continue

        # Save cited paper stub
        conn.execute(
            """INSERT OR IGNORE INTO papers
               (paper_id, title, year, citation_count, fetched_at)
               VALUES (?, ?, ?, ?, ?)""",
            (cited_id, cited.get("title"), cited.get("year"),
             cited.get("citationCount"), now)
        )

        intents = ref.get("intents") or []
        conn.execute(
            """INSERT OR IGNORE INTO refs
               (paper_id, cited_paper_id, is_influential, intents, fetched_at)
               VALUES (?, ?, ?, ?, ?)""",
            (paper_id, cited_id,
             1 if ref.get("isInfluential") else 0,
             json.dumps(intents),
             now)
        )

    conn.commit()
    conn.close()


# ─────────────────────────────────────────────
# Analysis (lineage + analysis + comparison + secondary influences)
# ─────────────────────────────────────────────

def get_cached_analysis(paper_id: str):
    """
    Returns the full Gemini output dict for this paper (same shape as
    analyze_step() / analyze_foundational()), or None if not cached.
    """
    conn = _connect()
    c = conn.cursor()

    c.execute("SELECT * FROM lineage WHERE paper_id = ?", (paper_id,))
    lin = c.fetchone()
    if lin is None:
        conn.close()
        return None

    c.execute("SELECT * FROM analysis WHERE paper_id = ?", (paper_id,))
    an = c.fetchone()

    c.execute("SELECT * FROM comparison WHERE paper_id = ?", (paper_id,))
    cmp = c.fetchone()

    c.execute(
        "SELECT influenced_by_id, contribution FROM secondary_influences WHERE paper_id = ?",
        (paper_id,)
    )
    sec_rows = c.fetchall()
    conn.close()

    target_analysis = {}
    if an:
        target_analysis = {
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
            "remaining_limitations":           json.loads(cmp["remaining_limitations"]) if cmp["remaining_limitations"] else [],
        }

    secondary = [
        {"paper_id": r["influenced_by_id"], "contribution": r["contribution"]}
        for r in sec_rows
    ]

    return {
        "selected_predecessor_id": lin["predecessor_id"],
        "selection_reasoning":     lin["selection_reasoning"],
        "target_analysis":         target_analysis,
        "comparison":              comparison,
        "secondary_influences":    secondary,
    }


def save_analysis(paper_id: str, predecessor_id, is_foundational: bool, analysis_dict: dict):
    """
    Write lineage + analysis + comparison + secondary_influences in one transaction.
    """
    now = datetime.datetime.utcnow().isoformat()
    ta  = analysis_dict.get("target_analysis") or {}
    cmp = analysis_dict.get("comparison") or {}
    sec = analysis_dict.get("secondary_influences") or []

    conn = _connect()
    try:
        conn.execute(
            """INSERT OR REPLACE INTO lineage
               (paper_id, predecessor_id, is_foundational, selection_reasoning)
               VALUES (?, ?, ?, ?)""",
            (paper_id, predecessor_id, 1 if is_foundational else 0,
             analysis_dict.get("selection_reasoning"))
        )

        conn.execute(
            """INSERT OR REPLACE INTO analysis
               (paper_id, problem_addressed, core_method, key_innovation,
                limitations, breakthrough_level, explanation_eli5,
                explanation_intuitive, explanation_technical, analyzed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                paper_id,
                ta.get("problem_addressed"),
                ta.get("core_method"),
                ta.get("key_innovation"),
                json.dumps(ta.get("limitations") or []),
                ta.get("breakthrough_level"),
                ta.get("explanation_eli5"),
                ta.get("explanation_intuitive"),
                ta.get("explanation_technical"),
                now,
            )
        )

        if cmp and not is_foundational:
            conn.execute(
                """INSERT OR REPLACE INTO comparison
                   (paper_id, predecessor_id, what_was_improved, how_it_was_improved,
                    why_it_matters, problem_solved_from_predecessor, remaining_limitations)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    paper_id,
                    predecessor_id,
                    cmp.get("what_was_improved"),
                    cmp.get("how_it_was_improved"),
                    cmp.get("why_it_matters"),
                    cmp.get("problem_solved_from_predecessor"),
                    json.dumps(cmp.get("remaining_limitations") or []),
                )
            )

        for inf in sec:
            if isinstance(inf, dict) and inf.get("paper_id"):
                conn.execute(
                    """INSERT OR IGNORE INTO secondary_influences
                       (paper_id, influenced_by_id, contribution)
                       VALUES (?, ?, ?)""",
                    (paper_id, inf["paper_id"], inf.get("contribution"))
                )

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ─────────────────────────────────────────────
# Full timeline reconstruction
# ─────────────────────────────────────────────

def get_cached_timeline(paper_id: str, max_depth: int = None):
    """
    Try to reconstruct the full timeline chain from DB.

    Returns (steps_list, True) if the full chain is cached,
    (None, False) if any step is missing.

    The returned steps list has the same shape as build_timeline() —
    depth 0 is the seed paper, increasing toward the foundational paper.

    If max_depth is given, truncates the chain at that length (same
    behaviour as the pipeline stopping at max_depth).
    """
    conn = _connect()
    c = conn.cursor()

    # Walk lineage chain: seed → predecessor → ... → foundational
    chain_ids = []

    # Normalise input the same way semantic_scholar.normalize_paper_id does,
    # then strip the ARXIV: prefix to get the bare ID for the DB lookup.
    import re as _re
    _id = paper_id.strip()
    for _pat in [r'arxiv\.org/abs/(\d+\.\d+)', r'arxiv\.org/pdf/(\d+\.\d+)', r'arxiv\.org/html/(\d+\.\d+)']:
        _m = _re.search(_pat, _id)
        if _m:
            _id = f"ARXIV:{_m.group(1)}"
            break
    if _re.match(r'^\d{4}\.\d{4,5}(v\d+)?$', _id):
        _id = f"ARXIV:{_id}"
    arxiv_bare = _id.replace("ARXIV:", "").replace("arxiv:", "")

    current = paper_id
    c.execute("SELECT paper_id FROM papers WHERE arxiv_id = ?", (arxiv_bare,))
    row = c.fetchone()
    if row:
        current = row["paper_id"]

    while True:
        c.execute("SELECT * FROM lineage WHERE paper_id = ?", (current,))
        lin = c.fetchone()
        if lin is None:
            # This paper hasn't been analysed yet — cache miss
            conn.close()
            return None, False

        chain_ids.append(current)

        if max_depth and len(chain_ids) >= max_depth:
            break

        if lin["is_foundational"] or lin["predecessor_id"] is None:
            break

        current = lin["predecessor_id"]

    conn.close()

    # Reconstruct step dicts for each paper in chain
    steps = []
    for depth, pid in enumerate(chain_ids):
        cached = get_cached_analysis(pid)
        paper  = get_paper(pid)

        if cached is None or paper is None:
            return None, False

        pred_id   = cached.get("selected_predecessor_id")
        pred_paper = get_paper(pred_id) if pred_id else None

        step = {
            "depth":              depth,
            "target_paper":       paper,
            "target_text":        "",      # not stored; not needed after Gemini cached
            "target_source_type": paper.get("_source_type") or "FULL_TEXT",
            "predecessor_paper":  pred_paper,
            "candidates_considered": 0,   # not stored
            "analysis":           cached,
            "is_foundational":    bool(pred_paper is None),
        }
        steps.append(step)

    return steps, True


# ─────────────────────────────────────────────
# Module init
# ─────────────────────────────────────────────

init_db()
