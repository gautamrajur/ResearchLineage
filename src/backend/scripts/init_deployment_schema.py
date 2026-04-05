"""
scripts/init_deployment_schema.py
-----------------------------------
Creates the `deployment_schema` PostgreSQL schema and all application tables
inside it on the Cloud SQL instance.

Prerequisites:
    Cloud SQL Auth Proxy must be running on port 5432:
        ./cloud-sql-proxy researchlineage:us-central1:researchlineage-db --port 5432

Usage:
    # from repo root, with venv activated
    python -m src.backend.scripts.init_deployment_schema

    # or with env override
    PG_PASSWORD=mypassword python -m src.backend.scripts.init_deployment_schema

Idempotent — safe to run multiple times (all statements use IF NOT EXISTS).
"""

import logging
import os
import sys
import time

import psycopg2

# ---------------------------------------------------------------------------
# Logger  (format matches the project analytics standard)
# ---------------------------------------------------------------------------

_fmt = logging.Formatter(
    fmt="%(asctime)s | %(levelname)-5s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
_handler = logging.StreamHandler(sys.stdout)
_handler.setFormatter(_fmt)

log = logging.getLogger("init_schema")
log.setLevel(logging.DEBUG)
log.addHandler(_handler)
log.propagate = False


def _tag(tag: str, **kwargs) -> str:
    pairs = " ".join(f"{k}={v}" for k, v in kwargs.items())
    return f"[{tag}] {pairs}"


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://jithin:{pw}@127.0.0.1:5432/researchlineage".format(
        pw=os.environ.get("PG_PASSWORD", "jithin")
    ),
)

SCHEMA_NAME = "deployment_schema"

# ---------------------------------------------------------------------------
# DDL — one statement per table so we can log each individually
# ---------------------------------------------------------------------------

TABLES = {
    "papers": """
        CREATE TABLE IF NOT EXISTS {schema}.papers (
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
        )
    """,
    "references": """
        CREATE TABLE IF NOT EXISTS {schema}."references" (
            paper_id              TEXT,
            cited_paper_id        TEXT,
            is_influential        INT,
            intents               TEXT,
            cited_citation_count  INT,
            fetched_at            TEXT,
            PRIMARY KEY (paper_id, cited_paper_id)
        )
    """,
    "citations": """
        CREATE TABLE IF NOT EXISTS {schema}.citations (
            paper_id               TEXT,
            citing_paper_id        TEXT,
            is_influential         INT,
            intents                TEXT,
            citing_citation_count  INT,
            year_window_start      INT,
            year_window_end        INT,
            fetched_at             TEXT,
            PRIMARY KEY (paper_id, citing_paper_id)
        )
    """,
    "fetch_log": """
        CREATE TABLE IF NOT EXISTS {schema}.fetch_log (
            paper_id      TEXT,
            fetch_type    TEXT,
            year_start    INT,
            year_end      INT,
            result_count  INT,
            fetched_at    TEXT,
            PRIMARY KEY (paper_id, fetch_type, year_start, year_end)
        )
    """,
    "lineage": """
        CREATE TABLE IF NOT EXISTS {schema}.lineage (
            paper_id             TEXT PRIMARY KEY,
            predecessor_id       TEXT,
            is_foundational      INT,
            selection_reasoning  TEXT
        )
    """,
    "analysis": """
        CREATE TABLE IF NOT EXISTS {schema}.analysis (
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
        )
    """,
    "comparison": """
        CREATE TABLE IF NOT EXISTS {schema}.comparison (
            paper_id                        TEXT PRIMARY KEY,
            predecessor_id                  TEXT,
            what_was_improved               TEXT,
            how_it_was_improved             TEXT,
            why_it_matters                  TEXT,
            problem_solved_from_predecessor TEXT,
            remaining_limitations           TEXT
        )
    """,
    "secondary_influences": """
        CREATE TABLE IF NOT EXISTS {schema}.secondary_influences (
            paper_id         TEXT,
            influenced_by_id TEXT,
            contribution     TEXT,
            PRIMARY KEY (paper_id, influenced_by_id)
        )
    """,
    "trees": """
        CREATE TABLE IF NOT EXISTS {schema}.trees (
            tree_id        TEXT PRIMARY KEY,
            root_paper_id  TEXT,
            generated_at   TEXT,
            max_depth      INT,
            max_children   INT,
            window_years   INT
        )
    """,
    "tree_nodes": """
        CREATE TABLE IF NOT EXISTS {schema}.tree_nodes (
            tree_id         TEXT,
            paper_id        TEXT,
            node_type       TEXT,
            depth           INT,
            parent_paper_id TEXT,
            PRIMARY KEY (tree_id, paper_id)
        )
    """,
    "feedback": """
        CREATE TABLE IF NOT EXISTS {schema}.feedback (
            feedback_id      TEXT PRIMARY KEY,
            paper_id         TEXT,
            related_paper_id TEXT,
            view_type        TEXT,
            feedback_target  TEXT,
            rating           INT,
            comment          TEXT,
            created_at       TEXT
        )
    """,
}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def init_schema(dsn: str = DATABASE_URL, schema: str = SCHEMA_NAME) -> None:
    t_start = time.perf_counter()

    log.info(_tag("INIT_START", schema=schema, host="127.0.0.1:5432", db="researchlineage"))

    # -- connect -------------------------------------------------------------
    log.info(_tag("DB_CONNECT", dsn=dsn.replace(dsn.split("@")[0].split("//")[1], "***")))
    try:
        conn = psycopg2.connect(dsn)
        conn.autocommit = True          # DDL doesn't need explicit transaction
        log.info(_tag("DB_CONNECT_OK"))
    except Exception as exc:
        log.error(_tag("DB_CONNECT_FAILED", error=exc))
        sys.exit(1)

    cur = conn.cursor()

    # -- create schema -------------------------------------------------------
    log.info(_tag("SCHEMA_CREATE", name=schema))
    try:
        cur.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
        log.info(_tag("SCHEMA_CREATE_OK", name=schema))
    except Exception as exc:
        log.error(_tag("SCHEMA_CREATE_FAILED", name=schema, error=exc))
        print(
            "\n"
            "  The app user lacks CREATE ON DATABASE.  Run these two lines\n"
            "  as the postgres/admin user (Cloud Console > Cloud SQL > researchlineage\n"
            "  > Cloud Shell, or psql as postgres) then re-run this script:\n\n"
            f"      GRANT CREATE ON DATABASE researchlineage TO jithin;\n"
            f"      CREATE SCHEMA IF NOT EXISTS {schema} AUTHORIZATION jithin;\n",
            file=sys.stderr,
        )
        conn.close()
        sys.exit(1)

    # -- set search_path so subsequent queries resolve without prefix --------
    cur.execute(f"SET search_path TO {schema}, public")

    # -- create tables -------------------------------------------------------
    created = 0
    failed  = 0

    for table_name, ddl in TABLES.items():
        stmt = ddl.format(schema=schema).strip()
        t0 = time.perf_counter()
        try:
            cur.execute(stmt)
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            log.info(_tag("TABLE_CREATE_OK", table=f"{schema}.{table_name}", elapsed_ms=elapsed_ms))
            created += 1
        except Exception as exc:
            log.error(_tag("TABLE_CREATE_FAILED", table=f"{schema}.{table_name}", error=exc))
            failed += 1

    # -- verify --------------------------------------------------------------
    log.info(_tag("VERIFY_START", schema=schema))
    cur.execute(
        """
        SELECT table_name
        FROM   information_schema.tables
        WHERE  table_schema = %s
        ORDER  BY table_name
        """,
        (schema,),
    )
    found = [row[0] for row in cur.fetchall()]
    log.info(_tag("VERIFY_TABLES_FOUND", count=len(found), tables=",".join(found)))

    expected = set(TABLES.keys())
    missing  = expected - set(found)
    if missing:
        log.warning(_tag("VERIFY_MISSING_TABLES", tables=",".join(sorted(missing))))
    else:
        log.info(_tag("VERIFY_OK", all_tables_present=True))

    # -- done ----------------------------------------------------------------
    elapsed_total = round(time.perf_counter() - t_start, 2)
    log.info(
        _tag(
            "INIT_COMPLETE",
            schema=schema,
            tables_created=created,
            tables_failed=failed,
            elapsed_sec=elapsed_total,
        )
    )

    cur.close()
    conn.close()


def grant_create(admin_dsn: str, schema: str, user: str) -> None:
    """
    One-time step: run as superuser to give `user` the right to create
    schemas and use this one.  Call before init_schema() when the regular
    user lacks CREATE ON DATABASE.
    """
    log.info(_tag("GRANT_START", admin_dsn=admin_dsn.split("@")[-1], user=user))
    conn = psycopg2.connect(admin_dsn)
    conn.autocommit = True
    cur = conn.cursor()

    cur.execute(f"GRANT CREATE ON DATABASE researchlineage TO {user}")
    log.info(_tag("GRANT_OK", privilege="CREATE ON DATABASE", user=user))

    # In case the schema was already created, hand it over too
    cur.execute(
        f"DO $$ BEGIN "
        f"  IF EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = '{schema}') THEN "
        f"    EXECUTE 'ALTER SCHEMA {schema} OWNER TO {user}'; "
        f"  END IF; "
        f"END $$"
    )
    cur.close()
    conn.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Init deployment_schema on Cloud SQL")
    parser.add_argument(
        "--dsn",
        default=DATABASE_URL,
        help="Connection string for the app user (default: DATABASE_URL env / jithin)",
    )
    parser.add_argument(
        "--admin-dsn",
        default=None,
        help=(
            "Superuser connection string to grant CREATE on the database first. "
            "Example: postgresql://postgres:password@127.0.0.1:5432/researchlineage"
        ),
    )
    parser.add_argument(
        "--schema",
        default=SCHEMA_NAME,
        help=f"Schema name to create (default: {SCHEMA_NAME})",
    )
    parser.add_argument(
        "--user",
        default="jithin",
        help="App DB user to grant privileges to (default: jithin)",
    )
    args = parser.parse_args()

    if args.admin_dsn:
        grant_create(args.admin_dsn, args.schema, args.user)

    init_schema(dsn=args.dsn, schema=args.schema)
